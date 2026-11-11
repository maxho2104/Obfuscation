"""Виджет и диалог выбора сотрудников, причастных к документу."""

from typing import Iterable, List, Optional, Set

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from internal_correspondence.orm.models import Department, Employee


class EmployeePickerDialog(QDialog):
    """Диалог выбора сотрудников филиала, ещё не добавленных в документ."""

    def __init__(
        self,
        session,
        branch_id: Optional[str],
        excluded_ids: Optional[Iterable] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.branch_id = branch_id
        self.excluded_ids: Set = {employee_id for employee_id in (excluded_ids or [])}
        self._employees: List[Employee] = []
        self.setWindowTitle("Выбор сотрудников")
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._load_employees()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list_widget)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_employees(self) -> None:
        """Загружает сотрудников филиала, исключая уже выбранных."""
        query = self.session.query(Employee)
        if self.branch_id:
            query = query.join(Department).filter(Department.branch_id == self.branch_id)
        if self.excluded_ids:
            query = query.filter(Employee.id.notin_(list(self.excluded_ids)))
        self._employees = query.order_by(
            Employee.last_name,
            Employee.first_name,
            Employee.middle_name,
        ).all()

        self.list_widget.clear()
        for employee in self._employees:
            department = employee.department
            department_label = ""
            if department is not None:
                department_label = department.short_name or department.name
            text = employee.display_name()
            if department_label:
                text = f"{text} — {department_label}"
            if not employee.active:
                text = f"{text} (неактивен)"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, employee.id)
            self.list_widget.addItem(item)

    def selected_employees(self) -> List[Employee]:
        """Возвращает сотрудников, выбранных в списке."""
        selected_ids = {
            item.data(Qt.UserRole) for item in self.list_widget.selectedItems()
        }
        return [employee for employee in self._employees if employee.id in selected_ids]


class ParticipatingEmployeesWidget(QGroupBox):
    """Список причастных сотрудников с кнопками добавления и удаления."""

    def __init__(self, session, branch_id: Optional[str], parent=None) -> None:
        super().__init__("Причастные сотрудники", parent)
        self.session = session
        self.branch_id = branch_id
        self._employees: List[Employee] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setMinimumHeight(100)
        layout.addWidget(self.list_widget)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton("+")
        self.add_btn.setProperty("role", "compact")
        self.add_btn.setToolTip("Добавить причастных сотрудников")
        self.add_btn.clicked.connect(self._add_employees)

        self.remove_btn = QPushButton("-")
        self.remove_btn.setProperty("role", "compact")
        self.remove_btn.setToolTip("Удалить выбранных сотрудников")
        self.remove_btn.clicked.connect(self._remove_employees)

        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.remove_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

    def set_employees(self, employees: Optional[Iterable[Employee]]) -> None:
        """Устанавливает список причастных сотрудников документа."""
        self._employees = list(employees or [])
        self._refresh_list()

    def get_employees(self) -> List[Employee]:
        """Возвращает текущий список причастных сотрудников."""
        return list(self._employees)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for employee in self._employees:
            department = employee.department
            department_label = ""
            if department is not None:
                department_label = department.short_name or department.name
            text = employee.display_name()
            if department_label:
                text = f"{text} — {department_label}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, employee.id)
            self.list_widget.addItem(item)

    def _add_employees(self) -> None:
        excluded_ids = {employee.id for employee in self._employees}
        dialog = EmployeePickerDialog(
            self.session,
            self.branch_id,
            excluded_ids=excluded_ids,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        known_ids = {employee.id for employee in self._employees}
        for employee in dialog.selected_employees():
            if employee.id not in known_ids:
                self._employees.append(employee)
                known_ids.add(employee.id)
        self._refresh_list()

    def _remove_employees(self) -> None:
        selected_ids = {
            item.data(Qt.UserRole) for item in self.list_widget.selectedItems()
        }
        if not selected_ids:
            return
        self._employees = [
            employee for employee in self._employees if employee.id not in selected_ids
        ]
        self._refresh_list()
