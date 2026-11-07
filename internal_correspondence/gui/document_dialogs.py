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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import (
    EVALUATION_VALUE_LABELS,
    MATERIAL_TYPE_LABELS,
    REPORT_TYPE_LABELS,
    TELEGRAM_TYPE_LABELS,
)
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
    ScientificMaterial,
    ScientificTask,
    Telegram,
)
from internal_correspondence.utils.string_resources import STRINGS


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
        for key, label in MATERIAL_TYPE_LABELS.items():
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

        self.task_combo = QComboBox()
        self.task_combo.addItem("—", None)
        for task in self.session.query(ScientificTask).order_by(ScientificTask.id).all():
            self.task_combo.addItem(f"{task.id} — {task.name}", task.id)
        self.form.addRow(field_form_label(ScientificMaterial, "task_id"), self.task_combo)

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
        if m.task_id:
            idx = self.task_combo.findData(m.task_id)
            if idx >= 0:
                self.task_combo.setCurrentIndex(idx)

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
            "task_id": self.task_combo.currentData(),
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
        for key, label in TELEGRAM_TYPE_LABELS.items():
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
        for key, label in REPORT_TYPE_LABELS.items():
            self.report_type_combo.addItem(f"{label} ({key})", key)
        self.form.addRow(field_form_label(Telegram, "report_type"), self.report_type_combo)

        self.country_combo = QComboBox()
        self.country_combo.addItem("—", None)
        for country in self.session.query(Country).order_by(Country.name).all():
            self.country_combo.addItem(country.name, country.id)
        self.form.addRow(field_form_label(Telegram, "country_id"), self.country_combo)

        self.task_combo = QComboBox()
        self.task_combo.addItem("—", None)
        for task in self.session.query(ScientificTask).order_by(ScientificTask.id).all():
            self.task_combo.addItem(f"{task.id} — {task.name}", task.id)
        self.form.addRow(field_form_label(Telegram, "task_id"), self.task_combo)

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
        if t.task_id:
            idx = self.task_combo.findData(t.task_id)
            if idx >= 0:
                self.task_combo.setCurrentIndex(idx)
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
            "task_id": self.task_combo.currentData(),
            "employees": self.employees_widget.get_employees(),
            "comment": self.comment.toPlainText().strip() or None,
            "branch_id": self.branch_id,
        }

    def get_new_files(self) -> List[Path]:
        return self.files_widget.get_new_files()
