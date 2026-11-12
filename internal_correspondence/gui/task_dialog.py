"""Диалог создания и редактирования научной задачи."""

from datetime import date
from typing import Any, Dict, Optional

from PyQt5.QtCore import QDate
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.domain_pack import enum_labels
from internal_correspondence.orm.labels import field_form_label
from internal_correspondence.orm.models import ScientificTask
from internal_correspondence.utils.string_resources import STRINGS


def _to_qdate(value: Optional[date]) -> QDate:
    if value is None:
        return QDate.currentDate()
    return QDate(value.year, value.month, value.day)


class ScientificTaskDialog(QDialog):
    """Диалог задачи: код, наименование, тип, сроки, пороги."""

    def __init__(
        self,
        task: Optional[ScientificTask] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.task = task
        self.setWindowTitle(
            STRINGS.task_edit_title if task is not None else STRINGS.task_create_title
        )
        self.setMinimumWidth(520)

        self.id_edit = QLineEdit()
        self.id_edit.setMaxLength(50)
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        for code, label in enum_labels("scientific_task_type").items():
            self.type_combo.addItem(f"{label} ({code})", code)

        self.start_edit = QDateEdit()
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("dd.MM.yyyy")
        self.end_edit = QDateEdit()
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("dd.MM.yyyy")
        self.no_end_check = QCheckBox(STRINGS.task_no_end)
        self.no_end_check.toggled.connect(self.end_edit.setDisabled)

        self.partial_edit = QLineEdit()
        self.full_edit = QLineEdit()
        validator = QDoubleValidator(0.0, 1_000_000_000.0, 2, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        for edit in (self.partial_edit, self.full_edit):
            edit.setValidator(validator)
            edit.setPlaceholderText("0,00")

        self.comment_edit = QPlainTextEdit()
        self.comment_edit.setFixedHeight(90)

        form = QFormLayout()
        form.addRow(field_form_label(ScientificTask, "id"), self.id_edit)
        form.addRow(field_form_label(ScientificTask, "name"), self.name_edit)
        form.addRow(field_form_label(ScientificTask, "type"), self.type_combo)
        form.addRow(field_form_label(ScientificTask, "start_date"), self.start_edit)
        form.addRow(field_form_label(ScientificTask, "end_date"), self.end_edit)
        form.addRow("", self.no_end_check)
        form.addRow(
            field_form_label(ScientificTask, "partial_threshold"), self.partial_edit
        )
        form.addRow(
            field_form_label(ScientificTask, "full_threshold"), self.full_edit
        )
        form.addRow(field_form_label(ScientificTask, "comment"), self.comment_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Save).setText(STRINGS.button_save)
        buttons.button(QDialogButtonBox.Cancel).setText(STRINGS.button_cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.start_edit.setDate(QDate.currentDate())
        self.end_edit.setDate(QDate.currentDate())
        self.no_end_check.setChecked(task is None)
        if task is not None:
            self._load(task)
        self.id_edit.setReadOnly(task is not None)

    def _load(self, task: ScientificTask) -> None:
        self.id_edit.setText(task.id)
        self.name_edit.setText(task.name)
        index = self.type_combo.findData(task.type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        self.start_edit.setDate(_to_qdate(task.start_date))
        self.no_end_check.setChecked(task.end_date is None)
        if task.end_date is not None:
            self.end_edit.setDate(_to_qdate(task.end_date))
        if task.partial_threshold is not None:
            self.partial_edit.setText(f"{float(task.partial_threshold):.2f}")
        if task.full_threshold is not None:
            self.full_edit.setText(f"{float(task.full_threshold):.2f}")
        self.comment_edit.setPlainText(task.comment or "")

    def _on_accept(self) -> None:
        if not self.id_edit.text().strip():
            QMessageBox.warning(
                self, STRINGS.title_error, STRINGS.task_code_required
            )
            return
        if not self.name_edit.text().strip():
            QMessageBox.warning(
                self, STRINGS.title_error, STRINGS.task_name_required
            )
            return
        if self.full_edit.text() and self.partial_edit.text():
            partial = float(self.partial_edit.text().replace(",", "."))
            full = float(self.full_edit.text().replace(",", "."))
            if partial > full:
                QMessageBox.warning(
                    self,
                    STRINGS.title_error,
                    STRINGS.task_threshold_order,
                )
                return
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        """Возвращает данные формы для ScientificTaskService."""
        return {
            "id": self.id_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "type": self.type_combo.currentData(),
            "start_date": self.start_edit.date().toPyDate(),
            "end_date": None
            if self.no_end_check.isChecked()
            else self.end_edit.date().toPyDate(),
            "comment": self.comment_edit.toPlainText().strip() or None,
            "partial_threshold": self._number(self.partial_edit.text()),
            "full_threshold": self._number(self.full_edit.text()),
        }

    @staticmethod
    def _number(text: str) -> Optional[float]:
        text = text.strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
