"""Виджет списка записей (материалы/телеграммы) с пагинацией и фильтрацией."""

from pathlib import Path
from typing import List, Optional, Type

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import Role
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.document_dialogs import (
    MaterialEditDialog,
    TelegramEditDialog,
)
from internal_correspondence.gui.evaluation_delegate import EvaluationItemDelegate
from internal_correspondence.gui.evaluation_dialog import EvaluationAssignDialog
from internal_correspondence.gui.filter_dialog import FilterDialog
from internal_correspondence.gui.table_model import (
    ColumnDef,
    DocumentsTableModel,
)
from internal_correspondence.orm.base import Base
from internal_correspondence.utils.string_resources import STRINGS
from internal_correspondence.orm.labels import deletion_confirmation_text
from internal_correspondence.orm.models import (
    ScientificMaterial,
)
from internal_correspondence.services.document_service import (
    ScientificMaterialService,
    TelegramService,
)
from internal_correspondence.services.evaluation_service import (
    EvaluationError,
    EvaluationService,
)

logger = get_logger("document_list_widget")


class DocumentListWidget(QWidget):
    """Универсальный виджет списка документов (материалов или телеграмм)."""

    filtersChanged = pyqtSignal(list)
    currentDocumentChanged = pyqtSignal(object)

    def __init__(
        self,
        session,
        storage_root: Path,
        model_class: Type[Base],
        columns: List[ColumnDef],
        branch_id: Optional[str],
        role: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.storage_root = storage_root
        self.model_class = model_class
        self.columns = columns
        self.branch_id = branch_id
        self.role = role
        self.is_material = model_class == ScientificMaterial
        self.service = (
            ScientificMaterialService(session, storage_root)
            if self.is_material
            else TelegramService(session, storage_root)
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Панель инструментов
        toolbar = QHBoxLayout()
        self.add_btn = QPushButton(STRINGS.button_add)
        self.edit_btn = QPushButton(STRINGS.button_edit)
        self.delete_btn = QPushButton(STRINGS.button_delete)
        self.refresh_btn = QPushButton(STRINGS.button_refresh)

        # Те же роли, что в редакторе «Данные → Страны»:
        # добавление — акцентное, изменение — нейтральное, удаление — опасное.
        self.add_btn.setProperty("role", "primary")
        self.delete_btn.setProperty("role", "danger")

        self.add_btn.clicked.connect(self._add)
        self.edit_btn.clicked.connect(self._edit)
        self.delete_btn.clicked.connect(self._delete)
        self.refresh_btn.clicked.connect(self.refresh)

        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addStretch()
        self.filter_btn = QPushButton(STRINGS.button_filter)
        self.filter_btn.clicked.connect(self._open_filter_dialog)
        toolbar.addWidget(self.filter_btn)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        # Таблица
        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # Перетаскивание заголовков мышью (порядок столбцов) — как в
        # проводнике Windows; сортировка по щелчку сохраняется.
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_context_menu)
        self.table.doubleClicked.connect(self._edit)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        layout.addWidget(self.table)

        # Пагинация
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

        # Для роли «филиал» выборка ограничена его строками
        model_branch = self.branch_id if self.role == Role.BRANCH.value else None
        self.table_model = DocumentsTableModel(
            self.session, self.model_class, self.columns, branch_id=model_branch
        )
        self.table.setModel(self.table_model)
        for idx, col in enumerate(self.columns):
            self.table.setColumnWidth(idx, col.width)
        self._setup_evaluation_delegate()
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._update_pagination()
        self._update_filter_button()

    def _setup_evaluation_delegate(self) -> None:
        """Назначает делегат цветового отображения для столбца оценки."""
        for idx, column in enumerate(self.columns):
            if column.name == "evaluation_display":
                self.table.setItemDelegateForColumn(
                    idx,
                    EvaluationItemDelegate(idx, self.table),
                )
                return

    def _open_filter_dialog(self) -> None:
        """Открывает диалог настройки фильтров текущей вкладки."""
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
        """Применяет условия фильтрации к модели таблицы."""
        self.table_model.set_filters(filters)
        self._update_pagination()
        self._update_filter_button()
        self.filtersChanged.emit(self.table_model.filters())

    def current_filters(self) -> list:
        """Возвращает применённые условия фильтрации."""
        return self.table_model.filters()

    def set_filters(self, filters) -> None:
        """Применяет восстановленные из настроек условия фильтрации."""
        self.table_model.set_filters(list(filters))
        self._update_pagination()
        self._update_filter_button()

    def reveal_record(self, entity_pk) -> bool:
        """Выделяет запись и показывает её страницу пагинации.

        Возвращает False, если запись не попадает в текущую выборку
        (действуют фильтры, исключающие её).
        """
        page = self.table_model.page_of(entity_pk)
        if page is None:
            return False
        if page != self.table_model.page():
            self.table_model.set_page(page)
            self._update_pagination()
        row = self.table_model.row_of(entity_pk)
        if row is None:
            return False
        index = self.table_model.index(row, 0)
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index, QAbstractItemView.PositionAtCenter)
        self.table.selectRow(row)
        return True

    def _update_filter_button(self) -> None:
        """Показывает количество применённых фильтров на кнопке."""
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

    def refresh(self) -> None:
        self.session.expire_all()
        self.table_model.refresh()
        self._update_pagination()
        self._update_filter_button()

    def reload_document_state(self, document_id) -> None:
        """Перечитывает служебное состояние записи (подсветка неэкспортированных изменений).

        Операции с файлами выполняются док-виджетом в другой сессии, поэтому
        кэш модели хранит устаревшее change_id до явного перечитывания.
        Полный refresh не нужен: меняется только фон строки.
        """
        instance = self.session.get(self.model_class, document_id)
        if instance is None:
            return
        self.session.expire(instance)
        row = self.table_model.row_of(document_id)
        if row is not None:
            self.table_model.dataChanged.emit(
                self.table_model.index(row, 0),
                self.table_model.index(row, len(self.columns) - 1),
                [Qt.BackgroundRole],
            )

    def column_widths(self) -> List[int]:
        """Возвращает текущие ширины колонок таблицы."""
        return [self.table.columnWidth(i) for i in range(len(self.columns))]

    # ------------------------------------------------------------------
    # Порядок, видимость и ширина колонок
    # ------------------------------------------------------------------

    def columns_layout(self) -> str:
        """Сериализует раскладку колонок: «имя:ширина:видимость» по порядку.

        Записи идут в визуальном порядке заголовка, поэтому строка
        описывает и порядок, и ширину, и видимость каждой колонки.
        """
        header = self.table.horizontalHeader()
        parts = []
        for visual in range(len(self.columns)):
            logical = header.logicalIndex(visual)
            name = self.columns[logical].name
            width = self.table.columnWidth(logical)
            visible = 0 if header.isSectionHidden(logical) else 1
            parts.append(f"{name}:{width}:{visible}")
        return ",".join(parts)

    def set_columns_layout(self, layout: str) -> None:
        """Применяет раскладку колонок, сохранённую ``columns_layout``.

        Неизвестные колонки пропускаются; нехватку записей виджет
        переживает — остальные колонки остаются на местах.
        """
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
        # Сначала ширины и видимость по логическим колонкам
        for name, width, visible in entries:
            for logical, column in enumerate(self.columns):
                if column.name != name:
                    continue
                if width > 0:
                    self.table.setColumnWidth(logical, width)
                if visible:
                    header.showSection(logical)
                else:
                    header.hideSection(logical)
                break
        # Затем порядок: расставляем визуальные позиции по сохранённой строке
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
        """Собирает контекстное меню заголовка: наименования колонок с галочками."""
        header = self.table.horizontalHeader()
        menu = QMenu(self)
        for logical in range(len(self.columns)):
            title = self.table_model.headerData(logical, Qt.Horizontal, Qt.DisplayRole)
            action = menu.addAction(str(title))
            action.setCheckable(True)
            action.setChecked(not header.isSectionHidden(logical))
            action.setData(logical)
        return menu

    def _header_context_menu(self, position) -> None:
        """Показывает меню видимости колонок по правому щелчку на заголовке."""
        header = self.table.horizontalHeader()
        chosen = self._build_header_menu().exec_(
            header.viewport().mapToGlobal(position)
        )
        if chosen is not None:
            self._set_column_visible(chosen.data(), chosen.isChecked())

    def _set_column_visible(self, logical: int, visible: bool) -> None:
        """Скрывает или показывает колонку; последнюю видимую не скрывает."""
        header = self.table.horizontalHeader()
        if visible:
            header.showSection(logical)
            return
        visible_count = sum(
            1
            for index in range(len(self.columns))
            if not header.isSectionHidden(index)
        )
        if visible_count <= 1:
            return
        header.hideSection(logical)

    def sort_state(self) -> Optional[tuple]:
        """Возвращает (колонка, по убыванию) текущей сортировки; None — не задана."""
        column = self.table_model.sort_column()
        if column is None:
            return None
        return (column, self.table_model.sort_descending())

    def set_sort_state(self, column_name: str, descending: bool) -> bool:
        """Применяет сортировку по имени колонки; False — колонки нет в таблице."""
        for index, column in enumerate(self.columns):
            if column.name == column_name:
                order = Qt.DescendingOrder if descending else Qt.AscendingOrder
                self.table.sortByColumn(index, order)
                return True
        return False

    def set_column_widths(self, widths: List[int]) -> None:
        """Применяет сохранённые ширины колонок таблицы."""
        for index, width in enumerate(widths):
            if 0 <= index < len(self.columns) and width > 0:
                self.table.setColumnWidth(index, width)

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
        """Переходит на страницу с ограничением допустимого диапазона."""
        total_pages = max(1, self.table_model.total_pages())
        target = max(1, min(page, total_pages))
        if target != self.table_model.page():
            self.table_model.set_page(target)
        self._update_pagination()

    def _on_page_edit_finished(self) -> None:
        """Обрабатывает ввод номера страницы в поле пагинации."""
        try:
            page = int(self.page_edit.text().strip())
        except ValueError:
            self._update_pagination()
            return
        self._go_to_page(page)

    def _selected_items(self) -> List[Base]:
        """Возвращает все выделенные строки таблицы."""
        items = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table_model.item_at(index.row())
            if item is not None:
                items.append(item)
        return items

    def _current_item(self) -> Optional[Base]:
        """Возвращает строку под фокусом (для редактирования)."""
        row = self.table.currentIndex().row()
        if row >= 0:
            item = self.table_model.item_at(row)
            if item is not None:
                return item
        items = self._selected_items()
        return items[-1] if items else None

    def _on_selection_changed(self) -> None:
        """Сообщает о смене текущей записи (для док-виджета файлов)."""
        items = self._selected_items()
        document = None
        if len(items) == 1 and hasattr(items[0], "files"):
            document = items[0]
        self.currentDocumentChanged.emit(document)

    def current_document(self) -> Optional[Base]:
        """Возвращает текущую запись документа (для док-виджета файлов)."""
        item = self._current_item()
        if item is not None and hasattr(item, "files"):
            return item
        return None

    def _add(self) -> None:
        dialog = (
            MaterialEditDialog(
                self.session,
                branch_id=self.branch_id,
                role=self.role,
                parent=self,
            )
            if self.is_material
            else TelegramEditDialog(
                self.session,
                branch_id=self.branch_id,
                role=self.role,
                parent=self,
            )
        )
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            data = dialog.get_data()
            entity = self.service.create(data)
            self.session.commit()
            self.refresh()
            self._reveal_after_save(entity)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка создания документа")
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_create_error.format(error=exc)
            )
            self.session.rollback()

    def _edit(self) -> None:
        item = self._current_item()
        if item is None:
            return
        dialog = (
            MaterialEditDialog(
                self.session,
                material=item,
                branch_id=item.branch_id,
                role=self.role,
                parent=self,
            )
            if self.is_material
            else TelegramEditDialog(
                self.session,
                telegram=item,
                branch_id=item.branch_id,
                role=self.role,
                parent=self,
            )
        )
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            data = dialog.get_data()
            self.service.update(item, data)
            self.session.commit()
            self.refresh()
            self._reveal_after_save(item)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка обновления документа")
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_update_error.format(error=exc)
            )
            self.session.rollback()

    def _reveal_after_save(self, entity) -> None:
        """Выделяет сохранённую запись; при скрытии фильтрами — сообщает."""
        pk = self.table_model.pk_of(entity)
        if not self.reveal_record(pk):
            QMessageBox.information(
                self, STRINGS.title_attention, STRINGS.msg_record_hidden_by_filters
            )

    def _table_context_menu(self, position) -> None:
        """Показывает контекстное меню таблицы документов."""
        if not self._selected_items():
            return
        menu = QMenu(self)
        assign_action = menu.addAction(STRINGS.action_assign_evaluation)
        chosen = menu.exec_(self.table.viewport().mapToGlobal(position))
        if chosen is assign_action:
            self._assign_evaluation()

    def _assign_evaluation(self) -> None:
        """Выставляет оценку выделенным записям по правилам смены оценки."""
        items = self._selected_items()
        if not items:
            return
        dialog = EvaluationAssignDialog(self.session, self)
        if dialog.exec_() != dialog.Accepted:
            return
        value, assigned_date, mode, number, list_date, existing_list = (
            dialog.get_data()
        )
        try:
            service = EvaluationService(self.session)
            if mode == "new":
                if not number:
                    raise EvaluationError(STRINGS.msg_evaluation_list_required)
                evaluation_list = service.create_list(number, list_date)
            else:
                evaluation_list = existing_list
                if evaluation_list is None:
                    raise EvaluationError(STRINGS.msg_evaluation_list_required)
            service.assign_evaluation(items, value, assigned_date, evaluation_list)
            self.session.commit()
            self.refresh()
            QMessageBox.information(
                self,
                STRINGS.dialog_assign_evaluation_title,
                STRINGS.msg_evaluation_assigned.format(count=len(items)),
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка выставления оценки")
            self.session.rollback()
            QMessageBox.critical(
                self, STRINGS.title_error, str(exc)
            )

    def _delete(self) -> None:
        """Удаляет все выделенные записи после подтверждения."""
        items = self._selected_items()
        if not items:
            return
        reply = QMessageBox.warning(
            self,
            STRINGS.title_attention,
            deletion_confirmation_text(self.model_class, len(items)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            for item in items:
                self.service.delete(item)
            self.session.commit()
            self.refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка удаления документов")
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_delete_error.format(error=exc)
            )
            self.session.rollback()
