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

_VALUE_PAGES = {
    "text": 0,
    "date": 1,
    "datetime": 2,
    "number": 3,
    "bool": 4,
    "integer": 5,
}


class AddFilterDialog(QDialog):
    """Диалог создания одного условия фильтрации."""

    def __init__(self, model_class: type, columns: List[ColumnDef], parent=None) -> None:
        super().__init__(parent)
        self.model_class = model_class
        self.columns = columns
        self._value_type = "text"
        self.setWindowTitle("Добавить фильтр")
        self.setMinimumWidth(420)
        self._setup_ui()
        self._on_column_changed()

    def _setup_ui(self) -> None:
        layout = QFormLayout(self)

        self.column_combo = QComboBox()
        for column in self.columns:
            self.column_combo.addItem(column.header, column.name)
        layout.addRow("Поле:", self.column_combo)

        self.operator_combo = QComboBox()
        layout.addRow("Условие:", self.operator_combo)

        self.value_stack = QStackedWidget()
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Введите значение")
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
        layout.addRow("Значение:", self.value_stack)

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
        """Возвращает созданное условие или None, если значение не задано."""
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
    """Диалог управления примененными фильтрами."""

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
        self.setWindowTitle("Фильтры")
        self.setMinimumWidth(520)
        self.setMinimumHeight(320)
        self._setup_ui()
        self._rebuild_rows()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Примененные фильтры:"))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self.rows_widget)
        self._rows_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.rows_widget)
        layout.addWidget(self.scroll, 1)

        self.add_btn = QPushButton("Добавить фильтр")
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
            empty_label = QLabel("Фильтры не заданы.")
            self._rows_layout.addWidget(empty_label)

        for condition in self._filters:
            self._rows_layout.addWidget(self._build_row(condition))

        self._rows_layout.addStretch(1)

    def _build_row(self, condition: FilterCondition) -> QWidget:
        column = self._columns_by_name.get(condition.column_name)
        header = column.header if column else condition.column_name
        value_type = resolve_value_type(self.model_class, condition.column_name)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(condition.describe(header, value_type))
        label.setWordWrap(True)
        row_layout.addWidget(label, 1)

        remove_btn = QToolButton()
        remove_btn.setText("×")
        remove_btn.setToolTip("Удалить фильтр")
        remove_btn.clicked.connect(lambda _checked=False, item=condition: self._remove_filter(item))
        row_layout.addWidget(remove_btn)

        return row

    def _add_filter(self) -> None:
        dialog = AddFilterDialog(self.model_class, self.columns, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        condition = dialog.condition()
        if condition is None or condition in self._filters:
            return
        self._filters.append(condition)
        self._rebuild_rows()
        self.filtersChanged.emit(self.filters())

    def _remove_filter(self, condition: FilterCondition) -> None:
        if condition not in self._filters:
            return
        self._filters.remove(condition)
        self._rebuild_rows()
        self.filtersChanged.emit(self.filters())
