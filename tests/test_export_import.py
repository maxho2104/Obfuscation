"""Тесты экспорта и импорта изменений."""

from pathlib import Path

import pytest

from internal_correspondence.core.constants import Role
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.importexport.export_service import ExportService, ExportError
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.orm.models import Branch, Change, Country, TerritorialUnit
from internal_correspondence.services.base_service import BaseService
from internal_correspondence.services.change_tracking import register_change_tracking


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


def test_export_clears_changes(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_data(session)
        service = ExportService(session, storage)
        service.export()
        session.commit()

        assert session.query(Change).count() == 0


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
