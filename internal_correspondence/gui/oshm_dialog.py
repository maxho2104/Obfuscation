"""Диалог организационно-штатной структуры (ОШС)."""

from pathlib import Path
from typing import Optional
from uuid import UUID

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.labels import (
    entity_label,
    field_form_label,
    field_label,
)
from internal_correspondence.orm.models import Branch, Department, Employee, WorkingGroup
from internal_correspondence.services.reference_service import (
    DepartmentService,
    EmployeeService,
    WorkingGroupService,
)

logger = get_logger("oshm_dialog")


class OSHMDialog(QDialog):
    """Диалог редактирования организационно-штатной структуры филиала."""

    def __init__(self, session, branch_id: str, read_only: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.branch_id = branch_id
        self.read_only = read_only
        self.setWindowTitle(f"ОШС филиала {branch_id}")
        self.setMinimumSize(700, 500)
        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Элемент", "Статус"])
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemDoubleClicked.connect(self._edit_item)
        layout.addWidget(self.tree)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_data(self) -> None:
        self.tree.clear()
        branch = self.session.get(Branch, self.branch_id)
        if branch is None:
            return

        branch_item = QTreeWidgetItem(self.tree, [branch.name, entity_label(Branch)])
        branch_item.setData(0, Qt.UserRole, ("branch", branch.id))
        branch_item.setExpanded(True)

        departments = (
            self.session.query(Department)
            .filter(Department.branch_id == self.branch_id)
            .order_by(Department.name)
            .all()
        )
        for dept in departments:
            dept_item = QTreeWidgetItem(
                branch_item,
                [dept.name, "Действующий" if dept.active else "Сокращён"],
            )
            dept_item.setData(0, Qt.UserRole, ("department", str(dept.id)))
            dept_item.setExpanded(True)

            workgroups = (
                self.session.query(WorkingGroup)
                .filter(WorkingGroup.department_id == dept.id)
                .order_by(WorkingGroup.name)
                .all()
            )
            for wg in workgroups:
                wg_item = QTreeWidgetItem(
                    dept_item,
                    [wg.name, "Действующая" if wg.active else "Упразднена"],
                )
                wg_item.setData(0, Qt.UserRole, ("workgroup", str(wg.id)))

            employees = (
                self.session.query(Employee)
                .filter(Employee.department_id == dept.id)
                .order_by(Employee.last_name)
                .all()
            )
            for emp in employees:
                emp_item = QTreeWidgetItem(
                    dept_item,
                    [emp.display_name(), "Действующий" if emp.active else "Неактивный"],
                )
                emp_item.setData(0, Qt.UserRole, ("employee", str(emp.id)))

    def _selected_node(self) -> Optional[tuple]:
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, Qt.UserRole)

    def _show_context_menu(self, position) -> None:
        if self.read_only:
            return
        item = self.tree.itemAt(position)
        if item is None:
            return
        self.tree.setCurrentItem(item)
        node_type, node_id = item.data(0, Qt.UserRole)

        menu = QMenu()
        if node_type == "branch":
            add_dept = menu.addAction(f"Добавить {entity_label(Department).lower()}")
            add_dept.triggered.connect(self._add_department)
        elif node_type == "department":
            add_wg = menu.addAction(f"Добавить {entity_label(WorkingGroup).lower()}")
            add_wg.triggered.connect(self._add_workgroup)
            add_emp = menu.addAction(f"Добавить {entity_label(Employee).lower()}")
            add_emp.triggered.connect(self._add_employee)
            menu.addSeparator()
            edit_dept = menu.addAction("Изменить")
            edit_dept.triggered.connect(self._edit_item)
            hide_dept = menu.addAction("Скрыть/показать")
            hide_dept.triggered.connect(self._toggle_department)
            delete_dept = menu.addAction("Удалить")
            delete_dept.triggered.connect(self._delete_item)
        elif node_type == "workgroup":
            edit_wg = menu.addAction("Изменить")
            edit_wg.triggered.connect(self._edit_item)
            toggle_wg = menu.addAction("Скрыть/показать")
            toggle_wg.triggered.connect(self._toggle_workgroup)
            delete_wg = menu.addAction("Удалить")
            delete_wg.triggered.connect(self._delete_item)
        elif node_type == "employee":
            edit_emp = menu.addAction("Изменить")
            edit_emp.triggered.connect(self._edit_item)
            toggle_emp = menu.addAction("Скрыть/показать")
            toggle_emp.triggered.connect(self._toggle_employee)
            delete_emp = menu.addAction("Удалить")
            delete_emp.triggered.connect(self._delete_item)
        menu.exec_(self.tree.viewport().mapToGlobal(position))

    def _add_department(self) -> None:
        dialog = DepartmentEditDialog(self.session, branch_id=self.branch_id, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            try:
                service = DepartmentService(self.session)
                service.create(dialog.get_data())
                self.session.commit()
                self._load_data()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Ошибка добавления отдела")
                QMessageBox.critical(self, "Ошибка", str(exc))
                self.session.rollback()

    def _add_workgroup(self) -> None:
        node = self._selected_node()
        if node is None or node[0] != "department":
            return
        dialog = WorkingGroupEditDialog(self.session, department_id=UUID(node[1]), parent=self)
        if dialog.exec_() == QDialog.Accepted:
            try:
                service = WorkingGroupService(self.session)
                service.create(dialog.get_data())
                self.session.commit()
                self._load_data()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Ошибка добавления рабочей группы")
                QMessageBox.critical(self, "Ошибка", str(exc))
                self.session.rollback()

    def _add_employee(self) -> None:
        node = self._selected_node()
        if node is None or node[0] != "department":
            return
        dialog = EmployeeEditDialog(self.session, department_id=UUID(node[1]), parent=self)
        if dialog.exec_() == QDialog.Accepted:
            try:
                service = EmployeeService(self.session)
                service.create(dialog.get_data())
                self.session.commit()
                self._load_data()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Ошибка добавления сотрудника")
                QMessageBox.critical(self, "Ошибка", str(exc))
                self.session.rollback()

    def _edit_item(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        node_type, node_id = node
        try:
            if node_type == "department":
                obj = self.session.get(Department, UUID(node_id))
                dialog = DepartmentEditDialog(self.session, item=obj, parent=self)
            elif node_type == "workgroup":
                obj = self.session.get(WorkingGroup, UUID(node_id))
                dialog = WorkingGroupEditDialog(self.session, item=obj, parent=self)
            elif node_type == "employee":
                obj = self.session.get(Employee, UUID(node_id))
                dialog = EmployeeEditDialog(self.session, item=obj, parent=self)
            else:
                return
            if dialog.exec_() == QDialog.Accepted:
                if node_type == "department":
                    DepartmentService(self.session).update(obj, dialog.get_data())
                elif node_type == "workgroup":
                    WorkingGroupService(self.session).update(obj, dialog.get_data())
                elif node_type == "employee":
                    EmployeeService(self.session).update(obj, dialog.get_data())
                self.session.commit()
                self._load_data()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка редактирования элемента ОШС")
            QMessageBox.critical(self, "Ошибка", str(exc))
            self.session.rollback()

    def _toggle_department(self) -> None:
        node = self._selected_node()
        if node is None or node[0] != "department":
            return
        obj = self.session.get(Department, UUID(node[1]))
        obj.active = not obj.active
        self.session.commit()
        self._load_data()

    def _toggle_workgroup(self) -> None:
        node = self._selected_node()
        if node is None or node[0] != "workgroup":
            return
        obj = self.session.get(WorkingGroup, UUID(node[1]))
        obj.active = not obj.active
        self.session.commit()
        self._load_data()

    def _toggle_employee(self) -> None:
        node = self._selected_node()
        if node is None or node[0] != "employee":
            return
        obj = self.session.get(Employee, UUID(node[1]))
        obj.active = not obj.active
        self.session.commit()
        self._load_data()

    def _delete_item(self) -> None:
        node = self._selected_node()
        if node is None:
            return
        node_type, node_id = node
        reply = QMessageBox.question(self, "Подтверждение", "Удалить выбранный элемент?")
        if reply != QMessageBox.Yes:
            return
        try:
            if node_type == "department":
                obj = self.session.get(Department, UUID(node_id))
                DepartmentService(self.session).delete(obj)
            elif node_type == "workgroup":
                obj = self.session.get(WorkingGroup, UUID(node_id))
                WorkingGroupService(self.session).delete(obj)
            elif node_type == "employee":
                obj = self.session.get(Employee, UUID(node_id))
                EmployeeService(self.session).delete(obj)
            self.session.commit()
            self._load_data()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка удаления элемента ОШС")
            QMessageBox.critical(self, "Ошибка", str(exc))
            self.session.rollback()


class DepartmentEditDialog(QDialog):
    """Диалог редактирования отдела."""

    def __init__(self, session, item=None, branch_id: Optional[str] = None, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.item = item
        self.branch_id = branch_id or (item.branch_id if item else None)
        title = entity_label(Department)
        self.setWindowTitle(title if item else f"Новый {title.lower()}")
        self._setup_ui()
        if item:
            self.name_edit.setText(item.name)
            self.short_edit.setText(item.short_name or "")
            self.active_check.setChecked(item.active)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.short_edit = QLineEdit()
        self.active_check = QCheckBox(field_label(Department, "active"))
        self.active_check.setChecked(True)
        form.addRow(field_form_label(Department, "name"), self.name_edit)
        form.addRow(field_form_label(Department, "short_name"), self.short_edit)
        form.addRow("", self.active_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "short_name": self.short_edit.text().strip() or None,
            "active": self.active_check.isChecked(),
            "branch_id": self.branch_id,
        }


class WorkingGroupEditDialog(QDialog):
    """Диалог редактирования рабочей группы."""

    def __init__(self, session, item=None, department_id: Optional[UUID] = None, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.item = item
        self.department_id = department_id or (item.department_id if item else None)
        title = entity_label(WorkingGroup)
        self.setWindowTitle(title if item else f"Новая {title.lower()}")
        self._setup_ui()
        if item:
            self.name_edit.setText(item.name)
            self.comment_edit.setPlainText(item.comment or "")
            self.active_check.setChecked(item.active)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setMaximumHeight(80)
        self.active_check = QCheckBox(field_label(WorkingGroup, "active"))
        self.active_check.setChecked(True)
        form.addRow(field_form_label(WorkingGroup, "name"), self.name_edit)
        form.addRow(field_form_label(WorkingGroup, "comment"), self.comment_edit)
        form.addRow("", self.active_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "comment": self.comment_edit.toPlainText().strip() or None,
            "active": self.active_check.isChecked(),
            "department_id": self.department_id,
        }


class EmployeeEditDialog(QDialog):
    """Диалог редактирования сотрудника."""

    def __init__(self, session, item=None, department_id: Optional[UUID] = None, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.item = item
        self.department_id = department_id or (item.department_id if item else None)
        title = entity_label(Employee)
        self.setWindowTitle(title if item else f"Новый {title.lower()}")
        self._setup_ui()
        if item:
            self.last_name.setText(item.last_name)
            self.first_name.setText(item.first_name)
            self.middle_name.setText(item.middle_name or "")
            self.position.setText(item.position or "")
            self.active_check.setChecked(item.active)
            if item.academic_title_id:
                idx = self.title_combo.findData(item.academic_title_id)
                if idx >= 0:
                    self.title_combo.setCurrentIndex(idx)
            if item.working_group_id:
                idx = self.workgroup_combo.findData(str(item.working_group_id))
                if idx >= 0:
                    self.workgroup_combo.setCurrentIndex(idx)
            if item.workgroup_start_date:
                self.workgroup_start_date.setDate(item.workgroup_start_date)
            if item.workgroup_end_date:
                self.workgroup_end_date.setDate(item.workgroup_end_date)
        self._update_date_fields_state()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.last_name = QLineEdit()
        self.first_name = QLineEdit()
        self.middle_name = QLineEdit()
        self.position = QLineEdit()
        self.title_combo = QComboBox()
        self.title_combo.addItem("—", None)
        from internal_correspondence.orm.models import AcademicTitle
        for title in self.session.query(AcademicTitle).order_by(AcademicTitle.sort_order).all():
            self.title_combo.addItem(title.name, title.id)
        self.workgroup_combo = QComboBox()
        self.workgroup_combo.addItem("—", None)
        for wg in self.session.query(WorkingGroup).order_by(WorkingGroup.name).all():
            self.workgroup_combo.addItem(wg.name, str(wg.id))
        self.workgroup_combo.currentIndexChanged.connect(self._update_date_fields_state)

        self.workgroup_start_date = self._create_date_edit()
        self.workgroup_end_date = self._create_date_edit()
        self.clear_dates_btn = QPushButton("Очистить даты")
        self.clear_dates_btn.clicked.connect(self._clear_workgroup_dates)

        self.active_check = QCheckBox(field_label(Employee, "active"))
        self.active_check.setChecked(True)
        form.addRow(field_form_label(Employee, "last_name"), self.last_name)
        form.addRow(field_form_label(Employee, "first_name"), self.first_name)
        form.addRow(field_form_label(Employee, "middle_name"), self.middle_name)
        form.addRow(field_form_label(Employee, "position"), self.position)
        form.addRow(field_form_label(Employee, "academic_title_id"), self.title_combo)
        form.addRow(field_form_label(Employee, "working_group_id"), self.workgroup_combo)
        form.addRow(field_form_label(Employee, "workgroup_start_date"), self.workgroup_start_date)
        form.addRow(field_form_label(Employee, "workgroup_end_date"), self.workgroup_end_date)
        form.addRow("", self.clear_dates_btn)
        form.addRow("", self.active_check)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_date_edit(self) -> QDateEdit:
        """Создаёт поле даты с пустым значением по умолчанию."""
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setMinimumDate(QDate(1900, 1, 1))
        edit.setSpecialValueText("не задано")
        edit.setDate(QDate(1900, 1, 1))
        return edit

    def _update_date_fields_state(self) -> None:
        """Включает поля дат только при выбранной рабочей группе."""
        has_group = self.workgroup_combo.currentData() is not None
        self.workgroup_start_date.setEnabled(has_group)
        self.workgroup_end_date.setEnabled(has_group)
        self.clear_dates_btn.setEnabled(has_group)

    def _clear_workgroup_dates(self) -> None:
        """Сбрасывает даты работы в рабочей группе."""
        self.workgroup_start_date.setDate(QDate(1900, 1, 1))
        self.workgroup_end_date.setDate(QDate(1900, 1, 1))

    def get_data(self) -> dict:
        wg_id = self.workgroup_combo.currentData()
        start_date = self.workgroup_start_date.date()
        end_date = self.workgroup_end_date.date()
        return {
            "last_name": self.last_name.text().strip(),
            "first_name": self.first_name.text().strip(),
            "middle_name": self.middle_name.text().strip() or None,
            "position": self.position.text().strip() or None,
            "academic_title_id": self.title_combo.currentData(),
            "department_id": self.department_id,
            "working_group_id": UUID(wg_id) if wg_id else None,
            "workgroup_start_date": (
                start_date.toPyDate() if wg_id and start_date.year() > 1900 else None
            ),
            "workgroup_end_date": (
                end_date.toPyDate() if wg_id and end_date.year() > 1900 else None
            ),
            "active": self.active_check.isChecked(),
        }
