"""Виджет файлов, восстановленных последней операцией импорта.

Список строится по манифесту последнего импорта (см.
``importexport/import_service``). Поддержаны: фильтр по имени файла с
регулярными выражениями, открытие файла по двойному щелчку средствами ОС,
перетаскивание во внешние приложения (проводник копирует файл; перемещение
из текущих папок размещения недопустимо и не предлагается), контекстное
меню «Расположение файла» / «Переименовать» / «Удалить файл». Элементы
упорядочены по алфавиту имени файла.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QFileInfo, QRegularExpression, Qt, QUrl
from PyQt5.QtGui import QColor, QDesktopServices, QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileIconProvider,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import Session

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.attached_files_widget import (
    BROKEN_FILE_COLOR,
    FileListWidget,
    _explorer_select_command,
)
from internal_correspondence.importexport.import_service import (
    read_import_manifest,
    write_import_manifest,
)
from internal_correspondence.orm.models import FileRecord
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("imported_files_widget")

# Роли элементов списка: абсолютный путь (для открытия/перетаскивания)
# и относительный путь манифеста (для переименования/удаления)
ROLE_PATH = Qt.UserRole + 1
ROLE_RELATIVE = Qt.UserRole + 2


class ImportedFilesWidget(QWidget):
    """Список файлов последнего импорта с фильтром и контекстным меню."""

    def __init__(
        self,
        session: Session,
        storage_root: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.storage_root = Path(storage_root)
        self._paths: List[str] = []
        self._icon_provider = QFileIconProvider()
        self._setup_ui()
        self.refresh()

    # --- интерфейс ---

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title = QLabel(STRINGS.dashboard_imported_files)
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            STRINGS.dashboard_imported_filter_placeholder
        )
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.list_widget = FileListWidget()
        # Только отдача файлов наружу: приём файлов извне здесь не поддержан
        self.list_widget.setAcceptDrops(False)
        self.list_widget.setDragDropMode(QAbstractItemView.DragOnly)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_item)
        self.list_widget.setMinimumHeight(170)
        layout.addWidget(self.list_widget, 1)

    def refresh(self) -> None:
        """Перечитывает манифест последнего импорта и перестраивает список."""
        self._paths = read_import_manifest(self.storage_root)
        ordered = sorted(self._paths, key=lambda item: Path(item).name.casefold())
        self.list_widget.clear()
        if not ordered:
            placeholder = QListWidgetItem(STRINGS.dashboard_imported_empty)
            placeholder.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(placeholder)
            return
        for relative in ordered:
            path = self.storage_root / relative
            item = QListWidgetItem(self._icon(path), Path(relative).name)
            item.setData(ROLE_PATH, str(path))
            item.setData(ROLE_RELATIVE, relative)
            item.setToolTip(str(path))
            if not path.exists():
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(BROKEN_FILE_COLOR)
                item.setToolTip(
                    STRINGS.tooltip_file_missing.format(path=path)
                )
            self.list_widget.addItem(item)
        self._apply_filter(self.filter_edit.text())

    # --- фильтр ---

    def _apply_filter(self, pattern: str) -> None:
        """Показывает только файлы, имя которых подходит под regex-фильтр."""
        pattern = pattern.strip()
        if not pattern:
            self.filter_edit.setStyleSheet("")
            self.filter_edit.setToolTip("")
            for row in range(self.list_widget.count()):
                self.list_widget.item(row).setHidden(False)
            return
        regex = QRegularExpression(
            pattern, QRegularExpression.CaseInsensitiveOption
        )
        if not regex.isValid():
            # Некорректный шаблон: ничего не скрываем, подсвечиваем поле
            self.filter_edit.setStyleSheet("border: 1px solid #c0392b;")
            self.filter_edit.setToolTip(STRINGS.dashboard_imported_invalid_regex)
            for row in range(self.list_widget.count()):
                self.list_widget.item(row).setHidden(False)
            return
        self.filter_edit.setStyleSheet("")
        self.filter_edit.setToolTip("")
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(ROLE_RELATIVE) is None:
                continue
            item.setHidden(not regex.match(item.text()).hasMatch())

    # --- служебное ---

    def _icon(self, path: Path) -> QIcon:
        """Возвращает стандартный значок для файла."""
        if path.exists():
            return self._icon_provider.icon(QFileInfo(str(path)))
        return self._icon_provider.icon(QFileIconProvider.File)

    def _selected_items(self) -> List[QListWidgetItem]:
        """Возвращает выбранные элементы с привязанным файлом."""
        return [
            item
            for item in self.list_widget.selectedItems()
            if item.data(ROLE_RELATIVE) is not None
        ]

    def _rewrite_manifest(self, paths: List[str]) -> None:
        """Сохраняет новый состав манифеста и обновляет список."""
        self._paths = list(paths)
        write_import_manifest(self.storage_root, self._paths)
        self.refresh()

    def _find_record(self, relative: str) -> Optional[FileRecord]:
        """Возвращает запись FileRecord файла хранилища (если есть)."""
        path = Path(relative)
        return (
            self.session.query(FileRecord)
            .filter_by(
                path=str(path.parent).replace("\\", "/"),
                name=path.stem,
                extension=path.suffix.lstrip("."),
            )
            .first()
        )

    # --- действия ---

    def _open_item(self, item: QListWidgetItem) -> None:
        """Открывает файл стандартным обработчиком операционной системы."""
        raw = item.data(ROLE_PATH)
        if not raw:
            return
        path = Path(raw)
        if not path.exists():
            QMessageBox.warning(
                self,
                STRINGS.title_attention,
                STRINGS.tooltip_file_missing.format(path=path),
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _context_menu(self, position) -> None:
        """Показывает контекстное меню файла."""
        items = self._selected_items()
        if not items:
            return
        menu = QMenu(self)
        reveal_action = menu.addAction(STRINGS.action_reveal)
        rename_action = menu.addAction(STRINGS.action_rename)
        rename_action.setEnabled(len(items) == 1)
        delete_action = menu.addAction(STRINGS.action_delete_file)
        chosen = menu.exec_(self.list_widget.viewport().mapToGlobal(position))
        if chosen is reveal_action:
            self._reveal_item(items[0])
        elif chosen is rename_action:
            self._rename_item(items[0])
        elif chosen is delete_action:
            self._delete_items(items)

    def _reveal_item(self, item: QListWidgetItem) -> None:
        """Открывает папку файла в проводнике ОС (файл выделен)."""
        path = Path(item.data(ROLE_PATH) or "")
        folder = path.parent
        if not folder.exists():
            QMessageBox.warning(
                self,
                STRINGS.title_attention,
                STRINGS.tooltip_file_missing.format(path=path),
            )
            return
        if os.name == "nt":
            try:
                subprocess.Popen(_explorer_select_command(path))
            except OSError:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _rename_item(self, item: QListWidgetItem) -> None:
        """Переименовывает файл на диске, обновляя запись БД и манифест."""
        relative = str(item.data(ROLE_RELATIVE))
        path = Path(item.data(ROLE_PATH))
        old_name = Path(relative).name
        new_name, ok = QInputDialog.getText(
            self,
            STRINGS.files_rename_title,
            STRINGS.files_rename_prompt,
            text=old_name,
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == old_name:
            return
        if new_name in (".", "..") or "/" in new_name or "\\" in new_name:
            QMessageBox.warning(
                self, STRINGS.title_attention, STRINGS.files_rename_invalid
            )
            return
        target = path.with_name(new_name)
        if target.exists():
            QMessageBox.warning(
                self,
                STRINGS.title_attention,
                STRINGS.files_rename_exists.format(name=new_name),
            )
            return
        try:
            record = self._find_record(relative)
            if path.exists():
                path.rename(target)
            if record is not None:
                record.name = target.stem
                record.extension = target.suffix.lstrip(".")
                self.session.flush()
            new_relative = str(Path(relative).with_name(new_name)).replace(
                "\\", "/"
            )
            paths = [
                new_relative if entry == relative else entry
                for entry in self._paths
            ]
            self.session.commit()
            self._rewrite_manifest(paths)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка переименования импортированного файла")
            self.session.rollback()
            QMessageBox.critical(
                self,
                STRINGS.title_error,
                STRINGS.imported_files_error.format(error=exc),
            )
            self.refresh()

    def _delete_items(self, items: List[QListWidgetItem]) -> None:
        """Удаляет выбранные файлы с диска и из манифеста."""
        relatives = [str(item.data(ROLE_RELATIVE)) for item in items]
        reply = QMessageBox.question(
            self,
            STRINGS.title_confirm,
            STRINGS.imported_files_delete_confirm.format(count=len(relatives)),
        )
        if reply != QMessageBox.Yes:
            return
        try:
            errors = []
            for relative in relatives:
                path = self.storage_root / relative
                try:
                    if path.exists():
                        path.unlink()
                except OSError as exc:
                    errors.append(f"{relative}: {exc}")
            remaining = [
                entry for entry in self._paths if entry not in set(relatives)
            ]
            self._rewrite_manifest(remaining)
            if errors:
                QMessageBox.warning(
                    self,
                    STRINGS.title_attention,
                    "\n".join(errors),
                )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка удаления импортированных файлов")
            QMessageBox.critical(
                self,
                STRINGS.title_error,
                STRINGS.imported_files_error.format(error=exc),
            )
