"""Тесты диалога ОШС: видимость по ролям, два дерева, операции."""

import os
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QMessageBox

from internal_correspondence.core.constants import Role, ScientificTaskType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.oshm_dialog import OSHMDialog
from internal_correspondence.gui.employee_picker import EmployeePickerDialog
from internal_correspondence.orm.models import (
    Branch,
    Department,
    Employee,
    ScientificTask,
    TerritorialUnit,
    WorkGroupMembership,
    WorkingGroup,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.utils.string_resources import STRINGS


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'oshm.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="function")
def oshm_data(db_manager: DatabaseManager) -> dict:
    """Два филиала; в F1: активный отдел (2 сотрудника + группа) и сокращённый."""
    session = db_manager.get_session()
    session.add(TerritorialUnit(id="TU", name="Единица"))
    session.add(Branch(id="F1", name="Филиал 1", short_name="Ф1", territorial_unit_id="TU"))
    session.add(Branch(id="F2", name="Филиал 2", short_name="Ф2", territorial_unit_id="TU"))
    session.flush()

    dept_a = Department(name="Отдел А", branch_id="F1", active=True)
    dept_b = Department(name="Отдел Б", branch_id="F1", active=False)
    dept_f2 = Department(name="Отдел Ф2", branch_id="F2", active=True)
    session.add_all([dept_a, dept_b, dept_f2])
    session.flush()

    workgroup = WorkingGroup(name="Группа 1", department_id=dept_a.id, active=True)
    session.add(workgroup)
    session.flush()

    emp1 = Employee(
        last_name="Иванов", first_name="Иван", department_id=dept_a.id,
        workgroup_memberships=[WorkGroupMembership(working_group=workgroup)],
        active=True,
    )
    emp2 = Employee(
        last_name="Петров", first_name="Пётр", department_id=dept_a.id, active=False
    )
    emp3 = Employee(
        last_name="Сидоров", first_name="Сидор", department_id=dept_b.id, active=True
    )
    session.add_all([emp1, emp2, emp3])
    session.flush()

    task1 = ScientificTask(
        id="T1", name="Задача 1", type=ScientificTaskType.MAIN, start_date=date(2024, 1, 1)
    )
    task2 = ScientificTask(
        id="T2", name="Задача 2", type=ScientificTaskType.ADDITIONAL, start_date=date(2024, 2, 1)
    )
    session.add_all([task1, task2])
    session.flush()
    emp1.tasks.append(task1)
    session.commit()
    return {
        "dept_a": dept_a, "dept_b": dept_b, "workgroup": workgroup,
        "emp1": emp1, "emp2": emp2, "emp3": emp3,
        "task1": task1, "task2": task2,
    }


def _walk(item):
    """Обходит дерево и возвращает список (текст, полезная нагрузка, элемент)."""
    result = []
    for index in range(item.childCount()):
        child = item.child(index)
        result.append((child.text(0), child.data(0, 1 << 8), child))
        result.extend(_walk(child))
    return result


def _tree_nodes(tree):
    root = tree.topLevelItem(0)
    return [(root.text(0), root.data(0, 1 << 8), root)] + _walk(root)


def test_head_office_sees_all_branches(qt_app, db_manager, oshm_data) -> None:
    """Головной офис: корень «Головной офис», внутри все филиалы."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id=None, role=Role.HEAD_OFFICE.value
    )
    for tree in (dialog.tree_structure, dialog.tree_workgroups):
        root = tree.topLevelItem(0)
        assert root.data(0, 1 << 8) == ("head_office", "")
        assert root.text(0) == STRINGS.role_head_office
        branch_ids = {
            payload[1]
            for _text, payload, _item in _walk(root)
            if payload[0] == "branch"
        }
        assert branch_ids == {"F1", "F2"}
    # Структуру редактировать можно, людей — нельзя
    assert not dialog.can_edit_people
    assert dialog.add_btn.isEnabled()
    assert dialog.toggle_btn.isEnabled()
    dialog.deleteLater()


def test_head_office_cannot_modify_employees(
    qt_app, db_manager, oshm_data, monkeypatch
) -> None:
    """ГО не скрывает, не удаляет и не перетаскивает сотрудников."""
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id=None, role=Role.HEAD_OFFICE.value
    )
    emp2 = oshm_data["emp2"]  # изначально неактивен
    item = next(
        item
        for _t, payload, item in _tree_nodes(dialog.tree_structure)
        if payload == ("employee", str(emp2.id))
    )
    dialog.tree_structure.setCurrentItem(item)
    dialog._activate_tree(dialog.tree_structure)
    dialog._toggle_selected()
    dialog._delete_selected()

    session = db_manager.get_session()
    emp = session.get(Employee, emp2.id)
    assert emp is not None
    assert emp.active is False  # не изменился

    # Drag&drop сотрудника головным офисом игнорируется
    emp1, dept_b = oshm_data["emp1"], oshm_data["dept_b"]
    dialog._on_nodes_dropped(
        dialog.tree_structure,
        [("employee", str(emp1.id))],
        ("department", str(dept_b.id)),
    )
    assert session.get(Employee, emp1.id).department_id == oshm_data["dept_a"].id
    dialog.deleteLater()


def test_head_office_can_modify_structure(qt_app, db_manager, oshm_data) -> None:
    """ГО скрывает отделы и рабочие группы."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id=None, role=Role.HEAD_OFFICE.value
    )
    dept_a = oshm_data["dept_a"]
    item = next(
        item
        for _t, payload, item in _tree_nodes(dialog.tree_structure)
        if payload == ("department", str(dept_a.id))
    )
    dialog.tree_structure.setCurrentItem(item)
    dialog._activate_tree(dialog.tree_structure)
    dialog._toggle_selected()

    dept = db_manager.get_session().get(Department, dept_a.id)
    assert dept.active is False
    dialog.deleteLater()


