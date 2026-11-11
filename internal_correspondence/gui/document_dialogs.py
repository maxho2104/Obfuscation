"""Диалоги редактирования научных материалов и телеграмм."""

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.domain_pack import enum_labels
from internal_correspondence.gui.attached_files_widget import AttachedFilesWidget
from internal_correspondence.gui.employee_picker import ParticipatingEmployeesWidget
from internal_correspondence.orm.labels import (
    entity_label,
    field_form_label,
    field_label,
)
from internal_correspondence.orm.models import (
    Country,
    Consumer,
    Leader,
    ReportAddress,
    ScientificMaterial,
    ScientificTask,
    Telegram,
)
from internal_correspondence.utils.string_resources import STRINGS


class TaskSelectWidget(QWidget):
    """Мультивыбор научных задач документа (список с чекбоксами)."""

    def __init__(self, session, parent=None) -> None:
        super().__init__(parent)
        self._tasks: Dict[str, ScientificTask] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(120)
        layout.addWidget(self.list_widget)
        for task in session.query(ScientificTask).order_by(ScientificTask.id).all():
            self._tasks[task.id] = task
            item = QListWidgetItem(f"{task.id} — {task.name}")
            item.setData(Qt.UserRole, task.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)

    def set_tasks(self, tasks: List[ScientificTask]) -> None:
        """Отмечает в списке задачи, уже связанные с документом."""
        selected = {task.id for task in tasks}
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            checked = item.data(Qt.UserRole) in selected
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def get_tasks(self) -> List[ScientificTask]:
        """Возвращает задачи, отмеченные в списке."""
        result = []
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.checkState() == Qt.Checked:
                result.append(self._tasks[item.data(Qt.UserRole)])
        return result


