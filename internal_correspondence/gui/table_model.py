"""Модель QTableView для отображения данных SQLAlchemy."""

from typing import Any, Callable, Dict, List, Optional, Type

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from sqlalchemy import asc, desc, func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import DEFAULT_PAGE_SIZE
from internal_correspondence.gui.filter_model import FilterCondition, resolve_value_type
from internal_correspondence.orm.base import Base
from internal_correspondence.gui.theme import current_theme
from internal_correspondence.orm.labels import field_short_label

# Роль для передачи значения оценки в делегат отображения
EVALUATION_VALUE_ROLE = Qt.UserRole + 1

class ColumnDef:
    """Описание столбца таблицы.

    Если заголовок не указан, он подставляется из русскоязычных меток
    поля ORM-модели (краткая метка, при отсутствии — полная).
    """

    def __init__(
        self,
        name: str,
        header: Optional[str] = None,
        width: int = 120,
        formatter: Optional[Callable[[Any], str]] = None,
    ) -> None:
        self.name = name
        self.header = header
        self.width = width
        self.formatter = formatter


class SqlAlchemyTableModel(QAbstractTableModel):
    """Модель таблицы для отображения ORM-объектов.

    Пагинация и сортировка по колонкам БД выполняются запросами;
    фильтры и сортировка по вычисляемым колонкам требуют загрузки
    записей в память.
    """

    def __init__(
        self,
        session: Session,
        model_class: Type[Base],
        columns: List[ColumnDef],
        branch_id: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.model_class = model_class
        self.columns = columns
        # Ограничение выборки филиалом (роль «филиал»): None — без ограничения
        self._branch_id = branch_id
        # Заголовки без явного значения подставляются из метаданных модели
        self._headers = [
            column.header if column.header is not None
            else field_short_label(model_class, column.name)
            for column in self.columns
        ]
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
                return current_theme().modified_row
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._headers[section]
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
            condition.column_name: resolve_value_type(
                self.model_class, condition.column_name
            )
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

    def pk_of(self, item: Base) -> Any:
        """Возвращает значение первичного ключа записи."""
        pk_column = sa_inspect(self.model_class).primary_key[0]
        return getattr(item, pk_column.name)

    def page_of(self, entity_pk: Any) -> Optional[int]:
        """Возвращает номер страницы (1-based) с записью с данным ключом.

        Учитывает фильтры, сортировку и ограничение филиалом; None —
        записи в текущей выборке нет.
        """
        if self._can_use_db_pagination():
            pk_column = sa_inspect(self.model_class).primary_key[0]
            query = self.session.query(pk_column)
            if self._branch_id is not None:
                query = query.filter(self.model_class.branch_id == self._branch_id)
            if self._order_by:
                column = getattr(self.model_class, self._order_by)
                query = query.order_by(desc(column) if self._order_desc else asc(column))
            keys = [row[0] for row in query.all()]
        else:
            keys = [self.pk_of(item) for item in self._filtered_items()]
        try:
            index = keys.index(entity_pk)
        except ValueError:
            return None
        return index // self._page_size + 1

    def row_of(self, entity_pk: Any) -> Optional[int]:
        """Возвращает индекс строки на текущей странице; None — записи нет."""
        for row, item in enumerate(self._items):
            if self.pk_of(item) == entity_pk:
                return row
        return None

    def refresh(self) -> None:
        """Обновляет данные модели из БД."""
        self.beginResetModel()
        try:
            if self._can_use_db_pagination():
                self._refresh_from_db()
            else:
                self._refresh_in_memory()
        finally:
            self.endResetModel()

    def _can_use_db_pagination(self) -> bool:
        """Проверяет, что все условия можно вычислить средствами БД."""
        if self._filter_text or self._filters:
            return False
        return not self._order_by or self._is_mapped_column(self._order_by)

    def _refresh_from_db(self) -> None:
        """Загружает одну страницу записей запросом с LIMIT/OFFSET."""
        query = self.session.query(self.model_class)
        count_query = self.session.query(func.count()).select_from(self.model_class)
        if self._branch_id is not None:
            query = query.filter(self.model_class.branch_id == self._branch_id)
            count_query = count_query.filter(
                self.model_class.branch_id == self._branch_id
            )
        if self._order_by:
            column = getattr(self.model_class, self._order_by)
            query = query.order_by(desc(column) if self._order_desc else asc(column))
        self._total = count_query.scalar() or 0
        offset = (self._page - 1) * self._page_size
        self._items = query.limit(self._page_size).offset(offset).all()

    def _refresh_in_memory(self) -> None:
        """Загружает записи в память для фильтров по вычисляемым значениям."""
        query = self.session.query(self.model_class)
        if self._branch_id is not None:
            query = query.filter(self.model_class.branch_id == self._branch_id)
        db_order = bool(self._order_by) and self._is_mapped_column(self._order_by)
        if db_order:
            column = getattr(self.model_class, self._order_by)
            query = query.order_by(desc(column) if self._order_desc else asc(column))

        all_items = self._filtered_items(query.all())
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
        self._items = all_items[start : start + self._page_size]

    def _filtered_items(self, items: Optional[List[Base]] = None) -> List[Base]:
        """Применяет текстовый и структурированный фильтры к списку записей."""
        if items is None:
            query = self.session.query(self.model_class)
            if self._branch_id is not None:
                query = query.filter(self.model_class.branch_id == self._branch_id)
            items = query.all()
        all_items = list(items)
        if self._filter_text:
            all_items = [
                item
                for item in all_items
                if self._filter_text.lower() in self._row_text(item).lower()
            ]
        if self._filters:
            all_items = [item for item in all_items if self._matches_filters(item)]
        return all_items

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


class DocumentsTableModel(SqlAlchemyTableModel):
    """Модель таблицы научных материалов и телеграмм.

    Дополнительно к базовому поведению выделяет цветом записи без
    входящего номера (менее ярко, чем неэкспортированные изменения).
    """

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if role == Qt.BackgroundRole and index.isValid():
            item = self._items[index.row()]
            theme = current_theme()
            if getattr(item, "change_id", None) is not None:
                return theme.modified_row
            if hasattr(item, "incoming_number") and not item.incoming_number:
                return theme.no_incoming_row
        return super().data(index, role)
