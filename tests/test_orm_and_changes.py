"""Тесты ORM-моделей и механизма отслеживания изменений."""

import os
import uuid
from datetime import date, datetime
from pathlib import Path

import pytest

from internal_correspondence.core.constants import ChangeOperation, ScientificTaskType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    Branch,
    Change,
    Country,
    Department,
    Employee,
    ScientificTask,
    TaskEntityLink,
    TerritorialUnit,
)
from internal_correspondence.services.change_tracking import (
    clear_change,
    purge_expired_changes,
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
        assert change.operation_type == ChangeOperation.CREATE.value
        assert "name" in change.changed_fields
        assert "short_name" in change.changed_fields
        assert branch.change_id == change.id


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
    """При удалении Change фиксирует операцию удаления с пустым множеством полей."""
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
        assert change.operation_type == ChangeOperation.DELETE.value
        assert change.changed_fields == []


def test_delete_before_export_removes_change(db_manager: DatabaseManager) -> None:
    """Удаление неэкспортированного создания просто удаляет запись Change."""
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        branch = Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()

        session.delete(branch)
        session.commit()

        assert session.query(Change).filter(Change.entity_name == "Branch").count() == 0


def test_update_unions_fields_before_export(db_manager: DatabaseManager) -> None:
    """До экспорта множество полей Change объединяется, тип операции остаётся «создание»."""
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        branch = Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()

        branch.name = "Филиал 1 новый"
        session.commit()
        branch.short_name = "Ф-1"
        session.commit()

        change = session.query(Change).filter(Change.entity_name == "Branch").one()
        assert change.operation_type == ChangeOperation.CREATE.value
        assert set(change.changed_fields) == {"id", "name", "short_name", "territorial_unit_id"}
        assert branch.change_id == change.id


def test_recreate_after_delete_rewrites_change(db_manager: DatabaseManager) -> None:
    """Пересоздание с тем же PK перезаписывает найденную запись Change как создание."""
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        branch = Branch(id="FIL001", name="Филиал 1", short_name="Фил-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()
        old_change_id = branch.change_id

        session.delete(branch)
        session.commit()

        branch = Branch(id="FIL001", name="Филиал 1", short_name="Ф-1", territorial_unit_id="MSK")
        session.add(branch)
        session.commit()

        change = session.query(Change).filter(Change.entity_name == "Branch").one()
        assert change.id == old_change_id
        assert change.operation_type == ChangeOperation.CREATE.value
        assert change.exported_at is None
        assert branch.change_id == change.id


def test_purge_removes_only_expired_exported(db_manager: DatabaseManager) -> None:
    """Чистка удаляет только экспортированные записи старше срока хранения."""
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(Country(id="RUS", name="Россия"))
        session.commit()

        exported_change = (
            session.query(Change).filter(Change.entity_name == "TerritorialUnit").one()
        )
        exported_change.exported_at = datetime(2026, 1, 1)
        session.commit()

        removed = purge_expired_changes(session, retention_days=30)
        session.commit()

        assert removed == 1
        assert session.query(Change).filter(Change.entity_name == "TerritorialUnit").count() == 0
        # Неэкспортированная запись не тронута
        assert session.query(Change).filter(Change.entity_name == "Country").count() == 1


def test_purge_disabled_with_non_positive_retention(db_manager: DatabaseManager) -> None:
    """При сроке <= 0 чистка не выполняется (бессрочное хранение)."""
    with db_manager.get_session() as session:
        session.add(Country(id="RUS", name="Россия"))
        session.commit()

        change = session.query(Change).one()
        change.exported_at = datetime(2020, 1, 1)
        session.commit()

        assert purge_expired_changes(session, retention_days=0) == 0
        assert session.query(Change).count() == 1


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


def test_task_entity_link(db_manager: DatabaseManager) -> None:
    """Связь задачи с сущностью сохраняется; удаление задачи каскадно удаляет связи."""
    with db_manager.get_session() as session:
        task = ScientificTask(
            id="T1",
            name="Задача 1",
            type=ScientificTaskType.MAIN,
            start_date=date(2026, 1, 1),
        )
        session.add(task)
        session.commit()

        link = TaskEntityLink(
            task_id="T1", entity_name="Employee", entity_pk="emp-1"
        )
        session.add(link)
        session.commit()
        link_id = link.id
        assert isinstance(link_id, int)

        loaded = session.get(TaskEntityLink, link_id)
        assert loaded.task_id == "T1"
        assert loaded.entity_name == "Employee"
        assert loaded.entity_pk == "emp-1"

        session.delete(task)
        session.commit()
        session.expire_all()
        assert session.get(TaskEntityLink, link_id) is None
