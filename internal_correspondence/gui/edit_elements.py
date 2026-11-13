"""Элементы редактирования полей сущностей для диалогов.

Каждый элемент получает при создании переменную сущности
(``mapped_column`` или relationship SQLAlchemy) и через единый интерфейс
умеет отображать и изменять её значение:

- ``load_value(entity)`` / ``collect_data(target)`` — чтение/запись;
- ``validate()`` — проверка введённого значения (сообщение или None);
- ``label_widget()`` — метка с выделением обязательных (жирным, «*»
  красным) и уникальных (подчёркиванием) полей;
- ``valueChanged`` — сигнал об изменении значения (для условной
  видимости полей).

Простые элементы выбираются фабрикой :func:`create_element` по типу
колонки; связи 1→N и N→N, расширенные таблицы связности и пары
«номер и дата» — отдельными классами.
"""

from datetime import date, datetime, time
from typing import Any, Callable, Dict, List, Optional, Sequence

import sqlalchemy as sa
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from internal_correspondence.core.enum_registry import pack_enum_choices
from internal_correspondence.orm.base import IntEnumType
from internal_correspondence.orm.labels import (
    entity_label,
    field_label,
    field_required,
    field_unique,
)
from internal_correspondence.utils.string_resources import STRINGS

# Порог количества вариантов, после которого комбобокс 1→N становится
# редактируемым с подсказкой (QCompleter)
COMPLETER_THRESHOLD = 10

# «Пустая» дата в календарных редакторах (спец. значение QDateEdit)
EMPTY_DATE = date(1900, 1, 1)


def is_empty_date(value: Optional[date]) -> bool:
    """Проверяет, является ли дата пустой (не заданной)."""
    return value is None or value <= EMPTY_DATE


def display_name(instance: Any) -> str:
    """Возвращает представление связанной сущности для списков и комбобоксов."""
    for attribute in ("name", "short_name"):
        value = getattr(instance, attribute, None)
        if value:
            return str(value)
    return str(getattr(instance, "id", instance))


def format_report_addresses(addresses: Sequence) -> str:
    """Форматирует адресацию доклада: «ИД+» для доложенных, через запятую."""
    parts = []
    for address in sorted(addresses or [], key=lambda item: item.leader_id):
        suffix = "+" if address.report_date is not None else ""
        parts.append(f"{address.leader_id}{suffix}")
    return ", ".join(parts)


class EditElement(QWidget):
    """Базовый (абстрактный) элемент редактирования переменной сущности.

    Args:
        attribute: Переменная сущности (mapped_column или relationship).
        parent: Родительский виджет.
        label: Переопределение метки элемента (по умолчанию — из info).
    """

    valueChanged = pyqtSignal()

    def __init__(self, attribute, parent=None, label: Optional[str] = None) -> None:
        super().__init__(parent)
        self.attribute = attribute
        self.model_class = attribute.class_
        self.field_name: str = attribute.key
        self._label_override = label
        self.editor = self._build_editor()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor, 1)

    # --- построение и доступ к редактору ---

    def _build_editor(self) -> QWidget:
        """Создаёт редактор значения (переопределяется наследниками)."""
        raise NotImplementedError

    def label_text(self) -> str:
        """Возвращает текст метки элемента."""
        if self._label_override is not None:
            return self._label_override
        return field_label(self.model_class, self.field_name)

    def is_required(self) -> bool:
        """Проверяет обязательность заполнения переменной."""
        return field_required(self.model_class, self.field_name)

    def is_unique(self) -> bool:
        """Проверяет, входит ли колонка в ограничение уникальности."""
        return field_unique(self.model_class, self.field_name)

    def label_widget(self) -> QLabel:
        """Создаёт метку элемента с выделением обязательных/уникальных полей."""
        label = QLabel(self.label_text())
        font = label.font()
        if self.is_required():
            font.setBold(True)
            label.setText(f"{self.label_text()} <span style='color:#c0392b'>*</span>")
            label.setTextFormat(Qt.RichText)
        if self.is_unique():
            font.setUnderline(True)
        label.setFont(font)
        label.setToolTip(self.label_text())
        return label

    # --- значение ---

    def load_value(self, entity) -> None:
        """Загружает значение переменной сущности в редактор."""
        self.set_value(getattr(entity, self.field_name, None))

    def set_value(self, value: Any) -> None:
        """Устанавливает значение редактора."""
        raise NotImplementedError

    def value(self) -> Any:
        """Возвращает значение редактора."""
        raise NotImplementedError

    def collect_data(self, target: Dict[str, Any]) -> None:
        """Записывает значение редактора в словарь данных."""
        target[self.field_name] = self.value()

    # --- проверка ---

    def validate(self) -> Optional[str]:
        """Проверяет введённое значение; возвращает сообщение или None."""
        if self.is_required() and self.is_empty():
            return STRINGS.msg_required_field.format(label=self.label_text())
        return None

    def is_empty(self) -> bool:
        """Проверяет, оставлено ли значение незаполненным."""
        return self.value() in (None, "")

    def focus_editor(self) -> None:
        """Передаёт фокус редактору элемента."""
        self.editor.setFocus()