class ReportAddressesWidget(QWidget):
    """Редактор адресации доклада: список «руководитель — дата доклада»."""

    def __init__(self, session, parent=None) -> None:
        super().__init__(parent)
        self._leaders = (
            session.query(Leader)
            .filter(Leader.active.is_(True))
            .order_by(Leader.id)
            .all()
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        self.leader_combo = QComboBox()
        for leader in self._leaders:
            self.leader_combo.addItem(leader.id, leader.id)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(date.today())
        self.add_btn = QPushButton(STRINGS.button_add)
        self.add_btn.clicked.connect(self._add)
        self.remove_btn = QPushButton(STRINGS.button_delete)
        self.remove_btn.clicked.connect(self._remove)
        controls.addWidget(self.leader_combo, 1)
        controls.addWidget(self.date_edit)
        controls.addWidget(self.add_btn)
        controls.addWidget(self.remove_btn)
        layout.addLayout(controls)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(100)
        layout.addWidget(self.list_widget)

    def _add(self) -> None:
        leader_id = self.leader_combo.currentData()
        if leader_id is None:
            return
        self._add_item(leader_id, self.date_edit.date().toPyDate(), None)

    def _add_item(
        self,
        leader_id: str,
        report_date: date,
        address: Optional[ReportAddress],
    ) -> None:
        item = QListWidgetItem(f"{leader_id} — {report_date.isoformat()}")
        item.setData(Qt.UserRole, (leader_id, report_date, address))
        self.list_widget.addItem(item)

    def _remove(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def set_addresses(self, addresses: List[ReportAddress]) -> None:
        """Заполняет список существующими записями адресации."""
        self.list_widget.clear()
        ordered = sorted(addresses, key=lambda a: (a.report_date, a.leader_id))
        for address in ordered:
            self._add_item(address.leader_id, address.report_date, address)

    def get_addresses(self) -> List[ReportAddress]:
        """Возвращает записи адресации; существующие сохраняют идентичность."""
        result = []
        for row in range(self.list_widget.count()):
            leader_id, report_date, address = self.list_widget.item(row).data(
                Qt.UserRole
            )
            if address is None:
                address = ReportAddress(leader_id=leader_id, report_date=report_date)
            result.append(address)
        return result


class MaterialEditDialog(QDialog):
    """Диалог создания/редактирования научного материала."""

    def __init__(
        self,
        session,
        storage_root: Path,
        material: Optional[ScientificMaterial] = None,
        branch_id: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.storage_root = storage_root
        self.material = material
        self.branch_id = branch_id or (material.branch_id if material else None)
        title = entity_label(ScientificMaterial)
        self.setWindowTitle(title if material else f"Новый {title.lower()}")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self._setup_ui()
        if material:
            self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        # Форма
        form_widget = QWidget()
        self.form = QFormLayout(form_widget)

        self.type_combo = QComboBox()
        for key, label in enum_labels("material_type").items():
            self.type_combo.addItem(f"{label} ({key})", key)
        self.form.addRow(field_form_label(ScientificMaterial, "type"), self.type_combo)

        self.outgoing_number = QLineEdit()
        self.form.addRow(
            field_form_label(ScientificMaterial, "outgoing_number"), self.outgoing_number
        )

        self.outgoing_date = QDateEdit()
        self.outgoing_date.setCalendarPopup(True)
        self.outgoing_date.setDate(date.today())
        self.form.addRow(
            field_form_label(ScientificMaterial, "outgoing_date"), self.outgoing_date
        )

        self.name_edit = QLineEdit()
        self.form.addRow(field_form_label(ScientificMaterial, "name"), self.name_edit)

        self.incoming_number = QLineEdit()
        self.form.addRow(
            field_form_label(ScientificMaterial, "incoming_number"), self.incoming_number
        )

        self.incoming_date = QDateEdit()
        self.incoming_date.setCalendarPopup(True)
        self.incoming_date.setSpecialValueText("")
        self.incoming_date.setDate(date(1900, 1, 1))
        self.incoming_date.setEnabled(False)
        self.form.addRow(
            field_form_label(ScientificMaterial, "incoming_date"), self.incoming_date
        )

        self.serial_number = QLineEdit()
        self.form.addRow(
            field_form_label(ScientificMaterial, "serial_number"), self.serial_number
        )

        self.release_year = QLineEdit()
        self.form.addRow(
            field_form_label(ScientificMaterial, "release_year"), self.release_year
        )

        self.permit_number = QLineEdit()
        self.form.addRow(
            field_form_label(ScientificMaterial, "permit_number"), self.permit_number
        )

        self.cost = QLineEdit()
        self.form.addRow(field_form_label(ScientificMaterial, "cost"), self.cost)

        self.country_combo = QComboBox()
        self.country_combo.addItem("—", None)
        for country in self.session.query(Country).order_by(Country.name).all():
            self.country_combo.addItem(country.name, country.id)
        self.form.addRow(field_form_label(ScientificMaterial, "country_id"), self.country_combo)

        self.consumer_combo = QComboBox()
        self.consumer_combo.addItem("—", None)
        for consumer in self.session.query(Consumer).order_by(Consumer.name).all():
            self.consumer_combo.addItem(consumer.name, consumer.id)
        self.form.addRow(field_form_label(ScientificMaterial, "consumer_id"), self.consumer_combo)

        self.tasks_widget = TaskSelectWidget(self.session)
        self.form.addRow(
            field_form_label(ScientificMaterial, "tasks"), self.tasks_widget
        )

        self.employees_widget = ParticipatingEmployeesWidget(self.session, self.branch_id)
        self.form.addRow(self.employees_widget)

        self.comment = QPlainTextEdit()
        self.comment.setMaximumHeight(80)
        self.form.addRow(field_form_label(ScientificMaterial, "comment"), self.comment)

        splitter.addWidget(form_widget)

        # Файлы
        self.files_widget = AttachedFilesWidget(self.storage_root)
        splitter.addWidget(self.files_widget)
        splitter.setSizes([500, 250])

        layout.addWidget(splitter)

        # Кнопки
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_data(self) -> None:
        m = self.material
        index = self.type_combo.findData(m.type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self.outgoing_number.setText(m.outgoing_number or "")
        if m.outgoing_date:
            self.outgoing_date.setDate(m.outgoing_date)
        self.name_edit.setText(m.name or "")
        self.incoming_number.setText(m.incoming_number or "")
        if m.incoming_date:
            self.incoming_date.setDate(m.incoming_date)
        self.serial_number.setText(m.serial_number or "")
        self.release_year.setText(str(m.release_year) if m.release_year else "")
        self.permit_number.setText(m.permit_number or "")
        self.cost.setText(str(m.cost) if m.cost else "")

        if m.country_id:
            idx = self.country_combo.findData(m.country_id)
            if idx >= 0:
                self.country_combo.setCurrentIndex(idx)
        if m.consumer_id:
            idx = self.consumer_combo.findData(m.consumer_id)
            if idx >= 0:
                self.consumer_combo.setCurrentIndex(idx)
        self.tasks_widget.set_tasks(list(m.tasks))

        self.comment.setPlainText(m.comment or "")
        self.employees_widget.set_employees(list(m.employees))
        self.files_widget.set_files(list(m.files))

    def _on_save(self) -> None:
        if not self._validate():
            return
        self.accept()

    def _validate(self) -> bool:
        if not self.outgoing_number.text().strip():
            label = field_label(ScientificMaterial, "outgoing_number")
            QMessageBox.warning(self, "Ошибка", f"Не заполнено обязательное поле «{label}».")
            return False
        if not self.name_edit.text().strip():
            label = field_label(ScientificMaterial, "name")
            QMessageBox.warning(self, "Ошибка", f"Не заполнено обязательное поле «{label}».")
            return False
        if not self.branch_id:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Не выбран филиал для {entity_label(ScientificMaterial).lower()}.",
            )
            return False
        return True

    def get_data(self) -> Dict[str, Any]:
        """Возвращает данные формы для создания/обновления модели."""
        return {
            "type": self.type_combo.currentData(),
            "outgoing_number": self.outgoing_number.text().strip(),
            "outgoing_date": self.outgoing_date.date().toPyDate(),
            "name": self.name_edit.text().strip(),
            "incoming_number": self.incoming_number.text().strip() or None,
            "incoming_date": self.incoming_date.date().toPyDate() if self.incoming_date.date().year() > 1900 else None,
            "serial_number": self.serial_number.text().strip() or None,
            "release_year": int(self.release_year.text()) if self.release_year.text().strip().isdigit() else None,
            "permit_number": self.permit_number.text().strip() or None,
            "cost": float(self.cost.text()) if self.cost.text().strip() else None,
            "country_id": self.country_combo.currentData(),
            "consumer_id": self.consumer_combo.currentData(),
            "tasks": self.tasks_widget.get_tasks(),
            "employees": self.employees_widget.get_employees(),
            "comment": self.comment.toPlainText().strip() or None,
            "branch_id": self.branch_id,
        }

    def get_new_files(self) -> List[Path]:
        return self.files_widget.get_new_files()


class TelegramEditDialog(QDialog):
    """Диалог создания/редактирования телеграммы."""

    def __init__(
        self,
        session,
        storage_root: Path,
        telegram: Optional[Telegram] = None,
        branch_id: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.storage_root = storage_root
        self.telegram = telegram
        self.branch_id = branch_id or (telegram.branch_id if telegram else None)
        title = entity_label(Telegram)
        self.setWindowTitle(title if telegram else f"Новая {title.lower()}")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self._setup_ui()
        if telegram:
            self._load_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)

        form_widget = QWidget()
        self.form = QFormLayout(form_widget)

        self.type_combo = QComboBox()
        for key, label in enum_labels("telegram_type").items():
            self.type_combo.addItem(f"{label} ({key})", key)
        self.form.addRow(field_form_label(Telegram, "type"), self.type_combo)

        self.outgoing_number = QLineEdit()
        self.form.addRow(field_form_label(Telegram, "outgoing_number"), self.outgoing_number)

        self.outgoing_date = QDateEdit()
        self.outgoing_date.setCalendarPopup(True)
        self.outgoing_date.setDate(date.today())
        self.form.addRow(field_form_label(Telegram, "outgoing_date"), self.outgoing_date)

        self.name_edit = QLineEdit()
        self.form.addRow(field_form_label(Telegram, "name"), self.name_edit)

        self.incoming_number = QLineEdit()
        self.form.addRow(field_form_label(Telegram, "incoming_number"), self.incoming_number)

        self.incoming_date = QDateEdit()
        self.incoming_date.setCalendarPopup(True)
        self.incoming_date.setSpecialValueText("")
        self.incoming_date.setDate(date(1900, 1, 1))
        self.incoming_date.setEnabled(False)
        self.form.addRow(field_form_label(Telegram, "incoming_date"), self.incoming_date)

        self.report_type_combo = QComboBox()
        self.report_type_combo.addItem("—", None)
        for key, label in enum_labels("telegram_report_type").items():
            self.report_type_combo.addItem(f"{label} ({key})", key)
        self.form.addRow(field_form_label(Telegram, "report_type"), self.report_type_combo)

        self.country_combo = QComboBox()
        self.country_combo.addItem("—", None)
        for country in self.session.query(Country).order_by(Country.name).all():
            self.country_combo.addItem(country.name, country.id)
        self.form.addRow(field_form_label(Telegram, "country_id"), self.country_combo)

        self.tasks_widget = TaskSelectWidget(self.session)
        self.form.addRow(field_form_label(Telegram, "tasks"), self.tasks_widget)

        self.report_addresses_widget = ReportAddressesWidget(self.session)
        self.form.addRow(
            field_form_label(Telegram, "report_addresses"),
            self.report_addresses_widget,
        )

        self.employees_widget = ParticipatingEmployeesWidget(self.session, self.branch_id)
        self.form.addRow(self.employees_widget)

        self.comment = QPlainTextEdit()
        self.comment.setMaximumHeight(80)
        self.form.addRow(field_form_label(Telegram, "comment"), self.comment)

        splitter.addWidget(form_widget)

        self.files_widget = AttachedFilesWidget(self.storage_root)
        splitter.addWidget(self.files_widget)
        splitter.setSizes([500, 250])

        layout.addWidget(splitter)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_data(self) -> None:
        t = self.telegram
        index = self.type_combo.findData(t.type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self.outgoing_number.setText(t.outgoing_number or "")
        if t.outgoing_date:
            self.outgoing_date.setDate(t.outgoing_date)
        self.name_edit.setText(t.name or "")
        self.incoming_number.setText(t.incoming_number or "")
        if t.incoming_date:
            self.incoming_date.setDate(t.incoming_date)
        if t.report_type:
            idx = self.report_type_combo.findData(t.report_type)
            if idx >= 0:
                self.report_type_combo.setCurrentIndex(idx)
        if t.country_id:
            idx = self.country_combo.findData(t.country_id)
            if idx >= 0:
                self.country_combo.setCurrentIndex(idx)
        self.tasks_widget.set_tasks(list(t.tasks))
        self.report_addresses_widget.set_addresses(list(t.report_addresses))
        self.comment.setPlainText(t.comment or "")
        self.employees_widget.set_employees(list(t.employees))
        self.files_widget.set_files(list(t.files))

    def _on_save(self) -> None:
        if not self._validate():
            return
        self.accept()

    def _validate(self) -> bool:
        if not self.outgoing_number.text().strip():
            label = field_label(Telegram, "outgoing_number")
            QMessageBox.warning(self, "Ошибка", f"Не заполнено обязательное поле «{label}».")
            return False
        if not self.name_edit.text().strip():
            label = field_label(Telegram, "name")
            QMessageBox.warning(self, "Ошибка", f"Не заполнено обязательное поле «{label}».")
            return False
        if not self.branch_id:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Не выбран филиал для {entity_label(Telegram).lower()}.",
            )
            return False
        return True

    def get_data(self) -> Dict[str, Any]:
        return {
            "type": self.type_combo.currentData(),
            "outgoing_number": self.outgoing_number.text().strip(),
            "outgoing_date": self.outgoing_date.date().toPyDate(),
            "name": self.name_edit.text().strip(),
            "incoming_number": self.incoming_number.text().strip() or None,
            "incoming_date": self.incoming_date.date().toPyDate() if self.incoming_date.date().year() > 1900 else None,
            "report_type": self.report_type_combo.currentData(),
            "country_id": self.country_combo.currentData(),
            "tasks": self.tasks_widget.get_tasks(),
            "report_addresses": self.report_addresses_widget.get_addresses(),
            "employees": self.employees_widget.get_employees(),
            "comment": self.comment.toPlainText().strip() or None,
            "branch_id": self.branch_id,
        }

    def get_new_files(self) -> List[Path]:
        return self.files_widget.get_new_files()
