"""Панель сведений об элементе ОШС.

Выдвигается справа в диалоге ОШС по двойному щелчку на элементе дерева:
показывает все данные элемента, для сотрудника — таблицу назначенных
научных задач с возможностью добавлять и снимать назначения. Кнопки:
«Скрыть» (закрывает панель), «Изменить» (окно редактирования элемента),
«Статистика» (запрашивает у приложения статистику по элементу).
"""

from typing import List, Optional, Tuple
from uuid import UUID

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.labels import field_label, field_short_label
from internal_correspondence.orm.models import (
    Branch,
    Department,
    Employee,
    ScientificTask,
    WorkGroupMembership,
    WorkingGroup,
)
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("oshm_details_panel")

# Полезная нагрузка узла дерева: (тип узла, строковый идентификатор)
NodeRef = Tuple[str, str]

# Отображение пустого значения
EMPTY = "—"


def _date_text(value) -> str:
    """Форматирует дату для показа на панели."""
    return value.strftime("%d.%m.%Y") if value is not None else EMPTY


def _bool_text(value: bool) -> str:
    """Форматирует признак активности для показа на панели."""
    return STRINGS.value_yes if value else STRINGS.value_no


class TaskPickerDialog(QDialog):
    """Диалог выбора научных задач, ещё не назначенных сотруднику."""

    def __init__(
        self, session, excluded_ids: Optional[List[str]] = None, parent=None
    ) -> None:
        super().__init__(parent)
        self.session = session
        self._excluded_ids = set(excluded_ids or [])
        self._tasks: List[ScientificTask] = []
        self.setWindowTitle(STRINGS.picker_tasks_title)
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._load_tasks()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list_widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_tasks(self) -> None:
        query = self.session.query(ScientificTask).order_by(ScientificTask.name)
        if self._excluded_ids:
            query = query.filter(ScientificTask.id.notin_(list(self._excluded_ids)))
        self._tasks = query.all()
        self.list_widget.clear()
        for task in self._tasks:
            item = QListWidgetItem(f"{task.id} — {task.name}")
            item.setData(Qt.UserRole, task.id)
            self.list_widget.addItem(item)

    def selected_tasks(self) -> List[ScientificTask]:
        """Возвращает задачи, выбранные в списке."""
        selected_ids = {
            item.data(Qt.UserRole) for item in self.list_widget.selectedItems()
        }
        return [task for task in self._tasks if task.id in selected_ids]


