"""Тесты сервисов научных материалов и телеграмм."""

from datetime import date
from pathlib import Path

import pytest

from internal_correspondence.core.constants import (
    MaterialType,
    TelegramType,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import Branch, Country, ScientificMaterial, Telegram, TerritorialUnit
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.services.document_service import ScientificMaterialService, TelegramService


def _setup_refs(session):
    session.add(TerritorialUnit(id="MSK", name="Москва"))
    session.add(Country(id="RUS", name="Россия"))
    session.add(Branch(id="FIL001", name="Филиал 1", short_name="Ф-1", territorial_unit_id="MSK"))
    session.commit()


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_tables()
    yield db
    db.close()


def test_create_material(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_refs(session)
        service = ScientificMaterialService(session, storage)
        material = service.create_with_files({
            "type": MaterialType.MESSAGE,
            "outgoing_number": "123",
            "outgoing_date": date(2024, 1, 15),
            "name": "Материал 1",
            "branch_id": "FIL001",
        })
        session.commit()

        assert material.name == "Материал 1"
        assert material.branch_id == "FIL001"


def test_attach_file_copies_to_storage(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    source_file = tmp_path / "source.txt"
    source_file.write_text("test content")

    with db_manager.get_session() as session:
        _setup_refs(session)
        service = ScientificMaterialService(session, storage)
        material = service.create_with_files({
            "type": MaterialType.MESSAGE,
            "outgoing_number": "123",
            "outgoing_date": date(2024, 1, 15),
            "name": "Материал 1",
            "branch_id": "FIL001",
        }, file_paths=[source_file])
        session.commit()

        assert len(material.files) == 1
        file_record = material.files[0]
        target = storage / file_record.path / f"{file_record.name}.{file_record.extension}"
        assert target.exists()
        assert target.read_text() == "test content"


def test_create_telegram(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_refs(session)
        service = TelegramService(session, storage)
        telegram = service.create_with_files({
            "type": TelegramType.THEMATIC,
            "outgoing_number": "TG-1",
            "outgoing_date": date(2024, 2, 1),
            "name": "Телеграмма 1",
            "branch_id": "FIL001",
        })
        session.commit()

        assert telegram.name == "Телеграмма 1"
        assert telegram.type == TelegramType.THEMATIC


def test_update_material(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_refs(session)
        service = ScientificMaterialService(session, storage)
        material = service.create_with_files({
            "type": MaterialType.MESSAGE,
            "outgoing_number": "123",
            "outgoing_date": date(2024, 1, 15),
            "name": "Материал 1",
            "branch_id": "FIL001",
        })
        session.commit()

        service.update_with_files(material, {"name": "Материал 1 обновлённый"})
        session.commit()

        loaded = session.query(ScientificMaterial).one()
        assert loaded.name == "Материал 1 обновлённый"


def test_delete_material(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()

    with db_manager.get_session() as session:
        _setup_refs(session)
        service = ScientificMaterialService(session, storage)
        material = service.create_with_files({
            "type": MaterialType.MESSAGE,
            "outgoing_number": "123",
            "outgoing_date": date(2024, 1, 15),
            "name": "Материал 1",
            "branch_id": "FIL001",
        })
        session.commit()

        service.delete(material)
        session.commit()

        assert session.query(ScientificMaterial).count() == 0
