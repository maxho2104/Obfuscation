"""Диалог ручного выставления оценок документам.

Оценка прикрепляется к списку оценок одним из двух способов:
создать новый список (номер предлагается автоматически, дата задаётся)
или привязать к существующему (поиск по номеру).
"""

from datetime import date
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import EvaluationValue
from internal_correspondence.core.enum_registry import pack_enum_choices
from internal_correspondence.orm.models import EvaluationList
from internal_correspondence.services.evaluation_service import EvaluationService
from internal_correspondence.utils.string_resources import STRINGS


class EvaluationAssignDialog(QDialog):
    """Диалог выбора значения, даты и списка оценок.

    Returns через ``get_data()``: значение оценки, дата выставления,
    режим («new»/«existing»), параметры нового списка (номер, дата) или
    выбранный существующий список.
    """

    def __init__(self, session: Session, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.dialog_assign_evaluation_title)
        self.setMinimumWidth(420)
        self._service = EvaluationService(session)
        self._lists: List[EvaluationList] = []
        self._setup_ui()
        self._load_lists()

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

        # --- выбор списка оценок ---
        self._new_radio = QRadioButton(STRINGS.evaluation_mode_new_list)
        self._new_radio.setChecked(True)
        layout.addWidget(self._new_radio)

        new_group = QGroupBox()
        new_form = QFormLayout(new_group)
        self.number_edit = QLineEdit()
        self.number_edit.setText(self._service.suggest_list_number())
        new_form.addRow(STRINGS.label_evaluation_list_number, self.number_edit)
        self.list_date_edit = QDateEdit()
        self.list_date_edit.setCalendarPopup(True)
        self.list_date_edit.setDisplayFormat("dd.MM.yyyy")
        self.list_date_edit.setDate(date.today())
        new_form.addRow(STRINGS.label_evaluation_list_date, self.list_date_edit)
        layout.addWidget(new_group)

        self._existing_radio = QRadioButton(STRINGS.evaluation_mode_existing_list)
        layout.addWidget(self._existing_radio)

        existing_group = QGroupBox()
        existing_layout = QVBoxLayout(existing_group)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(STRINGS.label_evaluation_list_filter)
        self.filter_edit.textChanged.connect(self._apply_filter)
        existing_layout.addWidget(self.filter_edit)
        self.lists_widget = QListWidget()
        existing_layout.addWidget(self.lists_widget, 1)
        layout.addWidget(existing_group, 1)

        self._new_radio.toggled.connect(self._toggle_mode)
        self._toggle_mode(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _toggle_mode(self, new_checked: bool) -> None:
        """Включает/выключает поля в зависимости от режима."""
        self.number_edit.setEnabled(new_checked)
        self.list_date_edit.setEnabled(new_checked)
        self.filter_edit.setEnabled(not new_checked)
        self.lists_widget.setEnabled(not new_checked)

    def _load_lists(self) -> None:
        """Загружает существующие списки оценок для выбора."""
        self._lists = (
            self._service.session.query(EvaluationList)
            .order_by(EvaluationList.date.desc(), EvaluationList.number.desc())
            .all()
        )
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Фильтрует списки оценок по введённому фрагменту номера."""
        needle = self.filter_edit.text().strip().lower() if hasattr(self, "filter_edit") else ""
        self.lists_widget.clear()
        for evaluation_list in self._lists:
            label = self._list_label(evaluation_list)
            if needle and needle not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, evaluation_list.id)
            self.lists_widget.addItem(item)
        if self.lists_widget.count() and self.lists_widget.currentRow() < 0:
            self.lists_widget.setCurrentRow(0)

    @staticmethod
    def _list_label(evaluation_list: EvaluationList) -> str:
        """Возвращает подпись списка оценок: «номер от дата»."""
        date_text = (
            evaluation_list.date.strftime("%d.%m.%Y")
            if evaluation_list.date
            else "—"
        )
        return f"{evaluation_list.number} от {date_text}"

    def selected_list(self) -> Optional[EvaluationList]:
        """Возвращает выбранный существующий список оценок (None — не выбран)."""
        item = self.lists_widget.currentItem()
        if item is None:
            return None
        list_id = item.data(Qt.UserRole)
        for evaluation_list in self._lists:
            if evaluation_list.id == list_id:
                return evaluation_list
        return None

    def get_data(self):
        """Возвращает введённые данные.

        Returns:
            Кортеж (значение оценки, дата выставления, режим, номер нового
            списка, дата нового списка, выбранный существующий список).
            Для режима «new» последние три: номер, дата, None; для
            «existing»: None, None, список.
        """
        value = EvaluationValue(self.value_combo.currentData())
        assigned_date = self.date_edit.date().toPyDate()
        if self._new_radio.isChecked():
            return (
                value,
                assigned_date,
                "new",
                self.number_edit.text().strip(),
                self.list_date_edit.date().toPyDate(),
                None,
            )
        return (value, assigned_date, "existing", None, None, self.selected_list())
