"""Тесты базового CRUD-сервиса."""

from pathlib import Path

import pytest

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import Branch, Country, TerritorialUnit
from internal_correspondence.services.base_service import BaseService
from internal_correspondence.services.change_tracking import register_change_tracking


def _db_path(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(_db_path(tmp_path))
    db.create_tables()
    yield db
    db.close()


def test_create_and_get(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        service = BaseService(session, Country)
        country = service.create({"id": "RUS", "name": "Россия"})
        session.commit()

        loaded = service.get_by_id("RUS")
        assert loaded is not None
        assert loaded.name == "Россия"


def test_update(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        service = BaseService(session, Country)
        country = service.create({"id": "RUS", "name": "Россия"})
        service.update(country, {"name": "Российская Федерация"})
        session.commit()

        loaded = service.get_by_id("RUS")
        assert loaded.name == "Российская Федерация"


def test_delete(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        service = BaseService(session, Country)
        country = service.create({"id": "RUS", "name": "Россия"})
        session.commit()

        service.delete(country)
        session.commit()

        loaded = service.get_by_id("RUS")
        assert loaded is None


def test_pagination(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        tu_service = BaseService(session, TerritorialUnit)
        tu_service.create({"id": "MSK", "name": "Москва"})
        branch_service = BaseService(session, Branch)
        branch_service.create({
            "id": "FIL001",
            "name": "Филиал 1",
            "short_name": "Ф-1",
            "territorial_unit_id": "MSK",
        })
        branch_service.create({
            "id": "FIL002",
            "name": "Филиал 2",
            "short_name": "Ф-2",
            "territorial_unit_id": "MSK",
        })
        session.commit()

        page = branch_service.get_paginated(page=1, page_size=1, order_by="id")
        assert page["total"] == 2
        assert len(page["items"]) == 1
        assert page["pages"] == 2


def test_count(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        service = BaseService(session, Country)
        service.create({"id": "RUS", "name": "Россия"})
        service.create({"id": "USA", "name": "США"})
        session.commit()

        assert service.count() == 2
