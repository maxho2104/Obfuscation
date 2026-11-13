"""Дымовые тесты вкладки распределения задач."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from internal_correspondence.core.constants import Role, ScientificTaskType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    Branch,
    Department,
    Employee,
    ScientificTask,
    TerritorialUnit,
    WorkingGroup,
)
from internal_correspondence.services.change_tracking import register_change_tracking


@pytest.fixture(scope="module")
def qt_app():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'widget.db'}")
    db.create_tables()
    yield db
    db.close()


def _setup_data(session):
    unit = TerritorialUnit(id="MSK", name="Москва")
    branch = Branch(
        id="BR1", name="Филиал 1", short_name="Ф-1", territorial_unit_id="MSK"
    )
    department = Department(name="Отдел 1", branch=branch)
    employee = Employee(
        last_name="Иванов", first_name="Иван", department=department
    )
    group = WorkingGroup(name="Группа 1", department=department)
    employee.working_group = group
    task = ScientificTask(
        id="T1",
        name="Задача 1",
        type=ScientificTaskType.MAIN.value,
        start_date=date(2026, 1, 10),
    )
    session.add_all([unit, branch, department, employee, group, task])
    session.commit()


def test_widget_builds_tree_and_tables(qt_app, db_manager: DatabaseManager) -> None:
    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        _setup_data(session)
        widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        try:
            assert widget.tree.topLevelItemCount() == 1
            assert widget.period_combo.count() >= 1
            assert widget.middle_model.rowCount() >= 0
            widget.refresh_all()
        finally:
            widget.deleteLater()


def test_buttons_pane_has_fixed_width(qt_app, db_manager: DatabaseManager) -> None:
    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        _setup_data(session)
        widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        try:
            buttons = widget.buttons_panel
            assert buttons.minimumWidth() == 52
            assert buttons.maximumWidth() == 52
            # Кнопки входят в центральную панель, а не в QSplitter.
            assert widget.splitter.count() == 3
            assert widget.splitter.isCollapsible(1) is False
        finally:
            widget.deleteLater()


def test_task_model_provides_drag_mime_data(qt_app, db_manager: DatabaseManager) -> None:
    from PyQt5.QtCore import QModelIndex

    from internal_correspondence.gui.task_table_model import (
        TASK_MIME_TYPE,
        TaskTableModel,
    )

    with db_manager.get_session() as session:
        _setup_data(session)
        task = session.query(ScientificTask).one()
        model = TaskTableModel()
        model.set_tasks([task])

        mime = model.mimeData([model.index(0, 0)])
        assert mime is not None
        assert mime.hasFormat(TASK_MIME_TYPE)
        assert bytes(mime.data(TASK_MIME_TYPE)).decode("utf-8") == "T1"
        assert model.mimeTypes() == [TASK_MIME_TYPE]

        invalid = model.mimeData([QModelIndex()])
        assert invalid is None