def test_head_office_branch_id_for_add(qt_app, db_manager, oshm_data) -> None:
    """ГО добавляет отдел в выбранный филиал; на корне ГО филиал не определён."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id=None, role=Role.HEAD_OFFICE.value
    )
    root = dialog.tree_structure.topLevelItem(0)
    branch_item = next(
        item
        for _t, payload, item in _walk(root)
        if payload == ("branch", "F2")
    )
    dialog.tree_structure.setCurrentItem(branch_item)
    dialog._activate_tree(dialog.tree_structure)
    assert dialog._branch_id_for_add() == "F2"

    dialog.tree_structure.setCurrentItem(root)
    assert dialog._branch_id_for_add() is None
    dialog.deleteLater()


def test_branch_sees_only_itself(qt_app, db_manager, oshm_data) -> None:
    """Филиал: корень — его собственный узел, чужих филиалов нет."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    for tree in (dialog.tree_structure, dialog.tree_workgroups):
        root = tree.topLevelItem(0)
        assert root.data(0, 1 << 8) == ("branch", "F1")
        all_payloads = [payload for _t, payload, _i in _walk(root)]
        assert all(
            not (payload[0] == "branch" and payload[1] != "F1")
            for payload in all_payloads
        )
        assert "head_office" not in [payload[0] for payload in all_payloads]
    assert dialog.can_edit_people
    assert dialog.add_btn.isEnabled()
    dialog.deleteLater()


def test_two_trees_structure(qt_app, db_manager, oshm_data) -> None:
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    structure = _tree_nodes(dialog.tree_structure)
    workgroups = _tree_nodes(dialog.tree_workgroups)

    structure_types = [payload[0] for _text, payload, _item in structure]
    workgroup_types = [payload[0] for _text, payload, _item in workgroups]

    # Штатная структура: филиал, отделы, сотрудники — без рабочих групп
    assert "workgroup" not in structure_types
    assert structure_types.count("department") == 2
    assert structure_types.count("employee") == 3

    # Рабочие группы: полная иерархия филиал → отдел → группа → состав
    assert workgroup_types.count("department") == 2
    assert workgroup_types.count("workgroup") == 1
    # В группе один участник (Иванов)
    assert workgroup_types.count("employee") == 1
    dialog.deleteLater()