class LineEditElement(EditElement):
    """Редактирование строкового поля (однострочного)."""

    def _build_editor(self) -> QWidget:
        self.line_edit = QLineEdit()
        self.line_edit.textChanged.connect(self.valueChanged)
        return self.line_edit

    def set_value(self, value: Any) -> None:
        self.line_edit.setText("" if value is None else str(value))

    def value(self) -> Any:
        return self.line_edit.text().strip() or None


class TextEditElement(EditElement):
    """Редактирование многострочного текстового поля."""

    def _build_editor(self) -> QWidget:
        self.text_edit = QPlainTextEdit()
        self.text_edit.setMaximumHeight(80)
        self.text_edit.textChanged.connect(self.valueChanged)
        return self.text_edit

    def set_value(self, value: Any) -> None:
        self.text_edit.setPlainText("" if value is None else str(value))

    def value(self) -> Any:
        return self.text_edit.toPlainText().strip() or None


class IntEditElement(EditElement):
    """Редактирование целочисленного поля."""

    def _build_editor(self) -> QWidget:
        self.spin_box = QSpinBox()
        # Значение, равное минимуму, считается «пустым» (specialValueText)
        self.spin_box.setRange(-2_000_000_000, 2_000_000_000)
        self.spin_box.setSpecialValueText("")
        self.spin_box.valueChanged.connect(self.valueChanged)
        return self.spin_box

    def set_value(self, value: Any) -> None:
        if value is None:
            self.spin_box.setValue(self.spin_box.minimum())
        else:
            self.spin_box.setValue(int(value))

    def value(self) -> Any:
        if self.spin_box.value() == self.spin_box.minimum():
            return None
        return self.spin_box.value()

    def is_empty(self) -> bool:
        return self.value() is None


class FloatEditElement(EditElement):
    """Редактирование числового поля с плавающей точкой."""

    def _build_editor(self) -> QWidget:
        self.double_spin = QDoubleSpinBox()
        self.double_spin.setDecimals(2)
        self.double_spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self.double_spin.valueChanged.connect(self.valueChanged)
        return self.double_spin

    def set_value(self, value: Any) -> None:
        self.double_spin.setValue(float(value) if value is not None else 0.0)

    def value(self) -> Any:
        if self.double_spin.value() == 0.0:
            return None
        return self.double_spin.value()

    def is_empty(self) -> bool:
        return self.value() is None


class BoolEditElement(EditElement):
    """Редактирование логического поля."""

    def _build_editor(self) -> QWidget:
        self.check_box = QCheckBox()
        self.check_box.toggled.connect(self.valueChanged)
        return self.check_box

    def set_value(self, value: Any) -> None:
        self.check_box.setChecked(bool(value))

    def value(self) -> Any:
        return self.check_box.isChecked()

    def label_widget(self) -> QLabel:
        # Чекбокс сам является подписью — пустая метка слева
        label = QLabel("")
        return label

    def is_empty(self) -> bool:
        return False


