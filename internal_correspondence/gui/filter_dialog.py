"""Диалоги настройки фильтрации записей таблиц."""

from typing import Any, List, Optional

from PyQt5.QtCore import QDate, QDateTime, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
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
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from internal_correspondence.core.enum_registry import pack_enum_choices
from internal_correspondence.gui.edit_elements import ItemsPickerDialog
from internal_correspondence.gui.filter_model import (
    FilterCondition,
    coerce_filter_ids,
    operators_for,
    parse_id_list,
    resolve_nullable,
    resolve_pack_enum,
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
    "enum": 6,
    "m2m": 7,
}


def _column_value_type(model_class: type, columns: List[ColumnDef], column_name: str) -> str:
    """Определяет тип значения колонки с учётом её описания (N→N)."""
    for column in columns:
        if column.name == column_name:
            if column.filter_target is not None:
                return "m2m"
            break
    return resolve_value_type(model_class, column_name)


def _column_filter_target(columns: List[ColumnDef], column_name: str) -> Optional[type]:
    """Возвращает класс связанной сущности для колонки-фильтра N→N."""
    for column in columns:
        if column.name == column_name:
            return column.filter_target
    return None


def resolve_m2m_labels(
    session: Session, target: type, raw_value: str
) -> List[str]:
    """Возвращает отображаемые имена связанных записей по идентификаторам.

    Не найденные идентификаторы пропускаются.
    """
    raw_ids = parse_id_list(raw_value)
    if session is None or target is None or not raw_ids:
        return raw_ids
    pk = sa_inspect(target).primary_key[0]
    instances = (
        session.query(target)
        .filter(getattr(target, pk.name).in_(coerce_filter_ids(target, raw_ids)))
        .all()
    )
    by_id = {str(getattr(instance, pk.name)): instance for instance in instances}
    return [
        ItemsPickerDialog._item_text(by_id[raw])  # pylint: disable=protected-access
        for raw in raw_ids
        if raw in by_id
    ]


