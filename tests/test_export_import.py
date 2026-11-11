"""Тесты экспорта и импорта изменений."""

import json
import os
import uuid
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from internal_correspondence.core.constants import (
    ChangeOperation,
    MaterialType,
    Role,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.importexport.export_service import ExportService, ExportError
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.orm.models import (
    Branch,
    Change,
    Country,
    Department,
    Employee,
    FileRecord,
    ScientificMaterial,
    TerritorialUnit,
)
from internal_correspondence.services.base_service import BaseService
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.services.document_service import ScientificMaterialService


def _read_export_json(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as zf:
        return json.loads(zf.read("export.json").decode("utf-8"))


def _setup_data(session):
    tu = TerritorialUnit(id="MSK", name="Москва")
    session.add(tu)
    branch = Branch(id="FIL001", name="Филиал 1", short_name="Ф-1", territorial_unit_id="MSK")
    session.add(branch)
    country = Country(id="RUS", name="Россия")
    session.add(country)
    session.commit()


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="module")
def qt_app():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_export_creates_zip(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)

        service = ExportService(session, storage)
        output = service.export()
        session.commit()

    assert output.exists()
    assert output.suffix == ".zip"


def test_export_marks_changes_exported(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        service = ExportService(session, storage)
        service.export()
        session.commit()

        # Записи Change сохраняются с датой экспорта; ссылки у сущностей сбрасываются
        changes = session.query(Change).all()
        assert len(changes) == 3
        assert all(change.exported_at is not None for change in changes)
        country = session.query(Country).one()
        assert country.change_id is None


def test_export_json_groups_by_entity_and_primary_key(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        service = ExportService(session, storage)
        output = service.export()
        session.commit()

    data = _read_export_json(output)
    assert "changes" not in data
    assert set(data) == {"TerritorialUnit", "Branch", "Country"}
    assert data["Country"]["RUS"] == {"id": "RUS", "name": "Россия"}


def test_export_removes_highlight_in_open_table(
    db_manager: DatabaseManager, tmp_path: Path, qt_app
) -> None:
    from PyQt5.QtCore import Qt

    from internal_correspondence.gui.table_model import ColumnDef, SqlAlchemyTableModel

    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)

    model_session = db_manager.get_session()
    try:
        model = SqlAlchemyTableModel(
            model_session, Country, [ColumnDef("name", "Название")]
        )
        index = model.index(0, 0)
        assert model.data(index, Qt.BackgroundRole) is not None

        export_session = db_manager.get_session()
        try:
            ExportService(export_session, storage).export()
            export_session.commit()
        finally:
            export_session.close()

        model_session.expire_all()
        model.refresh()

        assert model.data(model.index(0, 0), Qt.BackgroundRole) is None
        assert model_session.query(Change).count() == 3
        assert all(c.exported_at is not None for c in model_session.query(Change).all())
        assert model_session.get(Country, "RUS").change_id is None
    finally:
        model_session.close()


def test_countries_many_to_many_tracked_and_exported(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    """Страны документа N-N: трекинг связи и экспорт списка кодов."""
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK"))
        session.add(Country(id="RUS", name="Россия"))
        session.add(Country(id="USA", name="США"))
        material = ScientificMaterial(
            id=uuid.uuid4(),
            type=MaterialType.MESSAGE,
            name="Материал",
            branch_id="F1",
            countries=[session.get(Country, "RUS"), session.get(Country, "USA")],
        )
        session.add(material)
        session.commit()
        material_id = str(material.id)

        output = ExportService(session, storage).export()
        session.commit()

    with zipfile.ZipFile(output) as zf:
        data = json.loads(zf.read("export.json").decode("utf-8"))
    assert data["ScientificMaterial"][material_id]["countries"] == ["RUS", "USA"]

    # Изменение связи после экспорта трекается как новая дельта
    with db_manager.get_session() as session:
        material = session.get(ScientificMaterial, uuid.UUID(material_id))
        material.countries = [session.get(Country, "RUS")]
        session.commit()

        change = (
            session.query(Change)
            .filter(Change.entity_name == "ScientificMaterial")
            .one()
        )
        assert change.changed_fields == ["countries"]

        output = ExportService(session, storage).export()
        session.commit()

    with zipfile.ZipFile(output) as zf:
        data = json.loads(zf.read("export.json").decode("utf-8"))
    assert data["ScientificMaterial"][material_id]["countries"] == ["RUS"]


def test_import_creates_m2m_countries(db_manager: DatabaseManager, tmp_path: Path) -> None:
    """Импорт восстанавливает N-N связь документа со странами."""
    storage = tmp_path / "storage"
    storage.mkdir()
    material_id = str(uuid.uuid4())
    payload = {
        "ScientificMaterial": {
            material_id: {
                "id": material_id,
                "type": int(MaterialType.MESSAGE),
                "name": "Материал",
                "branch_id": "F1",
                "countries": ["RUS", "USA"],
            }
        },
        "Country": {
            "RUS": {"id": "RUS", "name": "Россия"},
            "USA": {"id": "USA", "name": "США"},
        },
        "Branch": {
            "F1": {
                "id": "F1",
                "name": "Филиал",
                "short_name": "Ф",
                "territorial_unit_id": "MSK",
            }
        },
        "TerritorialUnit": {"MSK": {"id": "MSK", "name": "Москва"}},
    }
    archive = tmp_path / "countries.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("export.json", json.dumps(payload, ensure_ascii=False))

    with db_manager.get_session() as session:
        result = ImportService(session, storage, Role.HEAD_OFFICE.value).import_archive(archive)

    assert result["imported"] == 5
    assert result["skipped"] == 0
    with db_manager.get_session() as session:
        material = session.query(ScientificMaterial).one()
        assert {country.id for country in material.countries} == {"RUS", "USA"}


def test_m2m_changes_are_tracked_and_exported(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    employee_id = uuid.uuid4()
    material_id = uuid.uuid4()
    department_id = uuid.uuid4()

    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK"))
        session.add(Department(id=department_id, name="Отдел", branch_id="F1"))
        session.add(
            Employee(
                id=employee_id,
                last_name="Иванов",
                first_name="Иван",
                department_id=department_id,
            )
        )
        session.add(
            ScientificMaterial(id=material_id, type=MaterialType.MESSAGE, name="Материал", branch_id="F1")
        )
        session.commit()
        ExportService(session, storage).export()
        session.commit()

        material = session.get(ScientificMaterial, material_id)
        employee = session.get(Employee, employee_id)
        material.employees = [employee]
        session.commit()

        change = (
            session.query(Change)
            .filter(Change.entity_name == "ScientificMaterial")
            .one()
        )
        assert "employees" in change.changed_fields

        output = ExportService(session, storage).export()
        session.commit()

    data = _read_export_json(output)
    assert data == {
        "ScientificMaterial": {str(material_id): {"employees": [str(employee_id)]}}
    }


def test_export_and_import_synchronizes_attached_files(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    source_storage = tmp_path / "source_storage"
    source_storage.mkdir()
    target_storage = tmp_path / "target_storage"
    target_storage.mkdir()

    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(
            Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK")
        )
        session.commit()

        source_file = tmp_path / "doc.txt"
        source_file.write_text("hello", encoding="utf-8")
        service = ScientificMaterialService(session, source_storage)
        material = service.create_with_files(
            {"type": int(MaterialType.MESSAGE), "name": "Материал", "branch_id": "F1"},
            [source_file],
        )
        session.commit()
        material_id = str(material.id)
        file_id = material.files[0].id

        output = ExportService(session, source_storage).export()
        session.commit()

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
        data = json.loads(zf.read("export.json").decode("utf-8"))

    assert f"files/{file_id}/doc.txt" in names
    assert data["ScientificMaterial"][material_id]["files"] == [str(file_id)]
    assert data["FileRecord"][str(file_id)]["name"] == "doc"

    target_db = DatabaseManager(f"sqlite:///{tmp_path / 'target.db'}")
    target_db.create_tables()
    try:
        with target_db.get_session() as session:
            result = ImportService(
                session, target_storage, Role.HEAD_OFFICE.value
            ).import_archive(output)

        assert result["imported"] == 4
        assert result["skipped"] == 0

        with target_db.get_session() as session:
            record = session.query(FileRecord).one()
            restored = (
                target_storage / record.path / f"{record.name}.{record.extension}"
            )
            assert restored.exists()
            assert restored.read_text(encoding="utf-8") == "hello"
    finally:
        target_db.close()


def test_import_creates_m2m_dependencies(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    employee_id = str(uuid.uuid4())
    material_id = str(uuid.uuid4())
    department_id = str(uuid.uuid4())
    payload = {
        "ScientificMaterial": {
            material_id: {
                "id": material_id,
                "type": int(MaterialType.MESSAGE),
                "name": "Материал",
                "branch_id": "F1",
                "employees": [employee_id],
            },
        },
        "Employee": {
            employee_id: {
                "id": employee_id,
                "last_name": "Петров",
                "first_name": "Пётр",
                "department_id": department_id,
            }
        },
        "Department": {
            department_id: {
                "id": department_id,
                "name": "Отдел",
                "branch_id": "F1",
            }
        },
        "Branch": {
            "F1": {
                "id": "F1",
                "name": "Филиал",
                "short_name": "Ф",
                "territorial_unit_id": "MSK",
            }
        },
        "TerritorialUnit": {"MSK": {"id": "MSK", "name": "Москва"}},
    }
    archive = tmp_path / "m2m.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("export.json", json.dumps(payload, ensure_ascii=False))

    with db_manager.get_session() as session:
        service = ImportService(session, storage, Role.HEAD_OFFICE.value)
        result = service.import_archive(archive)

    assert result["imported"] == 5
    assert result["skipped"] == 0
    with db_manager.get_session() as session:
        material = session.query(ScientificMaterial).one()
        assert [employee.id for employee in material.employees] == [uuid.UUID(employee_id)]


def test_export_json_contains_only_changed_fields(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        service = ExportService(session, storage)
        service.export()
        session.commit()

    with db_manager.get_session() as session:
        country = session.get(Country, "RUS")
        country.name = "Российская Федерация"
        session.commit()

    with db_manager.get_session() as session:
        service = ExportService(session, storage)
        output = service.export()
        session.commit()

    data = _read_export_json(output)
    assert data == {"Country": {"RUS": {"name": "Российская Федерация"}}}


def test_import_resolves_dependencies_from_json(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    material_id = str(uuid.uuid4())
    payload = {
        "ScientificMaterial": {
            material_id: {
                "id": material_id,
                "type": int(MaterialType.MESSAGE),
                "name": "Материал",
                "branch_id": "FIL001",
            }
        },
        "Branch": {
            "FIL001": {
                "id": "FIL001",
                "name": "Филиал 1",
                "short_name": "Ф-1",
                "territorial_unit_id": "MSK",
            }
        },
        "TerritorialUnit": {"MSK": {"id": "MSK", "name": "Москва"}},
    }
    archive = tmp_path / "import.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("export.json", json.dumps(payload, ensure_ascii=False))

    with db_manager.get_session() as session:
        service = ImportService(session, storage, Role.HEAD_OFFICE.value)
        result = service.import_archive(archive)

    assert result["imported"] == 3
    assert result["skipped"] == 0
    with db_manager.get_session() as session:
        assert session.query(TerritorialUnit).count() == 1
        assert session.query(Branch).count() == 1
        assert session.query(ScientificMaterial).count() == 1
        assert session.query(Change).count() == 0


def test_update_after_export_starts_new_delta(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    """После экспорта изменение фиксируется как «изменение» только новых полей."""
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        ExportService(session, storage).export()
        session.commit()

    with db_manager.get_session() as session:
        country = session.get(Country, "RUS")
        country.name = "Российская Федерация"
        session.commit()

    with db_manager.get_session() as session:
        change = (
            session.query(Change).filter(Change.entity_name == "Country").one()
        )
        assert change.operation_type == ChangeOperation.UPDATE.value
        assert change.changed_fields == ["name"]
        assert change.exported_at is None
        assert session.get(Country, "RUS").change_id == change.id

        output = ExportService(session, storage).export()
        session.commit()

    data = _read_export_json(output)
    assert data == {"Country": {"RUS": {"name": "Российская Федерация"}}}


def test_delete_after_export_marks_deletion(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    """Удаление экспортированной сущности фиксируется как операция удаления."""
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        ExportService(session, storage).export()
        session.commit()

    with db_manager.get_session() as session:
        session.delete(session.get(Country, "RUS"))
        session.commit()

    with db_manager.get_session() as session:
        change = (
            session.query(Change).filter(Change.entity_name == "Country").one()
        )
        assert change.operation_type == ChangeOperation.DELETE.value
        assert change.changed_fields == []
        assert change.exported_at is None

        output = ExportService(session, storage).export()
        session.commit()

    data = _read_export_json(output)
    assert data == {"Country": {"RUS": {"deleted": True}}}


def test_recreate_after_exported_delete_reuses_change(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    """Пересоздание после экспортированного удаления перезаписывает запись Change."""
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        ExportService(session, storage).export()
        session.commit()

    with db_manager.get_session() as session:
        session.delete(session.get(Country, "RUS"))
        session.commit()

    with db_manager.get_session() as session:
        session.add(Country(id="RUS", name="Россия"))
        session.commit()

    with db_manager.get_session() as session:
        changes = session.query(Change).filter(Change.entity_name == "Country").all()
        assert len(changes) == 1
        change = changes[0]
        assert change.operation_type == ChangeOperation.CREATE.value
        assert change.exported_at is None
        assert set(change.changed_fields) == {"id", "name"}
        assert session.get(Country, "RUS").change_id == change.id


def test_second_export_raises_when_all_exported(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    """Повторный экспорт без новых изменений отклоняется."""
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        ExportService(session, storage).export()
        session.commit()

    with db_manager.get_session() as session:
        with pytest.raises(ExportError):
            ExportService(session, storage).export()


def test_export_raises_when_no_changes(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        service = ExportService(session, storage)
        with pytest.raises(ExportError):
            service.export()


def test_import_creates_entities(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        service = ExportService(session, storage)
        output = service.export()
        session.commit()

    # Очищаем БД, чтобы имитировать приёмную сторону
    with db_manager.get_session() as session:
        session.query(Country).delete()
        session.query(Branch).delete()
        session.query(TerritorialUnit).delete()
        session.commit()

    with db_manager.get_session() as session:
        service = ImportService(session, storage, Role.HEAD_OFFICE.value)
        result = service.import_archive(output)

    assert result["imported"] == 3
    assert result["deleted"] == 0

    with db_manager.get_session() as session:
        assert session.query(TerritorialUnit).count() == 1
        assert session.query(Branch).count() == 1
        assert session.query(Country).count() == 1


def test_import_updates_entities(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        service = ExportService(session, storage)
        output = service.export()
        session.commit()

    with db_manager.get_session() as session:
        service = ImportService(session, storage, Role.HEAD_OFFICE.value)
        result = service.import_archive(output)

    assert result["imported"] == 3


def test_import_deletes_entities(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        service = ExportService(session, storage)
        output = service.export()
        session.commit()

    # Удаляем страну и экспортируем удаление
    with db_manager.get_session() as session:
        country_service = BaseService(session, Country)
        country = country_service.get_by_id("RUS")
        country_service.delete(country)
        session.commit()

    with db_manager.get_session() as session:
        service = ExportService(session, storage)
        output2 = service.export()
        session.commit()

    # Восстанавливаем страну на приёмной стороне, чтобы проверить удаление
    with db_manager.get_session() as session:
        session.add(Country(id="RUS", name="Россия"))
        session.commit()

    with db_manager.get_session() as session:
        service = ImportService(session, storage, Role.HEAD_OFFICE.value)
        result = service.import_archive(output2)

    assert result["deleted"] == 1
    with db_manager.get_session() as session:
        assert session.query(Country).count() == 0
