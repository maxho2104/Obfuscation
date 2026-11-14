"""Диалоги настройки фильтрации записей таблиц."""

from typing import List, Optional

from PyQt5.QtCore import QDate, QDateTime, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.gui.filter_model import (
    FilterCondition,
    operators_for,
    resolve_value_type,
)
from internal_correspondence.gui.table_model import ColumnDef
from internal_correspondence.orm.labels import field_short_label
from internal_correspondence.utils.string_resources import STRINGS

_VALUE_PAGES = {
    "text": 0,
    "date": 1,
    "datetime": 2,
    "number": 3,
    "bool": 4,
    "integer": 5,
}


class AddFilterDialog(QDialog):
    """Диалог создания или изменения одного условия фильтрации."""

    def __init__(
        self,
        model_class: type,
        columns: List[ColumnDef],
        condition: Optional[FilterCondition] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.model_class = model_class
        self.columns = columns
        self._condition = condition
        self._value_type = "text"
        self.setWindowTitle(
            STRINGS.dialog_edit_filter_title
            if condition is not None
            else STRINGS.dialog_add_filter_title
        )
        self.setMinimumWidth(420)
        self._setup_ui()
        self._on_column_changed()
        if condition is not None:
            self._load_condition(condition)

    def _setup_ui(self) -> None:
        layout = QFormLayout(self)

        self.column_combo = QComboBox()
        for column in self.columns:
            header = column.header or field_short_label(self.model_class, column.name)
            self.column_combo.addItem(header, column.name)
        layout.addRow(STRINGS.label_field, self.column_combo)

        self.operator_combo = QComboBox()
        layout.addRow(STRINGS.label_condition, self.operator_combo)

        self.value_stack = QStackedWidget()
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText(STRINGS.placeholder_filter_value)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setDate(QDate.currentDate())
        self.datetime_edit = QDateTimeEdit()
        self.datetime_edit.setCalendarPopup(True)
        self.datetime_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.datetime_edit.setDateTime(QDateTime.currentDateTime())
        self.number_edit = QDoubleSpinBox()
        self.number_edit.setDecimals(2)
        self.number_edit.setRange(-1_000_000_000, 1_000_000_000)
        self.int_edit = QSpinBox()
        self.int_edit.setRange(-2_000_000_000, 2_000_000_000)
        self.bool_combo = QComboBox()
        self.bool_combo.addItem("Да", "true")
        self.bool_combo.addItem("Нет", "false")

        for widget in (
            self.text_edit,
            self.date_edit,
            self.datetime_edit,
            self.number_edit,
            self.bool_combo,
            self.int_edit,
        ):
            self.value_stack.addWidget(widget)
        layout.addRow(STRINGS.label_value, self.value_stack)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

        self.column_combo.currentIndexChanged.connect(self._on_column_changed)

    def _on_column_changed(self) -> None:
        column_name = self.column_combo.currentData()
        self._value_type = resolve_value_type(self.model_class, column_name)
        self.operator_combo.clear()
        for operator, label in operators_for(self._value_type):
            self.operator_combo.addItem(label, operator)
        self.value_stack.setCurrentIndex(_VALUE_PAGES.get(self._value_type, 0))

    def _load_condition(self, condition: FilterCondition) -> None:
        """Заполняет редакторы существующим условием (режим изменения)."""
        column_index = self.column_combo.findData(condition.column_name)
        if column_index >= 0:
            self.column_combo.setCurrentIndex(column_index)
        operator_index = self.operator_combo.findData(condition.operator)
        if operator_index >= 0:
            self.operator_combo.setCurrentIndex(operator_index)
        if self._value_type == "date":
            self.date_edit.setDate(
                QDate.fromString(condition.value, "yyyy-MM-dd")
            )
        elif self._value_type == "datetime":
            self.datetime_edit.setDateTime(
                QDateTime.fromString(condition.value, Qt.ISODate)
            )
        elif self._value_type == "number":
            try:
                self.number_edit.setValue(float(condition.value))
            except ValueError:
                pass
        elif self._value_type == "integer":
            try:
                self.int_edit.setValue(int(condition.value))
            except ValueError:
                pass
        elif self._value_type == "bool":
            index = self.bool_combo.findData(condition.value)
            if index >= 0:
                self.bool_combo.setCurrentIndex(index)
        else:
            self.text_edit.setText(condition.value)

    def _current_value(self) -> str:
        if self._value_type == "date":
            return self.date_edit.date().toString("yyyy-MM-dd")
        if self._value_type == "datetime":
            return self.datetime_edit.dateTime().toString(Qt.ISODate)
        if self._value_type == "number":
            return f"{self.number_edit.value():g}"
        if self._value_type == "integer":
            return str(self.int_edit.value())
        if self._value_type == "bool":
            return str(self.bool_combo.currentData())
        return self.text_edit.text().strip()

    def condition(self) -> Optional[FilterCondition]:
        """Возвращает созданное (изменённое) условие; None, если пусто."""
        value = self._current_value()
        if self._value_type == "text" and not value:
            return None
        return FilterCondition(
            column_name=self.column_combo.currentData(),
            operator=self.operator_combo.currentData(),
            value=value,
        )

    def accept(self) -> None:
        if self.condition() is None:
            self.text_edit.setFocus()
            return
        super().accept()


class FilterDialog(QDialog):
    """Диалог управления примененными фильтрами.

    Строки условий оформлены рамкой (QFrame.Box); «×» удаляет условие,
    двойной щелчок по строке открывает диалог её изменения.
    """

    filtersChanged = pyqtSignal(list)

    def __init__(
        self,
        model_class: type,
        columns: List[ColumnDef],
        filters: List[FilterCondition],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.model_class = model_class
        self.columns = columns
        self._columns_by_name = {column.name: column for column in columns}
        self._filters = list(filters)
        self.setWindowTitle(STRINGS.button_filter)
        self.setMinimumWidth(520)
        self.setMinimumHeight(320)
        self._setup_ui()
        self._rebuild_rows()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(STRINGS.filters_applied_caption))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self.rows_widget)
        self._rows_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.rows_widget)
        layout.addWidget(self.scroll, 1)

        self.add_btn = QPushButton(STRINGS.button_add_filter)
        self.add_btn.clicked.connect(self._add_filter)
        layout.addWidget(self.add_btn)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def filters(self) -> List[FilterCondition]:
        """Возвращает текущий список условий."""
        return list(self._filters)

    def _clear_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_rows(self) -> None:
        self._clear_rows()

        if not self._filters:
            empty_label = QLabel(STRINGS.filters_none)
            self._rows_layout.addWidget(empty_label)

        for condition in self._filters:
            self._rows_layout.addWidget(self._build_row(condition))

        self._rows_layout.addStretch(1)

    def _build_row(self, condition: FilterCondition) -> QFrame:
        column = self._columns_by_name.get(condition.column_name)
        header = column.header if column else condition.column_name
        value_type = resolve_value_type(self.model_class, condition.column_name)

        row = QFrame()
        row.setFrameShape(QFrame.Box)
        row.mouseDoubleClickEvent = (
            lambda _event, item=condition: self._edit_filter(item)
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 4, 6, 4)

        label = QLabel(condition.describe(header, value_type))
        label.setWordWrap(True)
        row_layout.addWidget(label, 1, Qt.AlignVCenter)

        remove_btn = QToolButton()
        remove_btn.setText("×")
        remove_btn.setToolTip(STRINGS.tooltip_remove_filter)
        remove_btn.clicked.connect(
            lambda _checked=False, item=condition: self._remove_filter(item)
        )
        row_layout.addWidget(remove_btn, 0, Qt.AlignVCenter)

        return row

    def _add_filter(self) -> None:
        dialog = AddFilterDialog(self.model_class, self.columns, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        condition = dialog.condition()
        if condition is None or condition in self._filters:
            return
        self._filters.append(condition)
        self._rebuild_rows()
        self.filtersChanged.emit(self.filters())

    def _edit_filter(self, condition: FilterCondition) -> None:
        """Открывает диалог изменения существующего условия."""
        dialog = AddFilterDialog(
            self.model_class, self.columns, condition=condition, parent=self
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        updated = dialog.condition()
        if updated is None or (
            updated != condition and updated in self._filters
        ):
            return
        index = self._filters.index(condition)
        self._filters[index] = updated
        self._rebuild_rows()
        self.filtersChanged.emit(self.filters())

    def _remove_filter(self, condition: FilterCondition) -> None:
        if condition not in self._filters:
            return
        self._filters.remove(condition)
        self._rebuild_rows()
        self.filtersChanged.emit(self.filters())