class ElementDetailsPanel(QWidget):
    """Панель данных элемента ОШС с задачами сотрудника и кнопками действий."""

    hide_requested = pyqtSignal()
    edit_requested = pyqtSignal(tuple)  # NodeRef
    statistics_requested = pyqtSignal(tuple)  # NodeRef

    def __init__(self, session, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.session = session
        self.current_node: Optional[NodeRef] = None
        self._employee: Optional[Employee] = None
        self.setMinimumWidth(340)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.title_label = QLabel()
        title_font = self.title_label.font()
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.fields_layout = QFormLayout()
        layout.addLayout(self.fields_layout)

        # Задачи сотрудника
        self.tasks_group = QGroupBox(STRINGS.oshm_tasks_section)
        tasks_layout = QVBoxLayout(self.tasks_group)
        self.tasks_table = QTableWidget(0, 4)
        self.tasks_table.setHorizontalHeaderLabels(
            [
                field_short_label(ScientificTask, "id"),
                field_short_label(ScientificTask, "name"),
                field_short_label(ScientificTask, "start_date"),
                field_short_label(ScientificTask, "end_date"),
            ]
        )
        self.tasks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tasks_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tasks_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tasks_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tasks_table.verticalHeader().setVisible(False)
        tasks_layout.addWidget(self.tasks_table)

        tasks_buttons = QHBoxLayout()
        self.task_add_btn = QPushButton("+")
        self.task_add_btn.setToolTip(STRINGS.button_add)
        self.task_add_btn.clicked.connect(self._add_tasks)
        self.task_remove_btn = QPushButton("−")
        self.task_remove_btn.setToolTip(STRINGS.button_delete)
        self.task_remove_btn.clicked.connect(self._remove_tasks)
        tasks_buttons.addWidget(self.task_add_btn)
        tasks_buttons.addWidget(self.task_remove_btn)
        tasks_buttons.addStretch()
        tasks_layout.addLayout(tasks_buttons)
        layout.addWidget(self.tasks_group)

        layout.addStretch()

        # Кнопки действий
        buttons_row = QHBoxLayout()
        self.hide_btn = QPushButton(STRINGS.button_hide)
        self.hide_btn.clicked.connect(self.hide_requested.emit)
        self.edit_btn = QPushButton(STRINGS.button_edit)
        self.edit_btn.clicked.connect(self._edit_clicked)
        self.stats_btn = QPushButton(STRINGS.button_statistics)
        self.stats_btn.clicked.connect(self._show_statistics)
        buttons_row.addWidget(self.hide_btn)
        buttons_row.addWidget(self.edit_btn)
        buttons_row.addWidget(self.stats_btn)
        buttons_row.addStretch()
        layout.addLayout(buttons_row)

    # ------------------------------------------------------------------
    # Наполнение данными
    # ------------------------------------------------------------------

    def show_node(self, node: NodeRef, can_edit_people: bool = True) -> bool:
        """Заполняет панель данными узла. False — узел не найден (удалён)."""
        node_type, node_id = node
        loaders = {
            "branch": lambda: self._show_branch(node_id),
            "department": lambda: self._show_department(node_id),
            "workgroup": lambda: self._show_workgroup(node_id),
            "employee": lambda: self._show_employee(node_id),
            "head_office": lambda: self._show_head_office(),
        }
        loader = loaders.get(node_type)
        if loader is None:
            return False
        self._clear_fields()
        self._employee = None
        if not loader():
            return False
        self.current_node = node
        # «Изменить»: людей редактирует только филиал; филиал и корень ГО
        # редактируются в справочниках, а не в этом диалоге
        can_edit = node_type in ("department", "workgroup") or (
            node_type == "employee" and can_edit_people
        )
        self.edit_btn.setEnabled(can_edit)
        self.set_tasks_editable(can_edit_people)
        return True

    def _clear_fields(self) -> None:
        while self.fields_layout.rowCount():
            self.fields_layout.removeRow(0)

    def _add_field(self, label: str, value: Optional[str]) -> None:
        value_label = QLabel(value or EMPTY)
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.fields_layout.addRow(f"{label}:", value_label)

    def _show_head_office(self) -> bool:
        self.title_label.setText(STRINGS.role_head_office)
        self.tasks_group.hide()
        return True

    def _show_branch(self, node_id: str) -> bool:
        branch = self.session.get(Branch, node_id)
        if branch is None:
            return False
        self.title_label.setText(branch.name)
        self._add_field(field_label(Branch, "id"), branch.id)
        self._add_field(field_label(Branch, "short_name"), branch.short_name)
        if branch.territorial_unit is not None:
            self._add_field(
                field_label(Branch, "territorial_unit_id"),
                branch.territorial_unit.name,
            )
        self.tasks_group.hide()
        return True

    def _show_department(self, node_id: str) -> bool:
        department = self.session.get(Department, UUID(node_id))
        if department is None:
            return False
        self.title_label.setText(department.name)
        self._add_field(field_label(Department, "short_name"), department.short_name)
        if department.branch is not None:
            self._add_field(
                field_label(Department, "branch_id"), department.branch.name
            )
        self._add_field(
            field_label(Department, "active"), _bool_text(department.active)
        )
        self.tasks_group.hide()
        return True

    def _show_workgroup(self, node_id: str) -> bool:
        workgroup = self.session.get(WorkingGroup, UUID(node_id))
        if workgroup is None:
            return False
        self.title_label.setText(workgroup.name)
        if workgroup.department is not None:
            self._add_field(
                field_label(WorkingGroup, "department_id"),
                workgroup.department.name,
            )
        self._add_field(field_label(WorkingGroup, "comment"), workgroup.comment)
        self._add_field(
            field_label(WorkingGroup, "active"), _bool_text(workgroup.active)
        )
        self.tasks_group.hide()
        return True

    def _show_employee(self, node_id: str) -> bool:
        employee = self.session.get(Employee, UUID(node_id))
        if employee is None:
            return False
        self._employee = employee
        self.title_label.setText(employee.display_name())
        self._add_field(field_label(Employee, "last_name"), employee.last_name)
        self._add_field(field_label(Employee, "first_name"), employee.first_name)
        self._add_field(field_label(Employee, "middle_name"), employee.middle_name)
        self._add_field(field_label(Employee, "position"), employee.position)
        if employee.academic_title is not None:
            self._add_field(
                field_label(Employee, "academic_title_id"),
                employee.academic_title.name,
            )
        if employee.department is not None:
            self._add_field(
                field_label(Employee, "department_id"), employee.department.name
            )
        membership = employee.current_membership
        if membership is not None and membership.working_group is not None:
            self._add_field(
                field_label(WorkGroupMembership, "working_group_id"),
                membership.working_group.name,
            )
            self._add_field(
                field_label(WorkGroupMembership, "start_date"),
                _date_text(membership.start_date),
            )
            self._add_field(
                field_label(WorkGroupMembership, "end_date"),
                _date_text(membership.end_date),
            )
        # История прежних участий (закрытые записи)
        history = [
            m for m in employee.workgroup_memberships
            if m is not membership and m.working_group is not None
        ]
        for past in history:
            period = f"{_date_text(past.start_date)} — {_date_text(past.end_date)}"
            self._add_field(
                f"{past.working_group.name} ({STRINGS.oshm_membership_history})",
                period,
            )
        self._add_field(field_label(Employee, "active"), _bool_text(employee.active))
        self._fill_tasks(employee)
        self.tasks_group.show()
        return True

    def _fill_tasks(self, employee: Employee) -> None:
        """Заполняет таблицу задач, назначенных сотруднику."""
        tasks = sorted(employee.tasks, key=lambda task: task.name)
        self.tasks_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            cells = [
                task.id,
                task.name,
                _date_text(task.start_date),
                _date_text(task.end_date),
            ]
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if column == 0:
                    cell.setData(Qt.UserRole, task.id)
                self.tasks_table.setItem(row, column, cell)

    # ------------------------------------------------------------------
    # Действия
    # ------------------------------------------------------------------

    def set_tasks_editable(self, editable: bool) -> None:
        """Включает/отключает кнопки назначения задач (ГО не ведёт людей)."""
        self.task_add_btn.setEnabled(editable)
        self.task_remove_btn.setEnabled(editable)

    def _edit_clicked(self) -> None:
        if self.current_node is not None:
            self.edit_requested.emit(self.current_node)

    def _show_statistics(self) -> None:
        """Запрашивает статистику по текущему элементу (обрабатывает приложение)."""
        if self.current_node is not None:
            self.statistics_requested.emit(self.current_node)

    def _add_tasks(self) -> None:
        """Назначает сотруднику задачи, выбранные в диалоге выбора."""
        if self._employee is None:
            return
        excluded = [task.id for task in self._employee.tasks]
        dialog = TaskPickerDialog(self.session, excluded_ids=excluded, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            for task in dialog.selected_tasks():
                if task not in self._employee.tasks:
                    self._employee.tasks.append(task)
            self.session.commit()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка назначения задачи сотруднику")
            QMessageBox.critical(self, STRINGS.title_error, str(exc))
            self.session.rollback()
            return
        self._fill_tasks(self._employee)

    def _remove_tasks(self) -> None:
        """Снимает с сотрудника назначения, выбранные в таблице задач."""
        if self._employee is None:
            return
        selected_ids = {
            self.tasks_table.item(index.row(), 0).data(Qt.UserRole)
            for index in self.tasks_table.selectionModel().selectedRows()
        }
        if not selected_ids:
            return
        try:
            self._employee.tasks = [
                task for task in self._employee.tasks if task.id not in selected_ids
            ]
            self.session.commit()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка снятия назначения задачи")
            QMessageBox.critical(self, STRINGS.title_error, str(exc))
            self.session.rollback()
            return
        self._fill_tasks(self._employee)
