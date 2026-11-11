"""Интеграционные тесты C3: директории, строки, meta.json, валидация кодов."""

import json
import os
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from internal_correspondence.core.constants import MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.domain_pack import (
    dir_name,
    get_domain_pack,
    load_domain_pack,
    set_domain_pack,
)
from internal_correspondence.importexport.export_service import ExportService
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.orm.models import Branch, Country, TerritorialUnit
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.services.enum_validation import validate_enum_codes
from internal_correspondence.utils.string_resources import STRINGS, reload_strings


@pytest.fixture(autouse=True)
def reset_pack_and_strings():
    """Возвращает дефолтный пакет и строки после каждого теста."""
    set_domain_pack(None)
    reload_strings()
    yield
    set_domain_pack(None)
    reload_strings()


def _write_pack(tmp_path: Path, extra: dict) -> Path:
    """Пишет минимальный валидный пакет с дополнительными секциями."""
    data = {
        "id": "test-pack",
        "version": "0.1",
        "enums": {
            "material_type": {
                "label": "Тип",
                "values": [{"key": "document", "code": "ДОК", "label": "Документ"}],
            }
        },
    }
    data.update(extra)
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_tables()
    yield db
    db.close()


class TestDirectories:
    """Имена служебных директорий из пакета."""

    def test_override_and_fallback(self, tmp_path):
        set_domain_pack(load_domain_pack(_write_pack(tmp_path, {
            "directories": {"export": "Выгрузка"},
        })))
        assert dir_name("export") == "Выгрузка"
        assert dir_name("files") == "Файлы"  # фолбэк на встроенное имя
        assert dir_name("material_files") == "Научные материалы"

    def test_default_pack_directories(self):
        assert dir_name("export") == "Экспорт"
        assert dir_name("templates") == "Шаблоны"


class TestStrings:
    """Строки интерфейса из пакета."""

    def test_strings_override(self, tmp_path):
        set_domain_pack(load_domain_pack(_write_pack(tmp_path, {
            "strings": {"app_title": "Учёт НИР"},
        })))
        reload_strings()
        assert STRINGS.app_title == "Учёт НИР"
        assert STRINGS.menu_file == "Файл"  # не переопределено — дефолт

    def test_strings_restore_on_default_pack(self, tmp_path):
        set_domain_pack(load_domain_pack(_write_pack(tmp_path, {
            "strings": {"app_title": "Учёт НИР"},
        })))
        reload_strings()
        set_domain_pack(None)
        reload_strings()
        assert STRINGS.app_title == "Внутренняя корреспонденция"

    def test_default_pack_strings_mirror_code(self):
        strings = get_domain_pack().strings()
        assert strings["app_title"] == "Внутренняя корреспонденция"
        assert strings["menu_data"] == "Данные"


class TestExportMeta:
    """Метаданные пакета в экспортном архиве."""

    def test_export_writes_meta_json(self, db_manager, tmp_path):
        storage = tmp_path / "storage"
        storage.mkdir()
        with db_manager.get_session() as session:
            session.add(Country(id="RUS", name="Россия"))
            session.commit()
            output = ExportService(session, storage).export()
            session.commit()

        with zipfile.ZipFile(output) as zf:
            meta = json.loads(zf.read("meta.json").decode("utf-8"))
        pack = get_domain_pack()
        assert meta["app"] == "internal-correspondence"
        assert meta["pack_id"] == pack.id
        assert meta["pack_version"] == pack.version
        assert meta["exported_at"]

    def test_import_same_pack_no_warnings(self, db_manager, tmp_path):
        storage = tmp_path / "storage"
        storage.mkdir()
        archive = tmp_path / "same.zip"
        pack = get_domain_pack()
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("meta.json", json.dumps({
                "app": "internal-correspondence",
                "pack_id": pack.id,
                "pack_version": pack.version,
            }))
            zf.writestr("export.json", json.dumps(
                {"Country": {"RUS": {"id": "RUS", "name": "Россия"}}},
                ensure_ascii=False,
            ))
        with db_manager.get_session() as session:
            result = ImportService(session, storage, "head_office").import_archive(archive)
        assert result["warnings"] == []
        assert result["imported"] == 1

    def test_import_other_pack_warns(self, db_manager, tmp_path):
        storage = tmp_path / "storage"
        storage.mkdir()
        archive = tmp_path / "other.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("meta.json", json.dumps({
                "app": "internal-correspondence",
                "pack_id": "hospital-pack",
                "pack_version": "2.0",
            }))
            zf.writestr("export.json", json.dumps(
                {"Country": {"RUS": {"id": "RUS", "name": "Россия"}}},
                ensure_ascii=False,
            ))
        with db_manager.get_session() as session:
            result = ImportService(session, storage, "head_office").import_archive(archive)
        assert result["imported"] == 1
        assert len(result["warnings"]) == 1
        assert "hospital-pack" in result["warnings"][0]

    def test_import_legacy_archive_without_meta(self, db_manager, tmp_path):
        storage = tmp_path / "storage"
        storage.mkdir()
        archive = tmp_path / "legacy.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("export.json", json.dumps(
                {"Country": {"RUS": {"id": "RUS", "name": "Россия"}}},
                ensure_ascii=False,
            ))
        with db_manager.get_session() as session:
            result = ImportService(session, storage, "head_office").import_archive(archive)
        assert result["warnings"] == []