def test_inactive_display(qt_app, db_manager, oshm_data) -> None:
    """Неактивные элементы серые; сотрудник сокращённого отдела — тоже."""
    inactive_color = QColor(150, 150, 150)
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    nodes = _tree_nodes(dialog.tree_structure)
    by_text = {text: item for text, _payload, item in nodes}

    dept_b = by_text["Отдел Б"]
    assert dept_b.foreground(0).color() == inactive_color

    # Сидоров активен сам, но его отдел сокращён — отображается неактивным
    emp3 = by_text[[t for t in by_text if t.startswith("Сидоров")][0]]
    assert emp3.foreground(0).color() == inactive_color

    # Активный сотрудник активного отдела — обычного цвета
    emp1 = by_text[[t for t in by_text if t.startswith("Иванов")][0]]
    assert emp1.foreground(0).color() != inactive_color
    dialog.deleteLater()


def test_toggle_selected(qt_app, db_manager, oshm_data) -> None:
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    nodes = _tree_nodes(dialog.tree_structure)
    dept_item = next(item for text, _p, item in nodes if _p[0] == "department" and text == "Отдел А")
    dialog.tree_structure.setCurrentItem(dept_item)
    dialog._activate_tree(dialog.tree_structure)
    dialog._toggle_selected()

    dept = db_manager.get_session().get(Department, oshm_data["dept_a"].id)
    assert dept.active is False
    dialog.deleteLater()


def test_drop_employee_to_department(qt_app, db_manager, oshm_data) -> None:
    """Перенос сотрудника на отдел в дереве структуры меняет его отдел."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    emp1 = oshm_data["emp1"]
    dept_b = oshm_data["dept_b"]
    dialog._on_nodes_dropped(
        dialog.tree_structure,
        [("employee", str(emp1.id))],
        ("department", str(dept_b.id)),
    )
    moved = db_manager.get_session().get(Employee, emp1.id)
    assert moved.department_id == dept_b.id
    dialog.deleteLater()


def test_drop_employee_to_workgroup(qt_app, db_manager, oshm_data) -> None:
    """Перенос сотрудника на группу в дереве групп включает его в состав."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    emp3 = oshm_data["emp3"]
    workgroup = oshm_data["workgroup"]
    dialog._on_nodes_dropped(
        dialog.tree_workgroups,
        [("employee", str(emp3.id))],
        ("workgroup", str(workgroup.id)),
    )
    moved = db_manager.get_session().get(Employee, emp3.id)
    assert moved.current_membership is not None
    assert moved.current_membership.working_group_id == workgroup.id
    dialog.deleteLater()


def test_drop_ignores_wrong_target(qt_app, db_manager, oshm_data) -> None:
    """Перенос сотрудника на недопустимую цель ничего не меняет."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    emp1 = oshm_data["emp1"]
    dialog._on_nodes_dropped(
        dialog.tree_structure,
        [("employee", str(emp1.id))],
        ("employee", "whatever"),
    )
    unchanged = db_manager.get_session().get(Employee, emp1.id)
    assert unchanged.department_id == oshm_data["dept_a"].id
    dialog.deleteLater()


def test_delete_selected_multiple(qt_app, db_manager, oshm_data, monkeypatch) -> None:
    """Групповое удаление выбранных элементов после подтверждения."""
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    emp2, emp3 = oshm_data["emp2"], oshm_data["emp3"]
    items = [
        item
        for _text, payload, item in _tree_nodes(dialog.tree_structure)
        if payload[0] == "employee" and payload[1] in (str(emp2.id), str(emp3.id))
    ]
    assert len(items) == 2
    for item in items:
        item.setSelected(True)
    dialog._activate_tree(dialog.tree_structure)
    dialog._delete_selected()

    session = db_manager.get_session()
    assert session.get(Employee, emp2.id) is None
    assert session.get(Employee, emp3.id) is None
    dialog.deleteLater()


def test_employee_picker_excludes_inactive(qt_app, db_manager, oshm_data) -> None:
    """В выборе сотрудников нет неактивных и сотрудников сокращённых отделов."""
    dialog = EmployeePickerDialog(db_manager.get_session(), "F1")
    last_names = {employee.last_name for employee in dialog._employees}
    assert last_names == {"Иванов"}
    dialog.deleteLater()


# ----------------------------------------------------------------------
# Панель сведений об элементе
# ----------------------------------------------------------------------


def _find_node(dialog, tree, payload):
    """Находит элемент дерева по полезной нагрузке."""
    return next(
        item for _t, p, item in _tree_nodes(tree) if p == payload
    )


def test_details_panel_employee(qt_app, db_manager, oshm_data) -> None:
    """Двойной щелчок по сотруднику открывает панель с данными и задачами."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    emp1 = oshm_data["emp1"]
    item = _find_node(dialog, dialog.tree_structure, ("employee", str(emp1.id)))
    dialog._show_details(item, dialog.tree_structure)

    panel = dialog.details_panel
    assert not panel.isHidden()
    assert panel.title_label.text() == emp1.display_name()
    assert not panel.tasks_group.isHidden()
    assert panel.tasks_table.rowCount() == 1
    assert panel.tasks_table.item(0, 0).text() == "T1"
    assert panel.edit_btn.isEnabled()
    dialog.deleteLater()


