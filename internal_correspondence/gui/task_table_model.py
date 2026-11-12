"""Модель таблицы научных задач для модуля распределения."""

from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtGui import QBrush

from internal_correspondence.core.domain_pack import enum_label
from internal_correspondence.gui.theme import current_theme
from internal_correspondence.orm.labels import field_short_label
from internal_correspondence.orm.models import ScientificTask

# Поля таблицы и их ширины по умолчанию
TASK_COLUMNS: Sequence[Tuple[str, int]] = (
    ("id", 90),
    ("name", 260),
    ("type", 110),
    ("start_date", 100),
    ("end_date", 100),
    ("partial_threshold", 120),
    ("full_threshold", 120),
    ("comment", 200),
)

TASK_ID_ROLE = Qt.UserRole + 1


def _format_number(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.2f}".replace(".", ",")


def _format_date(value: Optional[date]) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


class TaskTableModel(QAbstractTableModel):
    """Таблица задач с поиском, сортировкой и подсветкой нераспределённых."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tasks: List[ScientificTask] = []
        self._visible: List[ScientificTask] = []
        self._search = ""
        self._undistributed: Set[str] = set()
        self._sort_column = 0
        self._sort_order = Qt.AscendingOrder

    # ------------------------------------------------------------------
    # Наполнение
    # ------------------------------------------------------------------

    def set_tasks(
        self,
        tasks: Sequence[ScientificTask],
        undistributed: Optional[Set[str]] = None,
    ) -> None:
        """Задаёт задачи и множество нераспределённых кодов."""
        self.beginResetModel()
        self._tasks = list(tasks)
        self._undistributed = set(undistributed or ())
        self._apply_filter_and_sort()
        self.endResetModel()

    def set_undistributed(self, task_ids: Set[str]) -> None:
        """Обновляет подсветку без перезагрузки списка."""
        self._undistributed = set(task_ids)
        if self._visible:
            top = self.index(0, 0)
            bottom = self.index(len(self._visible) - 1, len(TASK_COLUMNS) - 1)
            self.dataChanged.emit(top, bottom, [Qt.BackgroundRole])

    def refresh_theme(self) -> None:
        """Перерисовывает строки после смены темы."""
        if self._visible:
            top = self.index(0, 0)
            bottom = self.index(len(self._visible) - 1, len(TASK_COLUMNS) - 1)
            self.dataChanged.emit(top, bottom, [Qt.BackgroundRole])

    def set_search(self, text: str) -> None:
        """Фильтрует задачи по подстроке в коде/названии/типе/комментарии."""
        self.beginResetModel()
        self._search = (text or "").strip().lower()
        self._apply_filter_and_sort()
        self.endResetModel()

    def _apply_filter_and_sort(self) -> None:
        tasks = self._tasks
        if self._search:
            tasks = [
                task
                for task in tasks
                if self._search in (task.id or "").lower()
                or self._search in (task.name or "").lower()
                or self._search in (task.type or "").lower()
                or self._search in (task.comment or "").lower()
                or self._search
                in enum_label("scientific_task_type", task.type).lower()
            ]
        tasks = sorted(tasks, key=self._sort_key, reverse=self._sort_order == Qt.DescendingOrder)
        self._visible = tasks

    def _sort_key(self, task: ScientificTask):
        field = TASK_COLUMNS[self._sort_column][0]
        value = getattr(task, field, None)
        if field == "type":
            value = enum_label("scientific_task_type", task.type)
        if isinstance(value, date):
            return (value is None, value or date.min)
        if isinstance(value, (int, float)) or hasattr(value, "as_tuple"):
            return (value is None, float(value) if value is not None else 0.0)
        return (value is None, str(value or "").lower())

    # ------------------------------------------------------------------
    # Qt API
    # ------------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._visible)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(TASK_COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            return field_short_label(ScientificTask, TASK_COLUMNS[section][0])
        return None

    def flags(self, index: QModelIndex):  # noqa: N802
        if not index.isValid():
            return Qt.NoItemFlags
        return (
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsDragEnabled
        )

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._visible)):
            return None
        task = self._visible[index.row()]
        field = TASK_COLUMNS[index.column()][0]

        if role == Qt.DisplayRole:
            value = getattr(task, field, None)
            if field in ("start_date", "end_date"):
                return _format_date(value)
            if field in ("partial_threshold", "full_threshold"):
                return _format_number(value)
            if field == "type":
                return enum_label("scientific_task_type", task.type)
            return "" if value is None else str(value)

        if role == Qt.BackgroundRole and task.id in self._undistributed:
            return QBrush(current_theme().unassigned_row)
        if role == TASK_ID_ROLE:
            return task.id
        if role == Qt.ToolTipRole and task.comment:
            return task.comment
        return None

    def sort(self, column: int, order=Qt.AscendingOrder) -> None:
        if not 0 <= column < len(TASK_COLUMNS):
            return
        self.layoutAboutToBeChanged.emit()
        self._sort_column = column
        self._sort_order = order
        self._apply_filter_and_sort()
        self.layoutChanged.emit()

    def task_at(self, row: int) -> Optional[ScientificTask]:
        if 0 <= row < len(self._visible):
            return self._visible[row]
        return None

    def tasks_at(self, rows: Sequence[int]) -> List[ScientificTask]:
        return [
            self._visible[row]
            for row in rows
            if 0 <= row < len(self._visible)
        ]
