"""Тесты распределения научных задач по иерархии организации."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from internal_correspondence.core.constants import Role, ScientificTaskType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.importexport.export_service import ExportService
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.orm.models import (
    AddedTask,
    Branch,
    Department,
    Employee,
    ScientificTask,
    TerritorialUnit,
    WorkingGroup,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.services.reference_service import (
    ScientificTaskError,
    ScientificTaskService,
)
from internal_correspondence.services.task_distribution_service import (
    NODE_BRANCH,
    NODE_DEPARTMENT,
    NODE_EMPLOYEE,
    NODE_ORGANIZATION,
    NODE_REGION,
    NODE_WORKGROUP,
    FinancialPeriod,
    TaskDistributionError,
    TaskDistributionService,
)


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_tables()
    yield db
    db.close()


def _setup_org(session):
    unit = TerritorialUnit(id="MSK", name="Москва")
    branch = Branch(
        id="BR1",
        name="Филиал 1",
        short_name="Ф-1",
        territorial_unit_id="MSK",
    )
    session.add_all([unit, branch])
    session.flush()
    department = Department(name="Отдел 1", branch_id=branch.id)
    session.add(department)
    session.flush()
    employee = Employee(
        last_name="Иванов",
        first_name="Иван",
        department_id=department.id,
    )
    group = WorkingGroup(name="Группа 1", department_id=department.id)
    session.add_all([employee, group])
    session.flush()
    employee.working_group_id = group.id
    session.commit()
    return unit, branch, department, employee, group


def _task(task_id: str = "T1", start: date = date(2026, 1, 10)) -> ScientificTask:
    return ScientificTask(
        id=task_id,
        name="Задача " + task_id,
        type=ScientificTaskType.MAIN.value,
        start_date=start,
    )


def _key(node):
    return node.key


def test_tree_contains_organization_and_group_under_department(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        unit, branch, department, employee, group = _setup_org(session)
        service = TaskDistributionService(session, Role.HEAD_OFFICE.value)

        roots = service.build_tree()
        assert [root.node_type for root in roots] == [NODE_ORGANIZATION]
        organization = roots[0]
        assert [child.node_type for child in organization.children] == [NODE_REGION]

        department_node = service.node((NODE_DEPARTMENT, str(department.id)))
        assert department_node is not None
        child_types = {child.node_type for child in department_node.children}
        assert child_types == {NODE_EMPLOYEE, NODE_WORKGROUP}

        group_node = service.node((NODE_WORKGROUP, str(group.id)))
        assert group_node is not None
        assert [child.node_type for child in group_node.children] == [NODE_EMPLOYEE]
        assert group_node.children[0].assignable is False


def test_period_intersection_and_available_years(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup_org(session)
        service = TaskDistributionService(session, Role.HEAD_OFFICE.value)
        assert FinancialPeriod(2025).contains(date(2026, 1, 10), None)
        assert not FinancialPeriod(2024).contains(date(2026, 1, 10), None)

        task = _task("T1", date(2026, 1, 10))
        task.end_date = date(2027, 3, 1)
        session.add(task)
        session.commit()

        years = {period.year for period in service.available_periods()}
        assert 2025 in years
        assert 2026 in years


def test_head_office_assigns_chain_and_blocks_parent_unassign(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        unit, branch, department, employee, group = _setup_org(session)
        task = _task()
        session.add(task)
        session.commit()

        service = TaskDistributionService(session, Role.HEAD_OFFICE.value)
        period = FinancialPeriod(2025)
        service.tasks(period)

        region = service.node((NODE_REGION, unit.id))
        branch_node = service.node((NODE_BRANCH, branch.id))
        department_node = service.node((NODE_DEPARTMENT, str(department.id)))

        assert service.assign([task], region) == 1
        assert service.assign([task], branch_node) == 1
        assert service.is_undistributed(task, branch_node) is True
        assert service.assign([task], department_node) == 1
        session.commit()

        with pytest.raises(TaskDistributionError):
            service.unassign([task], region)

        assert service.is_undistributed(task, region) is False
        assert service.is_undistributed(task, branch_node) is False
        assert service.is_undistributed(task, department_node) is True


def test_branch_cannot_unassign_branch_and_auto_assigns_region(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        unit, branch, department, employee, group = _setup_org(session)
        task = _task()
        session.add(task)
        session.commit()

        service = TaskDistributionService(session, Role.BRANCH.value, branch.id)
        period = FinancialPeriod(2025)
        service.tasks(period)
        region = service.node((NODE_REGION, unit.id))
        branch_node = service.node((NODE_BRANCH, branch.id))

        service.assign([task], branch_node)
        session.commit()

        assert service.is_assigned(task, region.key)
        assert service.is_assigned(task, branch_node.key)
        with pytest.raises(TaskDistributionError):
            service.unassign([task], branch_node)


def test_branch_must_take_task_from_region_before_department(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        unit, branch, department, employee, group = _setup_org(session)
        task = _task()
        session.add(task)
        session.commit()

        service = TaskDistributionService(session, Role.BRANCH.value, branch.id)
        service.tasks(FinancialPeriod(2025))
        department_node = service.node((NODE_DEPARTMENT, str(department.id)))

        with pytest.raises(TaskDistributionError):
            service.assign([task], department_node)


def test_task_service_validates_dates_and_thresholds(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        service = ScientificTaskService(session)
        with pytest.raises(ScientificTaskError):
            service.create_task(
                {
                    "id": "T1",
                    "name": "Задача",
                    "type": ScientificTaskType.MAIN.value,
                    "start_date": date(2026, 2, 1),
                    "end_date": date(2026, 1, 1),
                }
            )
        with pytest.raises(ScientificTaskError):
            service.create_task(
                {
                    "id": "T1",
                    "name": "Задача",
                    "type": ScientificTaskType.MAIN.value,
                    "start_date": date(2026, 1, 1),
                    "partial_threshold": 5,
                    "full_threshold": 2,
                }
            )

        task = service.create_task(
            {
                "id": "T1",
                "name": "Задача",
                "type": ScientificTaskType.MAIN.value,
                "start_date": date(2026, 1, 1),
            }
        )
        assert task.end_date is None


def test_group_membership_depends_on_selected_period(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        unit, branch, department, employee, group = _setup_org(session)
        employee.workgroup_start_date = date(2025, 1, 1)
        employee.workgroup_end_date = date(2025, 12, 31)
        session.commit()

        service = TaskDistributionService(session, Role.HEAD_OFFICE.value)
        group_key = (NODE_WORKGROUP, str(group.id))

        service.build_tree(FinancialPeriod(2024))
        assert service.node(group_key) is not None
        assert len(service.node(group_key).children) == 1

        service.build_tree(FinancialPeriod(2026))
        assert service.node(group_key) is not None
        assert service.node(group_key).children == []


def test_assignment_survives_export_and_import(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    with db_manager.get_session() as session:
        unit, branch, department, employee, group = _setup_org(session)
        task = _task()
        session.add(task)
        session.add(
            AddedTask(task_id=task.id, node_type=NODE_REGION, node_id=unit.id)
        )
        session.commit()

        archive = ExportService(session, storage).export()
        session.commit()

    target = DatabaseManager(f"sqlite:///{tmp_path / 'target.db'}")
    target.create_tables()
    try:
        with target.get_session() as session:
            result = ImportService(
                session, storage, Role.HEAD_OFFICE.value
            ).import_archive(archive)
            session.commit()
            assert result["conflicts"] == []
            assert session.query(AddedTask).count() == 1
    finally:
        target.close()