class TestEnumValidation:
    """Проверка кодов перечислений БД против активного пакета."""

    def test_unknown_code_warns(self, db_manager):
        with db_manager.get_session() as session:
            session.add(TerritorialUnit(id="MSK", name="Москва"))
            session.add(Branch(id="F1", name="Ф", short_name="Ф", territorial_unit_id="MSK"))
            session.commit()
            from internal_correspondence.orm.models import ScientificMaterial

            # 99 вне диапазона MaterialType — имитация данных чужого пакета
            session.add(ScientificMaterial(type=99, name="М", branch_id="F1"))
            session.commit()
            warnings = validate_enum_codes(session)
        assert any("99" in warning for warning in warnings)

    def test_known_codes_no_warnings(self, db_manager):
        with db_manager.get_session() as session:
            session.add(TerritorialUnit(id="MSK", name="Москва"))
            session.add(Branch(id="F1", name="Ф", short_name="Ф", territorial_unit_id="MSK"))
            session.commit()
            from internal_correspondence.orm.models import ScientificMaterial

            session.add(ScientificMaterial(type=MaterialType.DOCUMENT, name="М", branch_id="F1"))
            session.commit()
            assert validate_enum_codes(session) == []

    def test_deprecated_codes_are_known(self, db_manager, tmp_path):
        """Устаревшее значение пакета в БД не должно считаться ошибкой."""
        pack_path = _write_pack(tmp_path, {})
        data = json.loads(pack_path.read_text(encoding="utf-8"))
        data["enums"]["material_type"]["values"].append(
            {
                "key": "product_sample",
                "code": "ОП",
                "label": "Образец продукции",
                "deprecated": True,
            }
        )
        pack_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        set_domain_pack(load_domain_pack(pack_path))

        with db_manager.get_session() as session:
            session.add(TerritorialUnit(id="MSK", name="Москва"))
            session.add(Branch(id="F1", name="Ф", short_name="Ф", territorial_unit_id="MSK"))
            session.commit()
            from internal_correspondence.orm.models import ScientificMaterial

            session.add(
                ScientificMaterial(type=MaterialType.PRODUCT_SAMPLE, name="М", branch_id="F1")
            )
            session.commit()
            warnings = validate_enum_codes(session)
        assert not any("PRODUCT_SAMPLE" in warning for warning in warnings)


class TestPackSerialization:
    """Выгрузка пакета в JSON и круговой оборот (меню «Пакет предметной области»)."""

    def test_default_pack_roundtrip(self):
        from internal_correspondence.core.domain_pack import (
            DomainPack,
            default_domain_pack,
        )

        original = default_domain_pack()
        restored = DomainPack.from_dict(original.to_dict())

        assert restored.id == original.id
        assert restored.version == original.version
        assert restored.labels("material_type") == original.labels("material_type")
        assert restored.weight("evaluation_value", "В") == 3
        assert restored.entity_label("Telegram", plural=True) == "Телеграммы"
        assert restored.entity_field_info(
            "ScientificMaterial", "outgoing_number"
        ) == {"label": "Исходящий номер", "short": "Исх. номер", "required": True}
        assert restored.strings() == original.strings()

    def test_save_domain_pack_writes_loadable_file(self, tmp_path):
        from internal_correspondence.core.domain_pack import (
            default_domain_pack,
            save_domain_pack,
        )

        path = save_domain_pack(default_domain_pack(), tmp_path / "exported.json")
        reloaded = load_domain_pack(path)
        assert reloaded.id == "scientific-network"
        assert reloaded.entity_label("ScientificMaterial") == "Научный материал"
        assert reloaded.directory("export") == "Экспорт"
