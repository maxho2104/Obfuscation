"""Универсальный редактор справочников."""

from typing import Callable, List, Optional, Type

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.table_model import ColumnDef, SqlAlchemyTableModel
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.labels import entity_label
from internal_correspondence.services.base_service import BaseService
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("reference_editor")


class ReferenceEditorWidget(QWidget):
    """Универсальный виджет редактирования справочника."""

    def __init__(
        self,
        session,
        model_class: Type[Base],
        service_class: Type[BaseService],
        columns: List[ColumnDef],
        edit_dialog_factory: Callable,
        read_only: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.model_class = model_class
        self.service = service_class(session)
        self.columns = columns
        self.edit_dialog_factory = edit_dialog_factory
        self.read_only = read_only
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        self.add_btn = QPushButton(STRINGS.button_add)
        self.edit_btn = QPushButton(STRINGS.button_edit)
        self.delete_btn = QPushButton(STRINGS.button_delete)
        self.refresh_btn = QPushButton(STRINGS.button_refresh)
        self.add_btn.setProperty("role", "primary")
        self.delete_btn.setProperty("role", "danger")

        self.add_btn.clicked.connect(self._add)
        self.edit_btn.clicked.connect(self._edit)
        self.delete_btn.clicked.connect(self._delete)
        self.refresh_btn.clicked.connect(self._refresh)

        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.edit_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addStretch()
        toolbar.addWidget(QLabel(STRINGS.filter_label))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(STRINGS.filter_placeholder)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.filter_edit)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.doubleClicked.connect(self._edit)
        layout.addWidget(self.table)

        pagination = QHBoxLayout()
        self.prev_btn = QPushButton(STRINGS.button_prev)
        self.next_btn = QPushButton(STRINGS.button_next)
        self.page_label = QLabel(STRINGS.page_label.format(current=1, total=1))
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
        self._update_pagination()

        if self.read_only:
            self.add_btn.setEnabled(False)
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)

    def _on_filter_changed(self, text: str) -> None:
        self.table_model.set_filter(text)
        self._update_pagination()

    def _refresh(self) -> None:
        self.table_model.refresh()
        self._update_pagination()

    def _update_pagination(self) -> None:
        total_pages = self.table_model.total_pages()
        current_page = self.table_model.page()
        self.page_label.setText(
            STRINGS.page_label.format(current=current_page, total=total_pages)
        )
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

    def _add(self) -> None:
        dialog = self.edit_dialog_factory(session=self.session, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            data = dialog.get_data()
            self.service.create(data)
            self.session.commit()
            self._refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка создания записи справочника")
            QMessageBox.critical(
                self, STRINGS.title_error,
                STRINGS.msg_ref_create_error.format(error=exc),
            )
            self.session.rollback()

    def _edit(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        dialog = self.edit_dialog_factory(session=self.session, item=item, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            data = dialog.get_data()
            self.service.update(item, data)
            self.session.commit()
            self._refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка обновления записи справочника")
            QMessageBox.critical(
                self, STRINGS.title_error,
                STRINGS.msg_ref_update_error.format(error=exc),
            )
            self.session.rollback()

    def _delete(self) -> None:
        item = self._selected_item()
        if item is None:
            return
        reply = QMessageBox.question(
            self,
            STRINGS.title_delete_confirm,
            STRINGS.msg_delete_record_confirm,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self.service.delete(item)
            self.session.commit()
            self._refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка удаления записи справочника")
            QMessageBox.critical(
                self, STRINGS.title_error,
                STRINGS.msg_ref_delete_error.format(error=exc),
            )
            self.session.rollback()


class ReferenceEditorDialog(QDialog):
    """Диалог-обёртка для универсального редактора справочников."""

    def __init__(
        self,
        session,
        model_class: Type[Base],
        service_class: Type[BaseService],
        columns: List[ColumnDef],
        edit_dialog_factory: Callable,
        read_only: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(entity_label(model_class, plural=True))
        self.setMinimumSize(800, 500)
        layout = QVBoxLayout(self)
        self.editor = ReferenceEditorWidget(
            session,
            model_class,
            service_class,
            columns,
            edit_dialog_factory,
            read_only=read_only,
            parent=self,
        )
        layout.addWidget(self.editor)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
