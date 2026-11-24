"""Дымовые тесты вкладки распределения задач."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from internal_correspondence.core.constants import Role, ScientificTaskType
from internal_correspondence.core.database import DatabaseManager
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
    session.add_all([unit, branch])
    session.flush()
    department = Department(name="Отдел 1", branch_id=branch.id)
    session.add(department)
    session.flush()
    employee = Employee(
        last_name="Иванов", first_name="Иван", department_id=department.id
    )
    group = WorkingGroup(name="Группа 1", department_id=department.id)
    session.add_all([employee, group])
    session.flush()
    employee.assign_working_group(group, start_date=date(2025, 1, 1))
    task = ScientificTask(
        id="T1",
        name="Задача 1",
        type=ScientificTaskType.MAIN.value,
        start_date=date(2026, 1, 10),
    )
    session.add(task)
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
            from PyQt5.QtWidgets import QHeaderView

            header = widget.middle_view.horizontalHeader()
            assert header.sectionResizeMode(1) == QHeaderView.Interactive
            assert header.sectionResizeMode(2) == QHeaderView.Interactive
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


def test_task_model_search_by_type_label(
    qt_app, db_manager: DatabaseManager
) -> None:
    """Поиск по типу задачи работает и для IntEnum-значений."""
    from internal_correspondence.gui.task_table_model import TaskTableModel

    with db_manager.get_session() as session:
        _setup_data(session)
        session.add(
            ScientificTask(
                id="T2",
                name="Дополнительная задача",
                type=ScientificTaskType.ADDITIONAL,
                start_date=date(2026, 2, 1),
            )
        )
        session.commit()
        tasks = session.query(ScientificTask).order_by(ScientificTask.id).all()
        model = TaskTableModel()
        model.set_tasks(tasks)

        model.set_search("дополнительная")
        assert model.rowCount() == 1
        assert model.task_at(0).id == "T2"

        model.set_search("основная")
        assert model.rowCount() == 1
        assert model.task_at(0).id == "T1"

        model.set_search("дз")
        assert model.rowCount() == 1
        assert model.task_at(0).id == "T2"

        model.set_search("оз")
        assert model.rowCount() == 1
        assert model.task_at(0).id == "T1"


def test_task_model_shows_type_column(qt_app, db_manager: DatabaseManager) -> None:
    """Колонка «Тип» заполняется меткой, а не остаётся пустой."""
    from PyQt5.QtCore import Qt

    from internal_correspondence.gui.task_table_model import TaskTableModel

    with db_manager.get_session() as session:
        _setup_data(session)
        task = session.query(ScientificTask).one()
        model = TaskTableModel()
        model.set_tasks([task])
        assert model.data(model.index(0, 2), Qt.DisplayRole) == "ОЗ"


def test_distributed_toggle_filters_distributed_tasks(
    qt_app, db_manager: DatabaseManager
) -> None:
    """Кнопка скрывает задачи, уже распределённые нижестоящим элементам."""
    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )
    from internal_correspondence.services.task_distribution_service import (
        NODE_BRANCH,
        NODE_REGION,
    )

    with db_manager.get_session() as session:
        _setup_data(session)
        task2 = ScientificTask(
            id="T2",
            name="Задача 2",
            type=ScientificTaskType.ADDITIONAL,
            start_date=date(2026, 2, 1),
        )
        session.add(task2)
        session.commit()

        widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        try:
            region = widget.service.node((NODE_REGION, "MSK"))
            branch = widget.service.node((NODE_BRANCH, "BR1"))
            assert region is not None and branch is not None
            widget.service.assign([task2], region)
            widget.service.assign([task2], branch)
            session.commit()
            widget.refresh_all()

            region_item = widget.tree.topLevelItem(0).child(0)
            widget.tree.setCurrentItem(region_item)
            assert widget.middle_model.rowCount() == 2
            assert widget.right_model.rowCount() == 1

            widget.distributed_button.setChecked(True)
            assert widget.middle_model.rowCount() == 1
            assert widget.middle_model.task_at(0).id == "T1"
            assert widget.right_model.rowCount() == 0
            assert widget.distributed_button.text() == "Показать распределённые"

            widget.distributed_button.setChecked(False)
            assert widget.middle_model.rowCount() == 2
            assert widget.right_model.rowCount() == 1
        finally:
            widget.deleteLater()

def _setup_two_departments(session):
    from internal_correspondence.orm.models import AddedTask
    from internal_correspondence.services.task_distribution_service import (
        NODE_BRANCH,
        NODE_REGION,
        TaskDistributionService,
    )

    unit = TerritorialUnit(id="MSK2", name="Москва 2")
    branch = Branch(
        id="BR2", name="Филиал 2", short_name="Ф-2", territorial_unit_id="MSK2"
    )
    session.add_all([unit, branch])
    session.flush()
    first = Department(name="Отдел А", branch_id=branch.id)
    second = Department(name="Отдел Б", branch_id=branch.id)
    session.add_all([first, second])
    session.flush()
    task = ScientificTask(
        id="T2",
        name="Задача 2",
        type=ScientificTaskType.MAIN.value,
        start_date=date(2026, 2, 1),
    )
    session.add(task)
    session.commit()

    service = TaskDistributionService(session, Role.HEAD_OFFICE.value)
    service.assign([task], service.node((NODE_REGION, unit.id)))
    service.assign([task], service.node((NODE_BRANCH, branch.id)))
    session.commit()
    return first, second, task


def test_tree_multi_selection_assigns_to_all_and_right_shows_first(
    qt_app, db_manager: DatabaseManager
) -> None:
    from PyQt5.QtCore import QItemSelectionModel

    from internal_correspondence.orm.models import AddedTask
    from internal_correspondence.services.task_distribution_service import (
        NODE_DEPARTMENT,
    )
    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        first, second, task = _setup_two_departments(session)
        widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        try:
            tree = widget.tree
            first_item = widget._item_for_key((NODE_DEPARTMENT, str(first.id)))
            second_item = widget._item_for_key((NODE_DEPARTMENT, str(second.id)))
            assert first_item is not None and second_item is not None

            first_item.setSelected(True)
            tree.setCurrentItem(first_item)
            second_item.setSelected(True)
            tree.selectionModel().setCurrentIndex(
                tree.indexFromItem(second_item),
                QItemSelectionModel.NoUpdate,
            )

            assert widget.selected_keys() == [
                (NODE_DEPARTMENT, str(first.id)),
                (NODE_DEPARTMENT, str(second.id)),
            ]
            assert widget.current_key() == (NODE_DEPARTMENT, str(first.id))
            # Правая таблица показывает задачи ведущего (первого) узла.
            assert widget.right_model.rowCount() == 0
            assert widget.middle_model.rowCount() == 1

            widget.middle_view.selectRow(0)
            assert widget.assign_button.isEnabled() is True
            widget._assign_tasks(widget.middle_model.tasks_at([0]))

            rows = (
                session.query(AddedTask)
                .filter(AddedTask.task_id == task.id)
                .filter(AddedTask.node_type == NODE_DEPARTMENT)
                .all()
            )
            assert {row.node_id for row in rows} == {
                str(first.id),
                str(second.id),
            }
            assert widget.right_model.rowCount() == 1
            assert widget.right_model.task_at(0).id == task.id
        finally:
            widget.deleteLater()

def test_branch_distribution_export(qt_app, db_manager: DatabaseManager, tmp_path: Path) -> None:
    from openpyxl import load_workbook

    from internal_correspondence.importexport.task_export import (
        DISTRIBUTION_HEADERS,
        write_branch_distribution,
    )
    from internal_correspondence.services.task_distribution_service import (
        FinancialPeriod,
    )

    with db_manager.get_session() as session:
        _setup_data(session)
        branch = session.query(Branch).one()
        first = session.query(Department).one()
        second = Department(name="Отдел 2", branch_id=branch.id)
        session.add(second)
        session.flush()
        employee1 = session.query(Employee).one()
        employee2 = Employee(
            last_name="Петров", first_name="Пётр", department_id=second.id
        )
        session.add(employee2)
        session.flush()
        task = session.query(ScientificTask).one()
        extra = ScientificTask(
            id="T2",
            name="Задача 2",
            type=ScientificTaskType.ADDITIONAL.value,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 3, 1),
        )
        session.add(extra)
        session.flush()
        session.add_all(
            [
                AddedTask(task_id=task.id, node_type="branch", node_id=branch.id),
                AddedTask(
                    task_id=task.id, node_type="department", node_id=str(first.id)
                ),
                AddedTask(
                    task_id=task.id, node_type="department", node_id=str(second.id)
                ),
                AddedTask(
                    task_id=task.id, node_type="employee", node_id=str(employee1.id)
                ),
                AddedTask(
                    task_id=task.id, node_type="employee", node_id=str(employee2.id)
                ),
            ]
        )
        session.commit()

        path = tmp_path / "distribution.xlsx"
        count = write_branch_distribution(
            session, branch.id, FinancialPeriod(2026), path
        )
        assert count == 2

        sheet = load_workbook(path).active
        assert [cell.value for cell in sheet[1]] == DISTRIBUTION_HEADERS
        assert sheet.cell(2, 2).value == "T1"
        assert sheet.cell(2, 6).value == "Отдел 1"
        assert sheet.cell(2, 7).value == "Иванов И."
        assert sheet.cell(3, 6).value == "Отдел 2"
        assert sheet.cell(3, 7).value == "Петров П."


def test_branch_has_save_button_instead_of_export(
    qt_app, db_manager: DatabaseManager
) -> None:
    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        _setup_data(session)
        branch_widget = TaskDistributionWidget(session, Role.BRANCH.value, "BR1")
        branch_widget.show()
        try:
            assert not branch_widget.save_distribution_button.isHidden()
            assert branch_widget.export_button.isHidden()
        finally:
            branch_widget.deleteLater()

        office_widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        office_widget.show()
        try:
            assert office_widget.save_distribution_button.isHidden()
            assert not office_widget.export_button.isHidden()
        finally:
            office_widget.deleteLater()


def _setup_management_data(session):
    """Задачи с назначениями по уровням и двумя документами."""
    from uuid import uuid4

    from internal_correspondence.core.constants import MaterialType
    from internal_correspondence.orm.models import (
        ScientificMaterial,
        material_task_association,
        telegram_task_association,
    )

    _setup_data(session)
    branch = session.query(Branch).one()
    department = session.query(Department).one()
    employee = session.query(Employee).one()
    task = session.query(ScientificTask).one()
    task.full_threshold = 10
    task.partial_threshold = 5
    task.comment = "примечание"
    session.add_all(
        [
            AddedTask(task_id=task.id, node_type="region", node_id="MSK"),
            AddedTask(task_id=task.id, node_type="branch", node_id=branch.id),
            AddedTask(
                task_id=task.id,
                node_type="department",
                node_id=str(department.id),
            ),
            AddedTask(
                task_id=task.id, node_type="employee", node_id=str(employee.id)
            ),
        ]
    )
    material = ScientificMaterial(
        id=uuid4(),
        name="Материал 1",
        branch_id=branch.id,
        type=MaterialType.DOCUMENT.value,
        outgoing_date=date(2026, 1, 5),
    )
    session.add(material)
    session.flush()
    session.execute(
        material_task_association.insert().values(
            material_id=material.id, task_id=task.id
        )
    )
    session.commit()
    return branch, department, employee, task


def test_management_mode_hides_distribution_panel(
    qt_app, db_manager: DatabaseManager
) -> None:
    """Кнопка «Управление задачами» скрывает распределение и показывает таблицу."""
    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        _setup_management_data(session)
        widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        view = widget.management_widget
        try:
            assert widget.manage_button.isChecked() is False
            assert widget.is_management_mode() is False
            assert widget.stack.currentWidget() is widget.distribution_page
            # Кнопка режима подсвечена темой как основная
            assert widget.manage_button.property("role") == "primary"

            widget.manage_button.setChecked(True)
            assert widget.is_management_mode() is True
            assert widget.stack.currentWidget() is view
            assert widget.distributed_button.isHidden() is True
            # Дерево и обе таблицы распределения скрыты вместе со страницей
            assert widget.distribution_page.isHidden() is True
            assert view.table_model.rowCount() == 1

            widget.set_management_mode(False)
            assert widget.is_management_mode() is False
            assert widget.distributed_button.isHidden() is False
        finally:
            widget.deleteLater()


def test_management_table_shows_assignments_for_head_office(
    qt_app, db_manager: DatabaseManager
) -> None:
    """Головной офис видит назначения регионам и филиалам, процент и примечание."""
    from PyQt5.QtCore import Qt

    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        _setup_management_data(session)
        widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        widget.set_management_mode(True)
        model = widget.management_widget.table_model
        headers = [
            model.headerData(index, Qt.Horizontal, Qt.DisplayRole)
            for index in range(model.columnCount())
        ]
        try:
            assert headers == [
                "Код задачи",
                "Наименование",
                "Тип",
                "Назначено регионам",
                "Назначено филиалам",
                "% процент выполнения",
                "Частичное решение",
                "Полное решение",
                "Начало",
                "Окончание",
                "Примечание",
            ]
            values = {
                header: model.data(model.index(0, column), Qt.DisplayRole)
                for column, header in enumerate(headers)
            }
            assert values["Код задачи"] == "T1"
            assert values["Тип"] == "ОЗ"
            assert values["Назначено регионам"] == "Москва"
            assert values["Назначено филиалам"] == "Ф-1"
            assert values["% процент выполнения"] == "10%"
            assert values["Частичное решение"] == "5,00"
            assert values["Полное решение"] == "10,00"
            assert values["Начало"] == "10.01.2026"
            assert values["Окончание"] == ""
            assert values["Примечание"] == "примечание"
        finally:
            widget.deleteLater()


def test_management_table_shows_assignments_for_branch(
    qt_app, db_manager: DatabaseManager
) -> None:
    """Филиал видит назначения своим отделам и исполнителям."""
    from PyQt5.QtCore import Qt

    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        _setup_management_data(session)
        widget = TaskDistributionWidget(session, Role.BRANCH.value, "BR1")
        widget.set_management_mode(True)
        model = widget.management_widget.table_model
        headers = [
            model.headerData(index, Qt.Horizontal, Qt.DisplayRole)
            for index in range(model.columnCount())
        ]
        try:
            assert "Назначено отделам" in headers
            assert "Назначено исполнителям" in headers
            assert "Назначено регионам" not in headers
            values = {
                header: model.data(model.index(0, column), Qt.DisplayRole)
                for column, header in enumerate(headers)
            }
            assert values["Назначено отделам"] == "Отдел 1"
            assert values["Назначено исполнителям"] == "Иванов И."
            assert values["% процент выполнения"] == "10%"
        finally:
            widget.deleteLater()


def test_management_table_search_and_sort(
    qt_app, db_manager: DatabaseManager
) -> None:
    """Поиск и сортировка работают по вычисляемым колонкам."""
    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        _setup_management_data(session)
        session.add(
            ScientificTask(
                id="T2",
                name="Задача 2",
                type=ScientificTaskType.ADDITIONAL.value,
                start_date=date(2026, 2, 1),
                full_threshold=2,
            )
        )
        session.commit()
        widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        widget.set_management_mode(True)
        view = widget.management_widget
        try:
            assert view.table_model.rowCount() == 2
            view.search_edit.setText("задача 2")
            assert view.table_model.rowCount() == 1
            assert view.table_model.task_at(0).id == "T2"

            view.search_edit.setText("москва")
            assert view.table_model.task_at(0).id == "T1"

            view.search_edit.clear()
            assert view.set_sort_state("progress", True) is True
            assert view.sort_state() == ("progress", True)
            assert view.table_model.task_at(0).id == "T1"
        finally:
            widget.deleteLater()


def test_management_table_columns_layout_roundtrip(
    qt_app, db_manager: DatabaseManager
) -> None:
    """Раскладка колонок сохраняется и восстанавливается."""
    from internal_correspondence.gui.task_distribution_widget import (
        TaskDistributionWidget,
    )

    with db_manager.get_session() as session:
        _setup_management_data(session)
        widget = TaskDistributionWidget(session, Role.HEAD_OFFICE.value)
        view = widget.management_widget
        try:
            layout = view.columns_layout()
            assert "id:" in layout and "comment:" in layout
            view.set_columns_layout("name:300:1,id:90:0")
            changed = view.columns_layout()
            assert "name:300:1" in changed
            assert "id:90:0" in changed
        finally:
            widget.deleteLater()
