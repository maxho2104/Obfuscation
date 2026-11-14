"""Диалог ручного выставления оценок документам."""

from datetime import date
from typing import Tuple

from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
)

from internal_correspondence.core.constants import EvaluationValue
from internal_correspondence.core.enum_registry import pack_enum_choices
from internal_correspondence.utils.string_resources import STRINGS


class EvaluationAssignDialog(QDialog):
    """Диалог выбора значения оценки и даты её выставления.

    Оценка сохраняется без списка оценок (ручное выставление) с датой
    в поле ``Evaluation.date``.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.dialog_assign_evaluation_title)
        self.setMinimumWidth(320)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.value_combo = QComboBox()
        for value, text in pack_enum_choices("evaluation_value"):
            self.value_combo.addItem(text, value)
        form.addRow(STRINGS.label_evaluation_value, self.value_combo)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setDate(date.today())
        form.addRow(STRINGS.label_evaluation_date, self.date_edit)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_data(self) -> Tuple[EvaluationValue, date]:
        """Возвращает выбранные значение оценки и дату выставления."""
        return EvaluationValue(self.value_combo.currentData()), (
            self.date_edit.date().toPyDate()
        )
