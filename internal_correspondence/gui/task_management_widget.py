"""Виджет режима «Управление задачами».

Показывает задачи выбранного периода в таблице с назначениями по
уровням иерархии, процентом выполнения и функциями списка документов:
поиск, фильтр, сортировка, пагинация и настройка колонок.
"""

from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.gui.filter_dialog import FilterDialog
from internal_correspondence.gui.table_model import ColumnDef
from internal_correspondence.gui.task_management_model import TaskManagementModel
from internal_correspondence.orm.models import ScientificTask
from internal_correspondence.utils.string_resources import STRINGS


class TaskManagementWidget(QWidget):
    """Таблица задач периода с назначениями и процентом выполнения."""

    filtersChanged = pyqtSignal(list)
    refreshRequested = pyqtSignal()
    editRequested = pyqtSignal(object)
    deleteRequested = pyqtSignal(object)

    def __init__(
        self,
        session,
        columns: List[ColumnDef],
        is_head_office: bool = False,
        scope_branch_id: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.columns = columns
        self.is_head_office = is_head_office
        self._scope_branch_id = scope_branch_id
        # Ширина скрытых колонок: у невидимой секции QHeaderView возвращает 0,
        # поэтому последнюю известную ширину запоминаем отдельно.
        self._hidden_widths: dict = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(STRINGS.task_search)
        self.search_edit.setClearButtonEnabled(True)
        toolbar.addWidget(self.search_edit, 1)

        self.filter_btn = QPushButton(STRINGS.button_filter)
        self.filter_btn.clicked.connect(self._open_filter_dialog)
        self.refresh_btn = QPushButton(STRINGS.button_refresh)
        self.refresh_btn.clicked.connect(self.refreshRequested.emit)
        toolbar.addWidget(self.filter_btn)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_context_menu)
        self.table.doubleClicked.connect(lambda _index: self._request_edit())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        layout.addWidget(self.table, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        pagination = QHBoxLayout()
        self.first_btn = QPushButton("|<")
        self.prev_btn = QPushButton("<")
        self.page_edit = QLineEdit()
        self.page_edit.setAlignment(Qt.AlignCenter)
        self.page_edit.setMaximumWidth(60)
        self.page_edit.setValidator(QIntValidator(1, 999999, self))
        self.page_edit.setToolTip(STRINGS.tooltip_page_number)
        self.next_btn = QPushButton(">")
        self.last_btn = QPushButton(">|")
        self.page_total_label = QLabel(STRINGS.page_of.format(total=1))

        self.first_btn.clicked.connect(lambda: self._go_to_page(1))
        self.prev_btn.clicked.connect(
            lambda: self._go_to_page(self.table_model.page() - 1)
        )
        self.next_btn.clicked.connect(
            lambda: self._go_to_page(self.table_model.page() + 1)
        )
        self.last_btn.clicked.connect(
            lambda: self._go_to_page(self.table_model.total_pages())
        )
        self.page_edit.editingFinished.connect(self._on_page_edit_finished)

        pagination.addWidget(self.first_btn)
        pagination.addWidget(self.prev_btn)
        pagination.addWidget(QLabel(STRINGS.label_page))
        pagination.addWidget(self.page_edit)
        pagination.addWidget(self.page_total_label)
        pagination.addWidget(self.next_btn)
        pagination.addWidget(self.last_btn)
        pagination.addStretch()
        layout.addLayout(pagination)

        self.table_model = TaskManagementModel(
            self.session,
            self.columns,
            is_head_office=self.is_head_office,
            scope_branch_id=self._scope_branch_id,
        )
        self.table.setModel(self.table_model)
        for index, column in enumerate(self.columns):
            self.table.setColumnWidth(index, column.width)
        self.search_edit.textChanged.connect(self.table_model.set_filter)
        self.search_edit.textChanged.connect(self._on_search_changed)
        self._update_pagination()
        self._update_filter_button()

    # ------------------------------------------------------------------
    # Данные
    # ------------------------------------------------------------------

    def set_tasks(self, tasks: List[ScientificTask]) -> None:
        """Заменяет список задач периода и обновляет таблицу."""
        self.table_model.set_tasks(tasks)
        self._update_pagination()
        self._update_filter_button()
        self._update_status()

    def refresh(self) -> None:
        """Перечитывает служебные данные модели без запроса новых задач."""
        self.table_model.refresh()
        self._update_pagination()
        self._update_filter_button()
        self._update_status()

    def _update_status(self) -> None:
        """Показывает пояснение, если задач периода нет."""
        if self.table_model.total():
            self.status_label.setVisible(False)
            return
        self.status_label.setText(
            STRINGS.task_manage_empty
            if not self.table_model.filters() and not self.search_edit.text()
            else STRINGS.task_empty
        )
        self.status_label.setVisible(True)

    def _on_search_changed(self, _text: str) -> None:
        self._update_pagination()
        self._update_filter_button()
        self._update_status()

    # ------------------------------------------------------------------
    # Фильтр
    # ------------------------------------------------------------------

    def _open_filter_dialog(self) -> None:
        dialog = FilterDialog(
            self.table_model.model_class,
            self.table_model.columns,
            self.table_model.filters(),
            session=self.session,
            parent=self,
        )
        dialog.filtersChanged.connect(self._apply_filters)
        dialog.exec_()

    def _apply_filters(self, filters) -> None:
        self.table_model.set_filters(filters)
        self._update_pagination()
        self._update_filter_button()
        self._update_status()
        self.filtersChanged.emit(self.table_model.filters())

    def current_filters(self) -> list:
        """Возвращает применённые условия фильтрации."""
        return self.table_model.filters()

    def set_filters(self, filters) -> None:
        """Применяет восстановленные из настроек условия фильтрации."""
        self.table_model.set_filters(list(filters))
        self._update_pagination()
        self._update_filter_button()
        self._update_status()

    def _update_filter_button(self) -> None:
        count = len(self.table_model.filters())
        self.filter_btn.setText(
            STRINGS.button_filter_count.format(count=count)
            if count
            else STRINGS.button_filter
        )
        self.filter_btn.setToolTip(
            STRINGS.tooltip_filter_setup
            if not count
            else STRINGS.tooltip_filter_applied.format(count=count)
        )

    # ------------------------------------------------------------------
    # Пагинация
    # ------------------------------------------------------------------

    def _update_pagination(self) -> None:
        total_pages = max(1, self.table_model.total_pages())
        current_page = self.table_model.page()
        self.page_edit.setText(str(current_page))
        self.page_total_label.setText(STRINGS.page_of.format(total=total_pages))
        self.first_btn.setEnabled(current_page > 1)
        self.prev_btn.setEnabled(current_page > 1)
        self.next_btn.setEnabled(current_page < total_pages)
        self.last_btn.setEnabled(current_page < total_pages)

    def _go_to_page(self, page: int) -> None:
        total_pages = max(1, self.table_model.total_pages())
        target = max(1, min(page, total_pages))
        if target != self.table_model.page():
            self.table_model.set_page(target)
        self._update_pagination()

    def _on_page_edit_finished(self) -> None:
        try:
            page = int(self.page_edit.text().strip())
        except ValueError:
            self._update_pagination()
            return
        self._go_to_page(page)

    # ------------------------------------------------------------------
    # Колонки: порядок, видимость, ширина
    # ------------------------------------------------------------------

    def column_widths(self) -> List[int]:
        """Возвращает текущие ширины колонок таблицы."""
        return [self.table.columnWidth(i) for i in range(len(self.columns))]

    def set_column_widths(self, widths: List[int]) -> None:
        """Применяет сохранённые ширины колонок таблицы."""
        for index, width in enumerate(widths):
            if 0 <= index < len(self.columns) and width > 0:
                self.table.setColumnWidth(index, width)

    def columns_layout(self) -> str:
        """Сериализует раскладку колонок: «имя:ширина:видимость»."""
        header = self.table.horizontalHeader()
        parts = []
        for visual in range(len(self.columns)):
            logical = header.logicalIndex(visual)
            name = self.columns[logical].name
            hidden = header.isSectionHidden(logical)
            width = (
                self._hidden_widths.get(logical, 0)
                if hidden
                else self.table.columnWidth(logical)
            )
            parts.append(f"{name}:{width}:{0 if hidden else 1}")
        return ",".join(parts)

    def set_columns_layout(self, layout: str) -> None:
        """Применяет раскладку колонок, сохранённую ``columns_layout``."""
        entries = []
        for part in layout.split(","):
            name, _, rest = part.partition(":")
            width_text, _, visible_text = rest.partition(":")
            if not name:
                continue
            try:
                width = int(width_text)
            except ValueError:
                width = 0
            entries.append((name, width, visible_text != "0"))
        if not entries:
            return
        header = self.table.horizontalHeader()
        for name, width, visible in entries:
            for logical, column in enumerate(self.columns):
                if column.name != name:
                    continue
                if width > 0:
                    self.table.setColumnWidth(logical, width)
                    self._hidden_widths[logical] = width
                if visible:
                    header.showSection(logical)
                else:
                    header.hideSection(logical)
                break
        for visual, (name, _width, _visible) in enumerate(entries):
            logical = next(
                (index for index, col in enumerate(self.columns) if col.name == name),
                None,
            )
            if logical is None:
                continue
            current = header.visualIndex(logical)
            if current != visual:
                header.moveSection(current, visual)

    def _build_header_menu(self) -> QMenu:
        header = self.table.horizontalHeader()
        menu = QMenu(self)
        for logical in range(len(self.columns)):
            title = self.table_model.headerData(
                logical, Qt.Horizontal, Qt.DisplayRole
            )
            action = menu.addAction(str(title))
            action.setCheckable(True)
            action.setChecked(not header.isSectionHidden(logical))
            action.setData(logical)
        return menu

    def _header_context_menu(self, position) -> None:
        header = self.table.horizontalHeader()
        chosen = self._build_header_menu().exec_(
            header.viewport().mapToGlobal(position)
        )
        if chosen is not None:
            self._set_column_visible(chosen.data(), chosen.isChecked())

    def _set_column_visible(self, logical: int, visible: bool) -> None:
        header = self.table.horizontalHeader()
        if visible:
            header.showSection(logical)
            width = self._hidden_widths.pop(logical, 0)
            if width > 0:
                self.table.setColumnWidth(logical, width)
            return
        visible_count = sum(
            1
            for index in range(len(self.columns))
            if not header.isSectionHidden(index)
        )
        if visible_count <= 1:
            return
        self._hidden_widths[logical] = self.table.columnWidth(logical)
        header.hideSection(logical)

    # ------------------------------------------------------------------
    # Сортировка
    # ------------------------------------------------------------------

    def sort_state(self) -> Optional[tuple]:
        """Возвращает (колонка, по убыванию) текущей сортировки."""
        column = self.table_model.sort_column()
        if column is None:
            return None
        return (column, self.table_model.sort_descending())

    def set_sort_state(self, column_name: str, descending: bool) -> bool:
        """Применяет сортировку по имени колонки."""
        for index, column in enumerate(self.columns):
            if column.name == column_name:
                order = Qt.DescendingOrder if descending else Qt.AscendingOrder
                self.table.sortByColumn(index, order)
                return True
        return False

    def current_task(self) -> Optional[ScientificTask]:
        """Возвращает задачу под фокусом (для контекстных действий)."""
        row = self.table.currentIndex().row()
        if row < 0:
            return None
        return self.table_model.task_at(row)

    def _request_edit(self) -> None:
        """Сообщает о запросе изменения задачи (двойной щелчок по строке)."""
        task = self.current_task()
        if task is not None:
            self.editRequested.emit(task)

    def _table_context_menu(self, position) -> None:
        """Контекстное меню таблицы: изменение и удаление задачи."""
        task = self.current_task()
        if task is None:
            return
        menu = QMenu(self)
        edit_action = menu.addAction(STRINGS.task_edit)
        edit_action.triggered.connect(lambda: self.editRequested.emit(task))
        delete_action = menu.addAction(STRINGS.task_delete)
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(task))
        menu.exec_(self.table.viewport().mapToGlobal(position))
