"""Тесты ORM-моделей и механизма отслеживания изменений."""

import os
import uuid
from pathlib import Path

import pytest

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    Branch,
    Change,
    Country,
    Department,
    Employee,
    TerritorialUnit,
)
from internal_correspondence.services.change_tracking import (
    DELETION_MARKER,
    clear_change,
    register_change_tracking,
)


def _db_path(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    """Создаёт временную БД с актуальными таблицами."""
    register_change_tracking()
    db = DatabaseManager(_db_path(tmp_path))
    db.create_tables()
    yield db
    db.close()


def test_create_tables(db_manager: DatabaseManager) -> None:
    """Таблицы создаются без ошибок."""
    assert db_manager.engine is not None


def test_insert_creates_change(db_manager: DatabaseManager) -> None:
    """При вставке создаётся запись Change с полным набором полей."""
    with db_manager.get_session() as session:
        tu = TerritorialUnit(id="MSK", name="Москва")
        session.add(tu)
        branch = Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()

        changes = session.query(Change).all()
        assert len(changes) == 2

        change = next(c for c in changes if c.entity_name == "Branch")
        assert change.entity_pk == "FIL001"
        assert "name" in change.changed_fields
        assert "short_name" in change.changed_fields


def test_update_merges_changed_fields(db_manager: DatabaseManager) -> None:
    """При обновлении поля Change дополняется (или сохраняет набор полей)."""
    with db_manager.get_session() as session:
        tu = TerritorialUnit(id="MSK", name="Москва")
        session.add(tu)
        branch = Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()

        clear_change(session, branch)
        session.commit()

        branch.name = "Филиал 1 обновлённый"
        session.commit()

        change = session.query(Change).filter(Change.entity_name == "Branch").one()
        assert change.changed_fields == ["name"]


def test_delete_marks_deletion(db_manager: DatabaseManager) -> None:
    """При удалении объекта Change помечается маркером __DELETED__."""
    with db_manager.get_session() as session:
        tu = TerritorialUnit(id="MSK", name="Москва")
        session.add(tu)
        branch = Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()

        clear_change(session, branch)
        session.commit()

        branch.name = "Филиал 1 обновлённый"
        session.commit()

        session.delete(branch)
        session.commit()

        change = session.query(Change).filter(Change.entity_name == "Branch").one()
        assert change.changed_fields == [DELETION_MARKER]


def test_oshm_relationships(db_manager: DatabaseManager) -> None:
    """ОШС: филиал → отдел → сотрудник связаны корректно."""
    with db_manager.get_session() as session:
        tu = TerritorialUnit(id="MSK", name="Москва")
        session.add(tu)
        branch = Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()

        dept = Department(name="Отдел 1", branch_id=branch.id)
        session.add(dept)
        session.commit()

        emp = Employee(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
            department_id=dept.id,
        )
        session.add(emp)
        session.commit()

        loaded = session.query(Employee).one()
        assert loaded.department.branch.id == branch.id
        assert loaded.display_name().startswith("Иванов И.")


def test_uuid_generation(db_manager: DatabaseManager) -> None:
    """UUID генерируется автоматически для Department."""
    with db_manager.get_session() as session:
        tu = TerritorialUnit(id="MSK", name="Москва")
        session.add(tu)
        branch = Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()

        dept = Department(name="Отдел UUID", branch_id=branch.id)
        session.add(dept)
        session.commit()

        assert isinstance(dept.id, uuid.UUID)


def test_change_records_uuid_primary_key(db_manager: DatabaseManager) -> None:
    """Для сущностей с UUID-ключом Change сохраняет реальный ключ, а не None."""
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK"))
        session.commit()

        dept = Department(name="Отдел UUID", branch_id="FIL001")
        session.add(dept)
        session.commit()

        change = session.query(Change).filter(Change.entity_name == "Department").one()
        assert change.entity_pk == str(dept.id)
        assert set(change.changed_fields) <= set(Department.__mapper__.columns.keys())


def test_country_basic(db_manager: DatabaseManager) -> None:
    """Справочник страны сохраняется и читается."""
    with db_manager.get_session() as session:
        country = Country(id="RUS", name="Российская Федерация")
        session.add(country)
        session.commit()

        loaded = session.query(Country).one()
        assert loaded.id == "RUS"
        assert loaded.name == "Российская Федерация"
