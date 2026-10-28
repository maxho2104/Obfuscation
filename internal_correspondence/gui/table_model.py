"""Модель QTableView для отображения данных SQLAlchemy."""

from typing import Any, Callable, Dict, List, Optional, Type

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from sqlalchemy import asc, desc
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import DEFAULT_PAGE_SIZE
from internal_correspondence.gui.filter_model import FilterCondition, resolve_value_type
from internal_correspondence.orm.base import Base

# Роль для передачи значения оценки в делегат отображения
EVALUATION_VALUE_ROLE = Qt.UserRole + 1


class ColumnDef:
    """Описание столбца таблицы."""

    def __init__(
        self,
        name: str,
        header: str,
        width: int = 120,
        formatter: Optional[Callable[[Any], str]] = None,
    ) -> None:
        self.name = name
        self.header = header
        self.width = width
        self.formatter = formatter


class SqlAlchemyTableModel(QAbstractTableModel):
    """Модель таблицы для отображения ORM-объектов."""

    def __init__(
        self,
        session: Session,
        model_class: Type[Base],
        columns: List[ColumnDef],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.model_class = model_class
        self.columns = columns
        self._items: List[Base] = []
        self._page = 1
        self._page_size = DEFAULT_PAGE_SIZE
        self._total = 0
        self._order_by: Optional[str] = None
        self._order_desc = False
        self._filter_text: Optional[str] = None
        self._filters: List[FilterCondition] = []
        self._filter_types: Dict[str, str] = {}
        self.refresh()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        column = self.columns[index.column()]

        if role == Qt.DisplayRole:
            value = self._get_value(item, column.name)
            if column.formatter:
                return column.formatter(value)
            return self._format_value(value)

        if role == EVALUATION_VALUE_ROLE and column.name == "evaluation_display":
            evaluation = getattr(item, "latest_evaluation", None)
            return evaluation.value if evaluation is not None else None

        if role == Qt.BackgroundRole:
            # Выделение изменённых, но не экспортированных записей
            if hasattr(item, "change_id") and getattr(item, "change_id") is not None:
                from PyQt5.QtGui import QColor
                return QColor(255, 230, 180)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns[section].header
        return None

    def sort(self, column_index: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        if column_index < 0 or column_index >= len(self.columns):
            return
        self._order_by = self.columns[column_index].name
        self._order_desc = order == Qt.DescendingOrder
        self.refresh()

    def set_filter(self, text: Optional[str]) -> None:
        """Устанавливает текстовый фильтр по строковому представлению строк."""
        self._filter_text = text.strip() if text else None
        self._page = 1
        self.refresh()

    def filters(self) -> List[FilterCondition]:
        """Возвращает список применённых условий фильтрации."""
        return list(self._filters)

    def set_filters(self, filters: List[FilterCondition]) -> None:
        """Устанавливает структурированные условия фильтрации."""
        self._filters = list(filters)
        self._filter_types = {
            condition.column_name: resolve_value_type(self.model_class, condition.column_name)
            for condition in self._filters
        }
        self._page = 1
        self.refresh()

    def set_page(self, page: int) -> None:
        """Переходит на указанную страницу."""
        self._page = max(1, page)
        self.refresh()

    def page(self) -> int:
        return self._page

    def page_size(self) -> int:
        return self._page_size

    def total(self) -> int:
        return self._total

    def total_pages(self) -> int:
        if self._page_size == 0:
            return 1
        return (self._total + self._page_size - 1) // self._page_size

    def item_at(self, row: int) -> Optional[Base]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def refresh(self) -> None:
        """Обновляет данные модели из БД."""
        self.beginResetModel()
        query = self.session.query(self.model_class)
        db_order = bool(self._order_by) and self._is_mapped_column(self._order_by)
        if db_order:
            column = getattr(self.model_class, self._order_by)
            query = query.order_by(desc(column) if self._order_desc else asc(column))

        all_items = query.all()
        if self._filter_text:
            all_items = [item for item in all_items if self._filter_text.lower() in self._row_text(item).lower()]
        if self._filters:
            all_items = [item for item in all_items if self._matches_filters(item)]
        if self._order_by and not db_order:
            sort_column = next(
                (column for column in self.columns if column.name == self._order_by),
                None,
            )
            if sort_column is not None:
                all_items.sort(
                    key=lambda item: self._sort_text(item, sort_column),
                    reverse=self._order_desc,
                )

        self._total = len(all_items)
        start = (self._page - 1) * self._page_size
        self._items = all_items[start:start + self._page_size]
        self.endResetModel()

    def _is_mapped_column(self, name: str) -> bool:
        """Проверяет, является ли атрибут (включая вложенные) колонкой ORM."""
        try:
            mapper = sa_inspect(self.model_class)
            parts = name.split(".")
            for part in parts[:-1]:
                attribute = mapper.attrs.get(part)
                target_mapper = getattr(attribute, "mapper", None)
                if target_mapper is None:
                    return False
                mapper = target_mapper
            return parts[-1] in mapper.columns
        except Exception:  # pylint: disable=broad-except
            return False

    def _sort_text(self, item: Base, column: ColumnDef) -> str:
        """Возвращает строковое значение ячейки для сортировки в памяти."""
        value = self._get_value(item, column.name)
        if column.formatter:
            return str(column.formatter(value)).lower()
        return self._format_value(value).lower()

    def _get_value(self, item: Base, name: str) -> Any:
        """Возвращает значение атрибута по имени (включая вложенные через точку)."""
        value = item
        for part in name.split("."):
            if value is None:
                return None
            value = getattr(value, part, None)
        return value

    def _format_value(self, value: Any) -> str:
        """Форматирует значение ячейки для отображения."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Да" if value else "Нет"
        return str(value)

    def _row_text(self, item: Base) -> str:
        """Возвращает полное строковое представление строки для фильтрации."""
        parts = []
        for column in self.columns:
            value = self._get_value(item, column.name)
            if column.formatter:
                parts.append(column.formatter(value))
            else:
                parts.append(self._format_value(value))
        return " ".join(parts)

    def _matches_filters(self, item: Base) -> bool:
        """Проверяет, удовлетворяет ли запись всем условиям фильтрации."""
        for condition in self._filters:
            value = self._get_value(item, condition.column_name)
            value_type = self._filter_types.get(condition.column_name, "text")
            if not condition.matches(value, value_type):
                return False
        return True
