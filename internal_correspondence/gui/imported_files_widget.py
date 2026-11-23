"""Док-виджет файлов, восстановленных последней операцией импорта.

Таблица строится по манифесту последнего импорта (см.
``importexport/import_service``): манифест хранит первичные ключи записей
``FileRecord``, остальные данные строк (филиал, тип и реквизиты документа)
берутся из базы. Поддержаны: поиск подстрокой по всем колонкам (regex не
нужен), открытие файла по двойному щелчку средствами ОС, перетаскивание во
внешние приложения (проводник копирует файл; перемещение из текущих папок
размещения недопустимо и не предлагается), контекстное меню «Расположение
файла» / «Переименовать» / «Удалить файл». Строки упорядочены по алфавиту
имени файла.

Панель оформлена по образцу дока прикреплённых файлов
(``gui/attached_files_widget``): свободно перетаскивается за заголовок во все
области главного окна и в отдельное плавающее окно. Показ панели ограничен
вкладкой «Дашборд» и ролью головного офиса — правило реализовано в
``gui/application`` при переключении вкладок.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import (
    QAbstractTableModel,
    QFileInfo,
    QMimeData,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QUrl,
)
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFileIconProvider,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import Session

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.attached_files_widget import (
    BROKEN_FILE_COLOR,
    _explorer_select_command,
)
from internal_correspondence.importexport.import_service import (
    read_import_manifest,
    write_import_manifest,
)
from internal_correspondence.orm.labels import entity_label
from internal_correspondence.orm.models import FileRecord
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("imported_files_widget")

# Колонки таблицы
COL_FILE = 0
COL_BRANCH = 1
COL_TYPE = 2
COL_OUTGOING = 3

# Начальные ширины колонок реквизитов: имя файла занимает остаток ширины
# панели, длинный текст сокращается многоточием и раскрывается подсказкой
_COLUMN_WIDTHS = {COL_BRANCH: 90, COL_TYPE: 85, COL_OUTGOING: 120}

# Ширина панели, при которой таблица помещается без горизонтальной прокрутки
_DOCK_MIN_WIDTH = 420


@dataclass
class ImportedFileRow:
    """Строка таблицы: ключ записи файла и вычисленные отображаемые поля."""

    record_id: str  # строковый UUID записи FileRecord
    filename: str  # имя файла с расширением
    path: Path  # абсолютный путь в файловом хранилище
    branch: str  # наименование филиала документа
    doc_type: str  # метка типа документа (научный материал / телеграмма)
    outgoing: str  # «Исходящий номер от ДД.ММ.ГГГГ»
    missing: bool  # файл отсутствует на диске


class ImportedFilesTableModel(QAbstractTableModel):
    """Модель таблицы файлов последнего импорта (4 колонки)."""

    def __init__(
        self, storage_root: Path, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._storage_root = Path(storage_root)
        self._rows: List[ImportedFileRow] = []
        self._icon_provider = QFileIconProvider()

    # --- интерфейс модели ---

    def set_rows(self, rows: List[ImportedFileRow]) -> None:
        """Полностью заменяет состав строк таблицы."""
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, index: QModelIndex) -> ImportedFileRow:
        """Возвращает строку данных по индексу модели."""
        return self._rows[index.row()]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else 4

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return (
                STRINGS.dashboard_imported_col_file,
                STRINGS.dashboard_imported_col_branch,
                STRINGS.dashboard_imported_col_type,
                STRINGS.dashboard_imported_col_outgoing,
            )[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == Qt.DisplayRole:
            return (
                row.filename,
                row.branch,
                row.doc_type,
                row.outgoing,
            )[index.column()]
        if role == Qt.DecorationRole and index.column() == COL_FILE:
            return self._icon(row.path)
        if role == Qt.ToolTipRole:
            # Колонки уже́ панели: сокращённый текст раскрывается подсказкой
            if row.missing:
                return STRINGS.tooltip_file_missing.format(path=row.path)
            return (
                row.filename,
                row.branch,
                row.doc_type,
                row.outgoing,
            )[index.column()]
        if row.missing:
            if role == Qt.FontRole:
                font = QFont()
                font.setStrikeOut(True)
                return font
            if role == Qt.ForegroundRole:
                return QColor(BROKEN_FILE_COLOR)
        return None

    # --- перетаскивание наружу ---

    def mimeTypes(self) -> List[str]:  # noqa: N802
        return ["text/uri-list"]

    def mimeData(self, indexes) -> QMimeData:  # noqa: N802
        """Возвращает URL выбранных файлов для перетаскивания наружу."""
        mime = QMimeData()
        urls = []
        seen = set()
        for index in indexes:
            if not index.isValid() or index.column() != COL_FILE:
                continue
            row = self._rows[index.row()]
            if row.record_id in seen:
                continue
            seen.add(row.record_id)
            urls.append(QUrl.fromLocalFile(str(row.path)))
        mime.setUrls(urls)
        return mime

    # --- служебное ---

    def _icon(self, path: Path) -> QIcon:
        """Возвращает стандартный значок для файла."""
        if path.exists():
            return self._icon_provider.icon(QFileInfo(str(path)))
        return self._icon_provider.icon(QFileIconProvider.File)


class ImportedFilesWidget(QDockWidget):
    """Док-виджет таблицы файлов последнего импорта с поиском и меню."""

    def __init__(
        self,
        session: Session,
        storage_root: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(STRINGS.dashboard_imported_files, parent)
        self.session = session
        self.storage_root = Path(storage_root)
        self._record_ids: List[str] = []
        self.setObjectName("imported_files_dock")
        # Панель свободно перетаскивается за заголовок: во все области
        # главного окна и в отдельное плавающее окно.
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        self._setup_ui()
        self.refresh()

    # --- интерфейс ---

    def _setup_ui(self) -> None:
        content = QWidget()
        # Ширина, при которой таблица помещается без горизонтальной прокрутки
        content.setMinimumWidth(_DOCK_MIN_WIDTH)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            STRINGS.dashboard_imported_filter_placeholder
        )
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.filter_edit)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.empty_label = QLabel(STRINGS.dashboard_imported_empty)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.stack.addWidget(self.empty_label)

        self.table_model = ImportedFilesTableModel(self.storage_root)
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        # Поиск подстрокой (без regex) по всем колонкам
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Только отдача файлов наружу: приём файлов извне здесь не поддержан
        self.table.setAcceptDrops(False)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        self.table.setDefaultDropAction(Qt.CopyAction)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._open_index)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setMinimumHeight(120)
        self.table.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        header = self.table.horizontalHeader()
        # Имя файла занимает свободное место, реквизиты получают штатную
        # ширину. В узкой панели появляется горизонтальная прокрутка, полный
        # текст доступен во всплывающей подсказке; ширину панели оператор
        # меняет перетаскиванием границы дока
        header.setSectionResizeMode(COL_FILE, QHeaderView.Stretch)
        for column, width in _COLUMN_WIDTHS.items():
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            header.resizeSection(column, width)
        header.setStretchLastSection(False)
        self.stack.addWidget(self.table)

        self.setWidget(content)

    def refresh(self) -> None:
        """Перечитывает манифест последнего импорта и перестраивает таблицу."""
        self._record_ids = read_import_manifest(self.storage_root)
        rows: List[ImportedFileRow] = []
        for raw in self._record_ids:
            try:
                record_id = uuid.UUID(str(raw))
            except (ValueError, AttributeError, TypeError):
                # Записи манифеста старого формата (пути) не отображаются
                continue
            record = self.session.get(FileRecord, record_id)
            if record is None:
                continue
            rows.append(self._build_row(record))
        rows.sort(key=lambda row: row.filename.casefold())
        self.table_model.set_rows(rows)
        self.stack.setCurrentWidget(
            self.table if rows else self.empty_label
        )
        self._apply_filter(self.filter_edit.text())

    # --- построение строк ---

    def _build_row(self, record: FileRecord) -> ImportedFileRow:
        """Формирует строку таблицы из записи файла и её документа."""
        filename = f"{record.name}.{record.extension}" if record.extension else record.name
        path = self.storage_root / record.path / filename
        document = self._primary_document(record)
        branch = ""
        doc_type = ""
        outgoing = ""
        if document is not None:
            if document.branch is not None:
                branch = document.branch.name
            doc_type = entity_label(type(document))
            outgoing = self._format_outgoing(
                document.outgoing_number, document.outgoing_date
            )
        return ImportedFileRow(
            record_id=str(record.id),
            filename=filename,
            path=path,
            branch=branch,
            doc_type=doc_type,
            outgoing=outgoing,
            missing=not path.exists(),
        )

    @staticmethod
    def _primary_document(record: FileRecord):
        """Возвращает документ файла: последний по дате исходящего номера."""
        documents = list(record.materials) + list(record.telegrams)
        if not documents:
            return None
        return max(documents, key=lambda doc: doc.outgoing_date or date.min)

    @staticmethod
    def _format_outgoing(number: Optional[str], doc_date: Optional[date]) -> str:
        """Форматирует «Исходящий номер от ДД.ММ.ГГГГ» из реквизитов документа."""
        if number and doc_date:
            return STRINGS.dashboard_imported_outgoing_full.format(
                number=number, date=doc_date.strftime("%d.%m.%Y")
            )
        if number:
            return number
        if doc_date:
            return doc_date.strftime("%d.%m.%Y")
        return ""

    # --- фильтр ---

    def _apply_filter(self, text: str) -> None:
        """Показывает только строки, содержащие подстроку в любой колонке."""
        self.proxy_model.setFilterFixedString(text.strip())

    # --- служебное ---

    def _selected_rows(self) -> List[ImportedFileRow]:
        """Возвращает данные выбранных строк без повторов."""
        rows: List[ImportedFileRow] = []
        for index in self.table.selectionModel().selectedRows():
            source = self.proxy_model.mapToSource(index)
            if source.isValid():
                row = self.table_model.row_at(source)
                if row not in rows:
                    rows.append(row)
        return rows

    def _rewrite_manifest(self, record_ids: List[str]) -> None:
        """Сохраняет новый состав манифеста и обновляет таблицу."""
        self._record_ids = list(record_ids)
        write_import_manifest(self.storage_root, self._record_ids)
        self.refresh()

    # --- действия ---

    def _open_index(self, index: QModelIndex) -> None:
        """Открывает файл стандартным обработчиком операционной системы."""
        source = self.proxy_model.mapToSource(index)
        if not source.isValid():
            return
        self._open_row(self.table_model.row_at(source))

    def _open_row(self, row: ImportedFileRow) -> None:
        """Открывает файл строки средствами ОС."""
        if not row.path.exists():
            QMessageBox.warning(
                self,
                STRINGS.title_attention,
                STRINGS.tooltip_file_missing.format(path=row.path),
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(row.path)))

    def _context_menu(self, position) -> None:
        """Показывает контекстное меню файла."""
        rows = self._selected_rows()
        if not rows:
            return
        menu = QMenu(self)
        reveal_action = menu.addAction(STRINGS.action_reveal)
        rename_action = menu.addAction(STRINGS.action_rename)
        rename_action.setEnabled(len(rows) == 1)
        delete_action = menu.addAction(STRINGS.action_delete_file)
        chosen = menu.exec_(self.table.viewport().mapToGlobal(position))
        if chosen is reveal_action:
            self._reveal_row(rows[0])
        elif chosen is rename_action:
            self._rename_row(rows[0])
        elif chosen is delete_action:
            self._delete_rows(rows)

    def _reveal_row(self, row: ImportedFileRow) -> None:
        """Открывает папку файла в проводнике ОС (файл выделен)."""
        folder = row.path.parent
        if not folder.exists():
            QMessageBox.warning(
                self,
                STRINGS.title_attention,
                STRINGS.tooltip_file_missing.format(path=row.path),
            )
            return
        if os.name == "nt":
            try:
                subprocess.Popen(_explorer_select_command(row.path))
            except OSError:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _rename_row(self, row: ImportedFileRow) -> None:
        """Переименовывает файл на диске и обновляет запись БД."""
        old_name = row.filename
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
        target = row.path.with_name(new_name)
        if target.exists():
            QMessageBox.warning(
                self,
                STRINGS.title_attention,
                STRINGS.files_rename_exists.format(name=new_name),
            )
            return
        try:
            record = self.session.get(FileRecord, uuid.UUID(row.record_id))
            if row.path.exists():
                row.path.rename(target)
            if record is not None:
                record.name = target.stem
                record.extension = target.suffix.lstrip(".")
                self.session.flush()
            self.session.commit()
            self.refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка переименования импортированного файла")
            self.session.rollback()
            QMessageBox.critical(
                self,
                STRINGS.title_error,
                STRINGS.imported_files_error.format(error=exc),
            )
            self.refresh()

    def _delete_rows(self, rows: List[ImportedFileRow]) -> None:
        """Удаляет выбранные файлы с диска и из манифеста."""
        removed_ids = {row.record_id for row in rows}
        reply = QMessageBox.question(
            self,
            STRINGS.title_confirm,
            STRINGS.imported_files_delete_confirm.format(count=len(rows)),
        )
        if reply != QMessageBox.Yes:
            return
        try:
            errors = []
            for row in rows:
                try:
                    if row.path.exists():
                        row.path.unlink()
                except OSError as exc:
                    errors.append(f"{row.filename}: {exc}")
            remaining = [
                item for item in self._record_ids if item not in removed_ids
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