def test_details_panel_department_without_tasks(qt_app, db_manager, oshm_data) -> None:
    """У отдела нет таблицы задач; «Изменить» доступно и головному офису."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id=None, role=Role.HEAD_OFFICE.value
    )
    dept_a = oshm_data["dept_a"]
    item = _find_node(dialog, dialog.tree_structure, ("department", str(dept_a.id)))
    dialog._show_details(item, dialog.tree_structure)

    panel = dialog.details_panel
    assert not panel.isHidden()
    assert panel.title_label.text() == "Отдел А"
    assert panel.tasks_group.isHidden()
    assert panel.edit_btn.isEnabled()
    dialog.deleteLater()


def test_details_panel_head_office_employee_read_only(
    qt_app, db_manager, oshm_data
) -> None:
    """ГО видит данные сотрудника, но «Изменить» и кнопки задач недоступны."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id=None, role=Role.HEAD_OFFICE.value
    )
    emp1 = oshm_data["emp1"]
    item = _find_node(dialog, dialog.tree_structure, ("employee", str(emp1.id)))
    dialog._show_details(item, dialog.tree_structure)

    panel = dialog.details_panel
    assert not panel.isHidden()
    assert not panel.tasks_group.isHidden()
    assert not panel.edit_btn.isEnabled()
    assert not panel.task_add_btn.isEnabled()
    assert not panel.task_remove_btn.isEnabled()
    dialog.deleteLater()


def test_details_panel_hide_button(qt_app, db_manager, oshm_data) -> None:
    """Кнопка «Скрыть» закрывает панель сведений."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    dept_a = oshm_data["dept_a"]
    item = _find_node(dialog, dialog.tree_structure, ("department", str(dept_a.id)))
    dialog._show_details(item, dialog.tree_structure)
    assert not dialog.details_panel.isHidden()

    dialog.details_panel.hide_btn.click()
    assert dialog.details_panel.isHidden()
    dialog.deleteLater()


def test_details_panel_remove_task(qt_app, db_manager, oshm_data) -> None:
    """Снятие назначения задачи через панель сведений."""
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    emp1 = oshm_data["emp1"]
    item = _find_node(dialog, dialog.tree_structure, ("employee", str(emp1.id)))
    dialog._show_details(item, dialog.tree_structure)

    panel = dialog.details_panel
    panel.tasks_table.selectRow(0)
    panel._remove_tasks()

    session = db_manager.get_session()
    assert session.get(Employee, emp1.id).tasks == []
    assert panel.tasks_table.rowCount() == 0
    dialog.deleteLater()


def test_details_panel_hidden_after_delete(
    qt_app, db_manager, oshm_data, monkeypatch
) -> None:
    """Удаление элемента скрывает открытую по нему панель."""
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    dialog = OSHMDialog(
        db_manager.get_session(), branch_id="F1", role=Role.BRANCH.value
    )
    emp2 = oshm_data["emp2"]
    item = _find_node(dialog, dialog.tree_structure, ("employee", str(emp2.id)))
    dialog._show_details(item, dialog.tree_structure)
    assert not dialog.details_panel.isHidden()

    item.setSelected(True)
    dialog._activate_tree(dialog.tree_structure)
    dialog._delete_selected()

    assert dialog.details_panel.isHidden()
    dialog.deleteLater()
