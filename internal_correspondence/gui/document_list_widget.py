"""Виджет списка записей (материалы/телеграммы) с пагинацией и фильтрацией."""

from pathlib import Path
from typing import Callable, List, Optional, Type

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
from internal_correspondence.gui.document_dialogs import MaterialEditDialog, TelegramEditDialog
from internal_correspondence.gui.evaluation_delegate import EvaluationItemDelegate
from internal_correspondence.gui.filter_dialog import FilterDialog
from internal_correspondence.gui.table_model import ColumnDef, SqlAlchemyTableModel
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import ScientificMaterial, Telegram
from internal_correspondence.services.document_service import ScientificMaterialService, TelegramService

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
        self.add_btn = QPushButton("Добавить")
        self.edit_btn = QPushButton("Изменить")
        self.delete_btn = QPushButton("Удалить")
        self.refresh_btn = QPushButton("Обновить")

        self.add_btn.clicked.connect(self._add)
        self.edit_btn.clicked.connect(self._edit)
        self.delete_btn.clicked.connect(self._delete)
        self.refresh_btn.clicked.connect(self._refresh)

        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addStretch()
        self.filter_btn = QPushButton("Фильтр")
        self.filter_btn.clicked.connect(self._open_filter_dialog)
        toolbar.addWidget(self.filter_btn)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        # Таблица
        splitter = QSplitter(Qt.Vertical)

        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
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
        self.prev_btn = QPushButton("< Назад")
        self.next_btn = QPushButton("Вперёд >")
        self.page_label = QLabel("Страница 1 / 1")
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)
        pagination.addWidget(self.prev_btn)
        pagination.addWidget(self.page_label)
        pagination.addWidget(self.next_btn)
        pagination.addStretch()
        layout.addLayout(pagination)

        self.table_model = SqlAlchemyTableModel(self.session, self.model_class, self.columns)
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
        self.filter_btn.setText(f"Фильтр ({count})" if count else "Фильтр")
        self.filter_btn.setToolTip(
            "Настроить фильтрацию записей" if not count else f"Применено фильтров: {count}"
        )

    def _refresh(self) -> None:
        self.table_model.refresh()
        self._update_pagination()
        self._update_filter_button()

    def _update_pagination(self) -> None:
        total_pages = self.table_model.total_pages()
        current_page = self.table_model.page()
        self.page_label.setText(f"Страница {current_page} / {total_pages}")
        self.prev_btn.setEnabled(current_page > 1)
        self.next_btn.setEnabled(current_page < total_pages)

    def _prev_page(self) -> None:
        self.table_model.set_page(self.table_model.page() - 1)
        self._update_pagination()

    def _next_page(self) -> None:
        self.table_model.set_page(self.table_model.page() + 1)
        self._update_pagination()

    def _selected_item(self) -> Optional[Base]:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.table_model.item_at(indexes[0].row())

    def _on_selection_changed(self) -> None:
        item = self._selected_item()
        if item and hasattr(item, "files"):
            self.files_widget.set_files(list(item.files))
        else:
            self.files_widget.set_files([])

    def _add(self) -> None:
        dialog = (
            MaterialEditDialog(self.session, self.storage_root, branch_id=self.branch_id, parent=self)
            if self.is_material
            else TelegramEditDialog(self.session, self.storage_root, branch_id=self.branch_id, parent=self)
        )
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            data = dialog.get_data()
            files = dialog.get_new_files()
            self.service.create_with_files(data, files)
            self.session.commit()
            self._refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка создания документа")
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать запись:\n{exc}")
            self.session.rollback()

    def _edit(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        dialog = (
            MaterialEditDialog(self.session, self.storage_root, material=item, branch_id=item.branch_id, parent=self)
            if self.is_material
            else TelegramEditDialog(self.session, self.storage_root, telegram=item, branch_id=item.branch_id, parent=self)
        )
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            data = dialog.get_data()
            files = dialog.get_new_files()
            if self.is_material:
                self.service.update_with_files(item, data, files)
            else:
                self.service.update_with_files(item, data, files)
            self.session.commit()
            self._refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка обновления документа")
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить запись:\n{exc}")
            self.session.rollback()

    def _delete(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            "Вы действительно хотите удалить выбранную запись?",
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self.service.delete(item)
            self.session.commit()
            self._refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка удаления документа")
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить запись:\n{exc}")
            self.session.rollback()