class DateEditElement(EditElement):
    """Редактирование поля-даты (допускает пустое значение)."""

    def _build_editor(self) -> QWidget:
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setSpecialValueText("")
        self.date_edit.setMinimumDate(EMPTY_DATE)
        self.date_edit.setDate(EMPTY_DATE)
        self.date_edit.dateChanged.connect(self.valueChanged)
        return self.date_edit

    def set_value(self, value: Any) -> None:
        if is_empty_date(value):
            self.date_edit.setDate(EMPTY_DATE)
        else:
            self.date_edit.setDate(value)

    def value(self) -> Any:
        value = self.date_edit.date().toPyDate()
        return None if is_empty_date(value) else value

    def is_empty(self) -> bool:
        return self.value() is None


class TimeEditElement(EditElement):
    """Редактирование поля-времени."""

    def _build_editor(self) -> QWidget:
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.timeChanged.connect(self.valueChanged)
        return self.time_edit

    def set_value(self, value: Any) -> None:
        if value is not None:
            self.time_edit.setTime(value)

    def value(self) -> Any:
        return self.time_edit.time().toPyTime()


class DateTimeEditElement(EditElement):
    """Редактирование поля «дата и время» (допускает пустое значение)."""

    def _build_editor(self) -> QWidget:
        self.datetime_edit = QDateTimeEdit()
        self.datetime_edit.setCalendarPopup(True)
        self.datetime_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.datetime_edit.setSpecialValueText("")
        self.datetime_edit.setMinimumDate(EMPTY_DATE)
        self.datetime_edit.setDateTime(self.datetime_edit.minimumDateTime())
        self.datetime_edit.dateTimeChanged.connect(self.valueChanged)
        return self.datetime_edit

    def set_value(self, value: Any) -> None:
        if value in (None, "") or (
            isinstance(value, datetime) and value.date() <= EMPTY_DATE
        ):
            self.datetime_edit.setDateTime(self.datetime_edit.minimumDateTime())
        else:
            self.datetime_edit.setDateTime(value)

    def value(self) -> Any:
        value = self.datetime_edit.dateTime().toPyDateTime()
        if value.date() <= EMPTY_DATE:
            return None
        return value

    def is_empty(self) -> bool:
        return self.value() is None


class EnumEditElement(EditElement):
    """Редактирование поля-перечисления (QComboBox из пакета предметной области)."""

    def __init__(self, attribute, pack_enum: str, parent=None, label=None) -> None:
        self.pack_enum = pack_enum
        super().__init__(attribute, parent=parent, label=label)

    def _build_editor(self) -> QWidget:
        self.combo = QComboBox()
        for value, text in pack_enum_choices(self.pack_enum):
            self.combo.addItem(text, value)
        self.combo.currentIndexChanged.connect(self.valueChanged)
        return self.combo

    def set_value(self, value: Any) -> None:
        index = self.combo.findData(int(value) if value is not None else None)
        if index >= 0:
            self.combo.setCurrentIndex(index)

    def value(self) -> Any:
        return self.combo.currentData()