class AddFilterDialog(QDialog):
    """Диалог создания или изменения одного условия фильтрации.

    Для полей «многие ко многим» значение задаётся списком с кнопками
    «+»/«−» (по аналогии с виджетами редактирования): «+» открывает
    диалог мультивыбора связанных записей, «−» удаляет выделенные.
    """

    def __init__(
        self,
        model_class: type,
        columns: List[ColumnDef],
        condition: Optional[FilterCondition] = None,
        session: Optional[Session] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.model_class = model_class
        self.columns = columns
        self._condition = condition
        self._session = session
        self._value_type = "text"
        self._m2m_items: List[Any] = []
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
        self.bool_combo.addItem(STRINGS.value_yes, "true")
        self.bool_combo.addItem(STRINGS.value_no, "false")
        self.enum_list = QListWidget()
        self.enum_list.setMaximumHeight(150)

        self.m2m_widget = QWidget()
        m2m_layout = QHBoxLayout(self.m2m_widget)
        m2m_layout.setContentsMargins(0, 0, 0, 0)
        self.m2m_list = QListWidget()
        self.m2m_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.m2m_list.setMaximumHeight(150)
        m2m_layout.addWidget(self.m2m_list, 1)
        m2m_buttons = QVBoxLayout()
        self.m2m_add_btn = QPushButton("+")
        self.m2m_add_btn.setToolTip(STRINGS.tooltip_add_items)
        self.m2m_add_btn.clicked.connect(self._m2m_add_items)
        self.m2m_remove_btn = QPushButton("−")
        self.m2m_remove_btn.setToolTip(STRINGS.tooltip_remove_items)
        self.m2m_remove_btn.clicked.connect(self._m2m_remove_items)
        m2m_buttons.addWidget(self.m2m_add_btn)
        m2m_buttons.addWidget(self.m2m_remove_btn)
        m2m_buttons.addStretch(1)
        m2m_layout.addLayout(m2m_buttons)

        for widget in (
            self.text_edit,
            self.date_edit,
            self.datetime_edit,
            self.number_edit,
            self.bool_combo,
            self.int_edit,
            self.enum_list,
            self.m2m_widget,
        ):
            self.value_stack.addWidget(widget)
        layout.addRow(STRINGS.label_value, self.value_stack)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

        self.column_combo.currentIndexChanged.connect(self._on_column_changed)
        self.operator_combo.currentIndexChanged.connect(self._on_operator_changed)

    def _on_column_changed(self) -> None:
        column_name = self.column_combo.currentData()
        self._value_type = _column_value_type(self.model_class, self.columns, column_name)
        nullable = resolve_nullable(self.model_class, column_name)
        self.operator_combo.clear()
        for operator, label in operators_for(self._value_type, nullable):
            self.operator_combo.addItem(label, operator)
        if self._value_type == "enum":
            self._reload_enum_choices(resolve_pack_enum(self.model_class, column_name))
        self.value_stack.setCurrentIndex(_VALUE_PAGES.get(self._value_type, 0))
        self._on_operator_changed()

    def _reload_enum_choices(self, pack_enum: Optional[str]) -> None:
        """Наполняет чек-лист вариантами пакетного перечисления."""
        self.enum_list.clear()
        if pack_enum is None:
            return
        for value, text in pack_enum_choices(pack_enum):
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.enum_list.addItem(item)

    # --- значение поля «многие ко многим» ---

    def _m2m_target(self) -> Optional[type]:
        """Возвращает класс связанной сущности текущей колонки."""
        return _column_filter_target(self.columns, self.column_combo.currentData())

    def _m2m_refresh(self) -> None:
        """Перестраивает список выбранных связанных записей (по алфавиту)."""
        self.m2m_list.clear()
        for instance in ItemsPickerDialog._ordered_instances(self._m2m_items):  # pylint: disable=protected-access
            item = QListWidgetItem(
                ItemsPickerDialog._item_text(instance)  # pylint: disable=protected-access
            )
            pk = sa_inspect(type(instance)).primary_key[0]
            item.setData(Qt.UserRole, str(getattr(instance, pk.name)))
            self.m2m_list.addItem(item)

    def _m2m_add_items(self) -> None:
        """Открывает диалог мультивыбора связанных записей («+»)."""
        target = self._m2m_target()
        if self._session is None or target is None:
            return
        pk = sa_inspect(target).primary_key[0]
        excluded = {
            getattr(instance, pk.name) for instance in self._m2m_items
        }
        dialog = ItemsPickerDialog(
            self._session,
            target,
            excluded_ids=excluded,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        known = {getattr(instance, pk.name) for instance in self._m2m_items}
        for instance in dialog.selected_items():
            if getattr(instance, pk.name) not in known:
                self._m2m_items.append(instance)
                known.add(getattr(instance, pk.name))
        self._m2m_refresh()

    def _m2m_remove_items(self) -> None:
        """Удаляет выделенные в списке записи («−»)."""
        selected_ids = {
            item.data(Qt.UserRole) for item in self.m2m_list.selectedItems()
        }
        if not selected_ids:
            return
        self._m2m_items = [
            instance
            for instance in self._m2m_items
            if str(getattr(instance, sa_inspect(type(instance)).primary_key[0].name))
            not in selected_ids
        ]
        self._m2m_refresh()

    def _on_operator_changed(self) -> None:
        """У унарных условий (пусто/не пусто) значение не требуется."""
        operator = self.operator_combo.currentData()
        self.value_stack.setEnabled(operator not in ("empty", "not_empty"))

    def _load_condition(self, condition: FilterCondition) -> None:
        """Заполняет редакторы существующим условием (режим изменения)."""
        column_index = self.column_combo.findData(condition.column_name)
        if column_index >= 0:
            self.column_combo.setCurrentIndex(column_index)
        operator_index = self.operator_combo.findData(condition.operator)
        if operator_index >= 0:
            self.operator_combo.setCurrentIndex(operator_index)
        if condition.operator in ("empty", "not_empty"):
            return
        if self._value_type == "enum":
            codes = {part.strip() for part in condition.value.split(",")}
            for row in range(self.enum_list.count()):
                item = self.enum_list.item(row)
                checked = str(item.data(Qt.UserRole)) in codes
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        elif self._value_type == "m2m":
            self._m2m_items = self._resolve_m2m_instances(condition.value)
            self._m2m_refresh()
        elif self._value_type == "date":
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

    def _resolve_m2m_instances(self, raw_value: str) -> List[Any]:
        """Возвращает связанные записи по идентификаторам условия.

        Без сессии или класса связанной сущности возвращает пустой список:
        значение сохранится, но редактор покажет пустой список.
        """
        target = self._m2m_target()
        raw_ids = parse_id_list(raw_value)
        if self._session is None or target is None or not raw_ids:
            return []
        pk = sa_inspect(target).primary_key[0]
        instances = (
            self._session.query(target)
            .filter(getattr(target, pk.name).in_(coerce_filter_ids(target, raw_ids)))
            .all()
        )
        by_id = {str(getattr(instance, pk.name)): instance for instance in instances}
        return [by_id[raw] for raw in raw_ids if raw in by_id]

    def _current_value(self) -> str:
        if self._value_type == "enum":
            codes = []
            for row in range(self.enum_list.count()):
                item = self.enum_list.item(row)
                if item.checkState() == Qt.Checked:
                    codes.append(str(item.data(Qt.UserRole)))
            return ",".join(codes)
        if self._value_type == "m2m":
            return ",".join(
                str(getattr(instance, sa_inspect(type(instance)).primary_key[0].name))
                for instance in self._m2m_items
            )
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
        operator = self.operator_combo.currentData()
        value = "" if operator in ("empty", "not_empty") else self._current_value()
        if operator not in ("empty", "not_empty"):
            if self._value_type in ("text", "enum", "m2m") and not value:
                return None
        return FilterCondition(
            column_name=self.column_combo.currentData(),
            operator=operator,
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
        session: Optional[Session] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.model_class = model_class
        self.columns = columns
        self.session = session
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
        if column is not None:
            header = column.header or field_short_label(
                self.model_class, condition.column_name
            )
        else:
            header = condition.column_name
        value_type = resolve_value_type(self.model_class, condition.column_name)

        row = QFrame()
        row.setFrameShape(QFrame.Box)
        row.mouseDoubleClickEvent = (
            lambda _event, item=condition: self._edit_filter(item)
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 4, 6, 4)

        pack_enum = resolve_pack_enum(self.model_class, condition.column_name)
        value_label = None
        if value_type == "m2m":
            value_label = ", ".join(
                resolve_m2m_labels(
                    self.session,
                    _column_filter_target(self.columns, condition.column_name),
                    condition.value,
                )
            )
        label = QLabel(
            condition.describe(header, value_type, pack_enum, value_label=value_label)
        )
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
        dialog = AddFilterDialog(
            self.model_class, self.columns, session=self.session, parent=self
        )
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
            self.model_class,
            self.columns,
            condition=condition,
            session=self.session,
            parent=self,
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
