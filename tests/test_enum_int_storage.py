"""Тесты целочисленного хранения кодов перечислений (IntEnum)."""

import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from internal_correspondence.core.constants import MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.domain_pack import (
    load_domain_pack,
    set_domain_pack,
)
from internal_correspondence.core.enum_registry import (
    pack_enum_choices,
    pack_enum_display,
    pack_enum_key,
)
from internal_correspondence.importexport.export_service import ExportService
from internal_correspondence.orm.models import (
    Branch,
    ScientificMaterial,
    TerritorialUnit,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from sqlalchemy import text


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    """Создаёт временную БД с актуальными таблицами."""
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_tables()
    yield db
    db.close()


def _create_material(session) -> ScientificMaterial:
    session.add(TerritorialUnit(id="MSK", name="Москва"))
    session.add(Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK"))
    material = ScientificMaterial(
        type=MaterialType.TECHNICAL_DOCUMENT,
        name="Материал",
        branch_id="F1",
    )
    session.add(material)
    session.commit()
    return material


def test_enum_stored_as_integer(db_manager: DatabaseManager) -> None:
    """В колонке БД хранится целое число, в Python загружается IntEnum."""
    with db_manager.get_session() as session:
        material = _create_material(session)
        raw = session.execute(text("SELECT type FROM scientific_materials")).scalar()
        assert raw == 4
        session.expire_all()
        assert session.get(ScientificMaterial, material.id).type == MaterialType.TECHNICAL_DOCUMENT


def test_enum_exported_as_integer(db_manager: DatabaseManager, tmp_path: Path) -> None:
    """Экспортный JSON содержит числовое значение перечисления."""
    storage = tmp_path / "storage"
    storage.mkdir()
    with db_manager.get_session() as session:
        material = _create_material(session)
        material_id = str(material.id)
        output = ExportService(session, storage).export()
        session.commit()

    with zipfile.ZipFile(output) as zf:
        data = json.loads(zf.read("export.json").decode("utf-8"))
    assert data["ScientificMaterial"][material_id]["type"] == int(
        MaterialType.TECHNICAL_DOCUMENT
    )


def test_pack_enum_display(db_manager: DatabaseManager) -> None:
    """Краткий текст определяется пакетом; неизвестные значения не падают."""
    assert pack_enum_display("material_type", int(MaterialType.MESSAGE)) == "С"
    assert pack_enum_display("material_type", int(MaterialType.TECHNICAL_DOCUMENT)) == "ТДОК"
    assert pack_enum_display("material_type", None) == ""
    assert pack_enum_display("material_type", 99) == "99"
    assert pack_enum_key("material_type", int(MaterialType.REPORT)) == "report"


def test_pack_enum_choices_excludes_deprecated(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    """Значения, помеченные в пакете deprecated, не попадают в выбор."""
    data = json.loads(
        Path("internal_correspondence/core/domain_pack.default.json").read_text(encoding="utf-8")
    )
    for value in data["enums"]["material_type"]["values"]:
        if value["key"] == "report":
            value["deprecated"] = True
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    set_domain_pack(load_domain_pack(pack_path))
    try:
        values = [value for value, _text in pack_enum_choices("material_type")]
        assert int(MaterialType.REPORT) not in values
        assert int(MaterialType.MESSAGE) in values
    finally:
        set_domain_pack(None)