class FkComboEditElement(EditElement):
    """Редактирование поля внешнего ключа (связь 1→N) через QComboBox.

    Нулевое значение (при допускающем NULL FK) — первым элементом списка.
    При количестве вариантов свыше :data:`COMPLETER_THRESHOLD` комбобокс
    становится редактируемым с подсказкой (QCompleter).
    """

    def __init__(self, attribute, session: Session, parent=None, label=None) -> None:
        self.session = session
        column = attribute.property.columns[0]
        self.nullable = column.nullable
        self._related_class = self._resolve_related_class(attribute)
        super().__init__(attribute, parent=parent, label=label)

    @staticmethod
    def _resolve_related_class(attribute) -> type:
        """Возвращает класс связанной сущности по FK-колонке."""
        mapper = sa_inspect(attribute.class_)
        column = attribute.property.columns[0]
        for relationship in mapper.relationships:
            if (
                relationship.direction.name == "MANYTOONE"
                and column in relationship.local_columns
            ):
                return relationship.mapper.class_
        raise ValueError(f"Колонка {column.name} не является внешним ключом")

    def _build_editor(self) -> QWidget:
        self.combo = QComboBox()
        self._items: Dict[Any, Any] = {}
        if self.nullable:
            self.combo.addItem("—", None)
        related_class = self._related_class
        query = self.session.query(related_class)
        order_attr = getattr(related_class, "name", None) or getattr(
            related_class, "short_name", None
        )
        if order_attr is not None:
            query = query.order_by(order_attr)
        items = query.all()
        for instance in items:
            self.combo.addItem(display_name(instance), instance.id)
            self._items[instance.id] = instance

        if len(items) > COMPLETER_THRESHOLD:
            self.combo.setEditable(True)
            completer = self.combo.completer()
            completer.setFilterMode(Qt.MatchContains)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.combo.currentIndexChanged.connect(self.valueChanged)
        return self.combo

    def set_value(self, value: Any) -> None:
        index = self.combo.findData(value)
        if index >= 0:
            self.combo.setCurrentIndex(index)

    def value(self) -> Any:
        return self.combo.currentData()

    def current_instance(self) -> Any:
        """Возвращает выбранный экземпляр связанной сущности (или None)."""
        return self._items.get(self.combo.currentData())


class ItemsPickerDialog(QDialog):
    """Диалог выбора записей связанной сущности (мультивыбор и фильтрация)."""

    def __init__(
        self,
        session: Session,
        model_class: type,
        excluded_ids: Optional[Sequence] = None,
        query_factory: Optional[Callable[[Session], Any]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.dialog_pick_title.format(entity=entity_label(model_class, plural=True)))
        self.setMinimumSize(500, 400)
        self._items: Dict[Any, Any] = {}
        self._setup_ui()
        self._load_items(session, model_class, excluded_ids or (), query_factory)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(STRINGS.placeholder_search)
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list_widget, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _load_items(self, session, model_class, excluded_ids, query_factory) -> None:
        query = (
            query_factory(session)
            if query_factory is not None
            else session.query(model_class)
        )
        if excluded_ids:
            pk = sa_inspect(model_class).primary_key[0].name
            query = query.filter(getattr(model_class, pk).notin_(list(excluded_ids)))
        self.list_widget.clear()
        for instance in query.all():
            text = self._item_text(instance)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, getattr(instance, "id"))
            self._items[getattr(instance, "id")] = instance
            self.list_widget.addItem(item)

    @staticmethod
    def _item_text(instance: Any) -> str:
        """Формирует текст строки с учётом специфики сущности."""
        if hasattr(instance, "display_name"):
            text = instance.display_name()
            department = getattr(instance, "department", None)
            if department is not None:
                text = f"{text} — {department.short_name or department.name}"
            if getattr(instance, "active", True) is False:
                text = f"{text} (неактивен)"
            return text
        return display_name(instance)

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def selected_items(self) -> List[Any]:
        """Возвращает выбранные экземпляры связанной сущности."""
        result = []
        for item in self.list_widget.selectedItems():
            instance = self._items.get(item.data(Qt.UserRole))
            if instance is not None:
                result.append(instance)
        return result


