"""Тесты вычисления причастных сотрудников, отделов и рабочих групп."""

from datetime import date
from pathlib import Path

import pytest

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.constants import (
    MaterialType,
    TelegramType,
)
from internal_correspondence.orm.models import (
    Branch,
    Department,
    Employee,
    ScientificMaterial,
    Telegram,
    TerritorialUnit,
    WorkingGroup,
)


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'participants.db'}")
    db.create_tables()
    yield db
    db.close()


def _create_oshm(session):
    session.add(TerritorialUnit(id="MSK", name="Москва"))
    branch = Branch(id="FIL001", name="Филиал 1", short_name="Ф-1", territorial_unit_id="MSK")
    session.add(branch)
    session.commit()

    department_one = Department(name="Отдел А", short_name="А", branch_id=branch.id)
    department_two = Department(name="Отдел Б", short_name="Б", branch_id=branch.id)
    session.add_all([department_one, department_two])
    session.commit()

    group_one = WorkingGroup(name="Группа 1", department_id=department_one.id)
    group_two = WorkingGroup(name="Группа 2", department_id=department_two.id)
    session.add_all([group_one, group_two])
    session.commit()

    employee_one = Employee(
        last_name="Иванов",
        first_name="Иван",
        department_id=department_one.id,
        working_group_id=group_one.id,
        workgroup_start_date=date(2024, 1, 1),
        workgroup_end_date=date(2024, 12, 31),
    )
    employee_two = Employee(
        last_name="Петров",
        first_name="Пётр",
        department_id=department_two.id,
        working_group_id=group_two.id,
        workgroup_start_date=date(2023, 1, 1),
        workgroup_end_date=date(2024, 5, 31),
    )
    session.add_all([employee_one, employee_two])
    session.commit()
    return branch, department_one, department_two, group_one, group_two, employee_one, employee_two


def test_material_participants_are_calculated_from_employees(db_manager: DatabaseManager) -> None:
    """Отделы берутся по принадлежности сотрудников, группы — по датам работы."""
    with db_manager.get_session() as session:
        branch, dept_one, dept_two, group_one, _group_two, employee_one, employee_two = _create_oshm(session)
        material = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="M-1",
            outgoing_date=date(2024, 6, 1),
            name="Материал",
            branch_id=branch.id,
            employees=[employee_one, employee_two],
        )
        session.add(material)
        session.commit()

        assert [employee.id for employee in material.participating_employees] == [
            employee_one.id,
            employee_two.id,
        ]
        assert [department.id for department in material.participating_departments] == [
            dept_one.id,
            dept_two.id,
        ]
        assert [workgroup.id for workgroup in material.participating_workgroups] == [group_one.id]


def test_telegram_uses_incoming_date_when_outgoing_date_is_missing(
    db_manager: DatabaseManager,
) -> None:
    """Для расчёта групп используется входящая дата, если исходящая не задана."""
    with db_manager.get_session() as session:
        branch, _dept_one, _dept_two, group_one, group_two, employee_one, employee_two = _create_oshm(session)
        telegram = Telegram(
            type=TelegramType.THEMATIC,
            name="Телеграмма",
            incoming_date=date(2024, 5, 15),
            branch_id=branch.id,
            employees=[employee_two],
        )
        session.add(telegram)
        session.commit()

        assert [workgroup.id for workgroup in telegram.participating_workgroups] == [group_two.id]
        assert telegram.participating_employees == [employee_two]

        telegram.employees = [employee_one]
        session.commit()
        assert [workgroup.id for workgroup in telegram.participating_workgroups] == [group_one.id]


def test_employee_workgroup_dates_are_optional(db_manager: DatabaseManager) -> None:
    """Если даты работы не заданы, членство в группе считается действующим."""
    with db_manager.get_session() as session:
        _branch, _dept_one, _dept_two, _group_one, _group_two, employee_one, _employee_two = _create_oshm(session)
        employee_one.workgroup_start_date = None
        employee_one.workgroup_end_date = None
        session.commit()

        assert employee_one.worked_in_workgroup_on(date(1900, 1, 1)) is True
        assert employee_one.worked_in_workgroup_on(date(2100, 1, 1)) is True

        employee_one.working_group_id = None
        assert employee_one.worked_in_workgroup_on(date(2024, 6, 1)) is False
