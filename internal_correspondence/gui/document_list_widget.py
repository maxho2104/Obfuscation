"""Виджет списка записей (материалы/телеграммы) с пагинацией и фильтрацией."""

from pathlib import Path
from typing import List, Optional, Type

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import DEFAULT_PAGE_SIZE
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.attached_files_widget import AttachedFilesWidget
from internal_correspondence.gui.document_dialogs import (
    MaterialEditDialog,
    TelegramEditDialog,
)
from internal_correspondence.gui.evaluation_delegate import EvaluationItemDelegate
from internal_correspondence.gui.filter_dialog import FilterDialog
from internal_correspondence.gui.table_model import ColumnDef, SqlAlchemyTableModel
from internal_correspondence.orm.base import Base
from internal_correspondence.utils.string_resources import STRINGS
from internal_correspondence.orm.labels import deletion_confirmation_text
from internal_correspondence.orm.models import ScientificMaterial, Telegram
from internal_correspondence.services.document_service import (
    ScientificMaterialService,
    TelegramService,
)

logger = get_logger("document_list_widget")


class DocumentListWidget(QWidget):
    """Универсальный виджет списка документов (материалов или телеграмм)."""

    def __init__(
        self,
        session,
        storage_root: Path,
        model_class: Type[Base],
        columns: List[ColumnDef],
        branch_id: Optional[str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.storage_root = storage_root
        self.model_class = model_class
        self.columns = columns
        self.branch_id = branch_id
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
        splitter = QSplitter(Qt.Vertical)

        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.doubleClicked.connect(self._edit)
        splitter.addWidget(self.table)

        self.files_widget = AttachedFilesWidget(self.storage_root)
        self.files_widget.setMaximumHeight(150)
        splitter.addWidget(self.files_widget)
        splitter.setSizes([400, 150])

        layout.addWidget(splitter)

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

        self.table_model = SqlAlchemyTableModel(
            self.session, self.model_class, self.columns
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
            self,
        )
        dialog.filtersChanged.connect(self._apply_filters)
        dialog.exec_()

    def _apply_filters(self, filters) -> None:
        """Применяет условия фильтрации к модели таблицы."""
        self.table_model.set_filters(filters)
        self._update_pagination()
        self._update_filter_button()

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
        items = self._selected_items()
        if len(items) == 1 and hasattr(items[0], "files"):
            self.files_widget.set_files(list(items[0].files))
        else:
            self.files_widget.set_files([])

    def _add(self) -> None:
        dialog = (
            MaterialEditDialog(
                self.session, self.storage_root, branch_id=self.branch_id, parent=self
            )
            if self.is_material
            else TelegramEditDialog(
                self.session, self.storage_root, branch_id=self.branch_id, parent=self
            )
        )
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            data = dialog.get_data()
            files = dialog.get_new_files()
            self.service.create_with_files(data, files)
            self.session.commit()
            self.refresh()
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
                self.storage_root,
                material=item,
                branch_id=item.branch_id,
                parent=self,
            )
            if self.is_material
            else TelegramEditDialog(
                self.session,
                self.storage_root,
                telegram=item,
                branch_id=item.branch_id,
                parent=self,
            )
        )
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            data = dialog.get_data()
            files = dialog.get_new_files()
            self.service.update_with_files(item, data, files)
            self.session.commit()
            self.refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка обновления документа")
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_update_error.format(error=exc)
            )
            self.session.rollback()

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