class ManyToManyEditElement(EditElement):
    """Редактирование связи N→N: список с кнопками «+» и «−».

    По нажатию «+» открывается диалог с записями, которые ещё можно
    добавить (без уже добавленных, с мультивыбором и фильтрацией);
    по нажатию «−» выбранные в списке записи удаляются.
    """

    def __init__(
        self,
        attribute,
        session: Session,
        parent=None,
        label=None,
        query_factory: Optional[Callable[[Session], Any]] = None,
    ) -> None:
        self.session = session
        self.query_factory = query_factory
        self._items: List[Any] = []
        super().__init__(attribute, parent=parent, label=label)

    def _build_editor(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setMinimumHeight(90)
        self.list_widget.setMaximumHeight(140)
        layout.addWidget(self.list_widget, 1)

        buttons = QVBoxLayout()
        self.add_button = QPushButton("+")
        self.add_button.setToolTip(STRINGS.tooltip_add_items)
        self.add_button.clicked.connect(self._add_items)
        self.remove_button = QPushButton("−")
        self.remove_button.setToolTip(STRINGS.tooltip_remove_items)
        self.remove_button.clicked.connect(self._remove_items)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return container

    def related_class(self) -> type:
        """Возвращает класс связанной сущности."""
        return self.attribute.property.mapper.class_

    def set_value(self, value: Any) -> None:
        self._items = list(value or [])
        self._refresh_list()

    def value(self) -> Any:
        return list(self._items)

    def collect_data(self, target: Dict[str, Any]) -> None:
        target[self.field_name] = list(self._items)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for instance in self._items:
            item = QListWidgetItem(ItemsPickerDialog._item_text(instance))
            item.setData(Qt.UserRole, getattr(instance, "id"))
            self.list_widget.addItem(item)

    def _add_items(self) -> None:
        dialog = ItemsPickerDialog(
            self.session,
            self.related_class(),
            excluded_ids=[getattr(item, "id") for item in self._items],
            query_factory=self.query_factory,
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        known = {getattr(item, "id") for item in self._items}
        for instance in dialog.selected_items():
            if getattr(instance, "id") not in known:
                self._items.append(instance)
                known.add(getattr(instance, "id"))
        self._refresh_list()
        self.valueChanged.emit()

    def _remove_items(self) -> None:
        selected_ids = {
            item.data(Qt.UserRole) for item in self.list_widget.selectedItems()
        }
        if not selected_ids:
            return
        self._items = [
            item for item in self._items if getattr(item, "id") not in selected_ids
        ]
        self._refresh_list()
        self.valueChanged.emit()


class ReportAddressesEditElement(ManyToManyEditElement):
    """Редактирование адресации доклада (расширенная таблица связности).

    Вместо списка — таблица: колонка «Руководитель» (текст «ИД+», если
    дата доклада заполнена) и редактируемая колонка «Дата доклада»
    (пустая дата допускается — «ещё не доложено»). «+» добавляет выбранных
    руководителей с пустой датой, «−» удаляет выбранные строки.
    """

    def _build_editor(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(
            [
                field_label(self.related_class(), "leader_id"),
                field_label(self.related_class(), "report_date"),
            ]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(90)
        self.table.setMaximumHeight(140)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        buttons = QVBoxLayout()
        self.add_button = QPushButton("+")
        self.add_button.setToolTip(STRINGS.tooltip_add_items)
        self.add_button.clicked.connect(self._add_items)
        self.remove_button = QPushButton("−")
        self.remove_button.setToolTip(STRINGS.tooltip_remove_items)
        self.remove_button.clicked.connect(self._remove_items)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return container

    def _address_rows(self) -> List[Any]:
        return list(self._items)

    def set_value(self, value: Any) -> None:
        self._items = list(value or [])
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self.table.setRowCount(0)
        ordered = sorted(self._items, key=lambda item: item.leader_id)
        for address in ordered:
            self._append_row(address.leader_id, address.report_date)

    def _append_row(self, leader_id: str, report_date: Optional[date]) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        leader_item = QTableWidgetItem(
            f"{leader_id}+" if report_date is not None else leader_id
        )
        leader_item.setFlags(leader_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, leader_item)

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd.MM.yyyy")
        date_edit.setSpecialValueText(STRINGS.date_not_set)
        date_edit.setMinimumDate(EMPTY_DATE)
        date_edit.setDate(EMPTY_DATE if report_date is None else report_date)
        date_edit.dateChanged.connect(
            lambda _value, row=row: self._on_date_changed(row)
        )
        self.table.setCellWidget(row, 1, date_edit)

    def _on_date_changed(self, row: int) -> None:
        """Синхронизирует метку руководителя («+») с датой строки."""
        leader_item = self.table.item(row, 0)
        date_edit = self.table.cellWidget(row, 1)
        if leader_item is None or date_edit is None:
            return
        leader_id = leader_item.text().rstrip("+")
        leader_item.setText(
            f"{leader_id}+" if date_edit.date().toPyDate() > EMPTY_DATE else leader_id
        )
        self.valueChanged.emit()

    def collect_data(self, target: Dict[str, Any]) -> None:
        """Собирает записи адресации; существующие сохраняют идентичность."""
        result = []
        existing = {
            address.leader_id: address
            for address in self._items
        }
        for row in range(self.table.rowCount()):
            leader_item = self.table.item(row, 0)
            date_edit = self.table.cellWidget(row, 1)
            if leader_item is None or date_edit is None:
                continue
            leader_id = leader_item.text().rstrip("+")
            report_date = date_edit.date().toPyDate()
            if report_date <= EMPTY_DATE:
                report_date = None
            address = existing.get(leader_id)
            if address is None:
                address = self._new_address(leader_id, report_date)
            else:
                address.report_date = report_date
            result.append(address)
        target[self.field_name] = result

    @staticmethod
    def _new_address(leader_id: str, report_date: Optional[date]):
        """Создаёт новую запись адресации (ленивый импорт против циклов)."""
        from internal_correspondence.orm.models import ReportAddress

        return ReportAddress(leader_id=leader_id, report_date=report_date)

    def _add_items(self) -> None:
        from internal_correspondence.orm.models import Leader

        dialog = ItemsPickerDialog(
            self.session,
            Leader,
            excluded_ids=[address.leader_id for address in self._items],
            parent=self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        for leader in dialog.selected_items():
            self._items.append(
                self._new_address(leader_id=leader.id, report_date=None)
            )
        self._rebuild_table()
        self.valueChanged.emit()

    def _remove_items(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.table.selectedIndexes()}, reverse=True
        )
        if not selected_rows:
            return
        removed_ids = set()
        for row in selected_rows:
            leader_item = self.table.item(row, 0)
            if leader_item is not None:
                removed_ids.add(leader_item.text().rstrip("+"))
            self.table.removeRow(row)
        self._items = [
            address
            for address in self._items
            if address.leader_id not in removed_ids
        ]
        self.valueChanged.emit()


class NumberDateEditElement(EditElement):
    """Пара «номер и дата» в одной строке (два связанных редактора).

    Args:
        number_attribute: Переменная колонки номера.
        date_attribute: Переменная колонки даты.
        required: Требовать оба значения; иначе допускается пара
            «оба пустые», но не одно значение без другого.
    """

    def __init__(
        self,
        number_attribute,
        date_attribute,
        parent=None,
        label=None,
        required: bool = False,
    ) -> None:
        self.number_attribute = number_attribute
        self.date_attribute = date_attribute
        self._required = required
        super().__init__(number_attribute, parent=parent, label=label)

    def _build_editor(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.number_edit = QLineEdit()
        self.number_edit.setMaximumWidth(150)
        self.number_edit.textChanged.connect(self._on_number_changed)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        self.date_edit.setSpecialValueText("")
        self.date_edit.setMinimumDate(EMPTY_DATE)
        self.date_edit.setDate(EMPTY_DATE)
        layout.addWidget(self.number_edit)
        layout.addWidget(self.date_edit)
        layout.addStretch(1)
        return container

    def _on_number_changed(self, text: str) -> None:
        """Дата активна только при заполненном номере."""
        self.date_edit.setEnabled(bool(text.strip()))
        self.valueChanged.emit()

    def is_required(self) -> bool:
        return self._required

    def is_unique(self) -> bool:
        # Уникальность пары проверяется составным ограничением модели;
        # подчёркиваем обе метки
        return field_unique(self.model_class, self.number_attribute.key)

    def label_text(self) -> str:
        if self._label_override is not None:
            return self._label_override
        number_label = field_label(self.model_class, self.number_attribute.key)
        date_label = field_label(self.model_class, self.date_attribute.key)
        return f"{number_label} / {date_label}"

    def set_value(self, value: Any) -> None:
        raise NotImplementedError("Используйте load_value(entity)")

    def load_value(self, entity) -> None:
        number = getattr(entity, self.number_attribute.key, None)
        value = getattr(entity, self.date_attribute.key, None)
        self.number_edit.setText(number or "")
        self.date_edit.setDate(EMPTY_DATE if is_empty_date(value) else value)

    def value(self) -> Any:
        raise NotImplementedError("Используйте collect_data(target)")

    def collect_data(self, target: Dict[str, Any]) -> None:
        number = self.number_edit.text().strip() or None
        value = self.date_edit.date().toPyDate()
        target[self.number_attribute.key] = number
        target[self.date_attribute.key] = (
            None if is_empty_date(value) else value
        )

    def validate(self) -> Optional[str]:
        number = self.number_edit.text().strip() or None
        value = self.date_edit.date().toPyDate()
        value = None if is_empty_date(value) else value
        label = self.label_text()
        if self._required:
            if number is None:
                return STRINGS.msg_required_field.format(label=label)
            if value is None:
                return STRINGS.msg_required_field.format(label=label)
            return None
        if (number is None) != (value is None):
            return STRINGS.msg_invalid_field.format(
                label=label, error=STRINGS.msg_number_date_together
            )
        return None

    def is_empty(self) -> bool:
        return not self.number_edit.text().strip()

    def focus_editor(self) -> None:
        self.number_edit.setFocus()


# Карта пакетных перечислений: имя IntEnum-класса → ключ перечисления пакета
_ENUM_PACK_KEYS: Dict[str, str] = {
    "MaterialType": "material_type",
    "TelegramType": "telegram_type",
    "TelegramReportType": "telegram_report_type",
    "ScientificTaskType": "scientific_task_type",
    "SourceType": "source_type",
    "EvaluationValue": "evaluation_value",
}


def create_element(
    attribute,
    session: Optional[Session] = None,
    parent=None,
    label: Optional[str] = None,
) -> EditElement:
    """Создаёт элемент редактирования по переменной сущности.

    Колонки отображаются по типу (простые значения, перечисления,
    внешние ключи); множественные связи (N→N) — элементом списка.
    """
    prop = attribute.property
    if hasattr(prop, "columns"):
        column = prop.columns[0]
        if isinstance(column.type, IntEnumType):
            pack_key = _ENUM_PACK_KEYS.get(column.type._enum_class.__name__)
            if pack_key:
                return EnumEditElement(attribute, pack_key, parent=parent, label=label)
        if column.foreign_keys:
            if session is None:
                raise ValueError(
                    f"Для колонки {attribute.key} нужна сессия (связь 1→N)"
                )
            return FkComboEditElement(attribute, session, parent=parent, label=label)
        if isinstance(column.type, sa.Boolean):
            return BoolEditElement(attribute, parent=parent, label=label)
        if isinstance(column.type, sa.Date):
            return DateEditElement(attribute, parent=parent, label=label)
        if isinstance(column.type, sa.DateTime):
            return DateTimeEditElement(attribute, parent=parent, label=label)
        if isinstance(column.type, sa.Time):
            return TimeEditElement(attribute, parent=parent, label=label)
        if isinstance(column.type, sa.Integer):
            return IntEditElement(attribute, parent=parent, label=label)
        if isinstance(column.type, sa.Numeric) or isinstance(column.type, sa.Float):
            return FloatEditElement(attribute, parent=parent, label=label)
        if isinstance(column.type, sa.Text):
            return TextEditElement(attribute, parent=parent, label=label)
        return LineEditElement(attribute, parent=parent, label=label)
    # Связь
    if prop.uselist:
        if session is None:
            raise ValueError(
                f"Для связи {attribute.key} нужна сессия (связь N→N)"
            )
        return ManyToManyEditElement(attribute, session, parent=parent, label=label)
    raise ValueError(f"Не удалось построить элемент для {attribute.key}")
