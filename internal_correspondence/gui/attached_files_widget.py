"""Док-виджет прикреплённых файлов текущего документа.

Привязан к выбранной строке вкладки «научные материалы»/«телеграммы»:
показывает файлы записи и позволяет прикреплять новые (диалог выбора
или drag&drop из проводника ОС) и откреплять. Копирование в хранилище
выполняется в отдельном потоке с индикацией прогресса; привязка в БД —
после завершения копирования. Файлы, не разделённые с другими записями,
при откреплении удаляются с диска вместе с опустевшими папками.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QObject, Qt, QThread, QFileInfo, QMimeData, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QDesktopServices, QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFileIconProvider,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QDockWidget,
)
from sqlalchemy.orm import Session

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.labels import entity_label
from internal_correspondence.orm.models import (
    FileRecord,
    ScientificMaterial,
    Telegram,
)
from internal_correspondence.services.document_service import (
    DocumentServiceError,
    ScientificMaterialService,
    TelegramService,
)
from internal_correspondence.services.file_service import (
    FileCopyCancelled,
    copy_with_progress,
    is_inside_storage,
    unique_target_path,
)
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("attached_files_widget")

# Цвет отображения файла, ссылка на который в БД «битая»
BROKEN_FILE_COLOR = QColor(190, 40, 40)


def _explorer_select_command(path: Path) -> str:
    """Формирует командную строку проводника с выделенным файлом.

    Путь обязан оказаться внутри кавычек сразу после запятой: при
    передаче аргументом списком (``[explorer, f"/select,{path}"]``)
    subprocess заключает в кавычки весь элемент целиком, и проводник
    не распознаёт ключ ``/select,`` — вместо папки файла открывается
    папка по умолчанию (Документы).
    """
    return f'explorer /select,"{path}"'


class FileListWidget(QListWidget):
    """Список файлов с приёмом drag&drop извне и перетаскиванием наружу.

    Перетаскивание из проводника ОС (и других приложений) передаётся
    наружу через сигнал ``filesDropped``; перетаскивание из списка во
    внешние программы (проводник, архиваторы) отдаёт URL файлов.
    """

    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.CopyAction)

    def _urls_from_mime(self, mime: QMimeData) -> List[Path]:
        """Возвращает локальные файлы из MIME-данных (пусто — не файлы)."""
        if not mime.hasUrls():
            return []
        return [
            Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()
        ]

    def dragEnterEvent(self, event) -> None:
        if self._urls_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._urls_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        paths = self._urls_from_mime(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
            return
        super().dropEvent(event)

    def mimeData(self, items) -> QMimeData:  # noqa: N802 (API Qt)
        """Возвращает MIME-данные перетаскиваемых элементов — URL файлов."""
        mime = QMimeData()
        urls = []
        for item in items:
            path = item.data(Qt.UserRole + 1)
            if path:
                urls.append(QUrl.fromLocalFile(str(path)))
        mime.setUrls(urls)
        return mime


class CopyFilesWorker(QObject):
    """Потоковое поблочное копирование файлов в хранилище.

    Не обращается к БД: только файловая система. Отмена проверяется
    между блоками; недокопированный файл удаляется.
    """

    progressed = pyqtSignal(str)
    step = pyqtSignal(int)
    finished = pyqtSignal(list)      # пары (источник, назначение) завершённых
    failed = pyqtSignal(str)

    def __init__(self, pairs: List[tuple]) -> None:
        super().__init__()
        self._pairs = list(pairs)
        self._cancelled = False

    def cancel(self) -> None:
        """Запрашивает отмену копирования."""
        self._cancelled = True

    @pyqtSlot()
    def run(self) -> None:
        completed = []
        try:
            for source, target in self._pairs:
                if self._cancelled:
                    self.finished.emit(completed)
                    return
                self.progressed.emit(
                    STRINGS.files_copy_progress.format(
                        name=source.name,
                        source=source.parent,
                        target=target.parent,
                    )
                )
                copy_with_progress(
                    source, target, should_cancel=lambda: self._cancelled
                )
                completed.append((source, target))
                self.step.emit(len(completed))
            self.finished.emit(completed)
        except FileCopyCancelled:
            self.finished.emit(completed)
        except OSError as exc:
            logger.exception("Ошибка копирования файлов")
            self.failed.emit(str(exc))


class AttachedFilesWidget(QDockWidget):
    """Док-виджет прикреплённых файлов текущего документа."""

    def __init__(self, session: Session, storage_root: Path, parent=None) -> None:
        super().__init__(STRINGS.tooltip_add_files, parent)
        self.session = session
        self.storage_root = storage_root
        self._document: Optional[object] = None
        self._records: List[FileRecord] = []
        self._icon_provider = QFileIconProvider()
        self._thread: Optional[QThread] = None
        self.setObjectName("attached_files_dock")
        self._setup_ui()

    # --- интерфейс ---

    def _setup_ui(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)

        self.header_label = QLabel(STRINGS.files_no_selection)
        self.header_label.setWordWrap(True)
        layout.addWidget(self.header_label)

        row = QHBoxLayout()
        self.list_widget = FileListWidget()
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._context_menu)
        self.list_widget.itemDoubleClicked.connect(self._open_item)
        self.list_widget.filesDropped.connect(self._add_paths)
        row.addWidget(self.list_widget, 1)

        buttons = QVBoxLayout()
        buttons.setAlignment(Qt.AlignTop)
        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip(STRINGS.tooltip_add_files)
        self.add_btn.clicked.connect(self._add_files_dialog)
        self.remove_btn = QPushButton("−")
        self.remove_btn.setToolTip(STRINGS.tooltip_remove_files)
        self.remove_btn.clicked.connect(self._remove_selected)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.remove_btn)
        row.addLayout(buttons)
        layout.addLayout(row, 1)

        self.setWidget(content)
        self._update_state()

    def set_document(self, document: Optional[object]) -> None:
        """Привязывает виджет к записи документа (None — без привязки)."""
        self._document = document
        self.refresh()

    def refresh(self) -> None:
        """Обновляет список файлов от текущей записи."""
        if self._document is None:
            self._records = []
            self.header_label.setText(STRINGS.files_no_selection)
        else:
            # Перепривязываем запись к сессии дока (таблица живёт в другой)
            document = self.session.get(type(self._document), self._document.id)
            if document is None:
                self._document = None
                self._records = []
                self.header_label.setText(STRINGS.files_no_selection)
            else:
                self._document = document
                self._records = list(document.files)
                number = document.outgoing_number or "—"
                date_value = document.outgoing_date
                date_text = date_value.strftime("%d.%m.%Y") if date_value else "—"
                if isinstance(document, ScientificMaterial):
                    self.header_label.setText(
                        STRINGS.files_label_material.format(
                            number=number, date=date_text
                        )
                    )
                    self.setWindowTitle(entity_label(ScientificMaterial, plural=True))
                else:
                    self.header_label.setText(
                        STRINGS.files_label_telegram.format(
                            number=number, date=date_text
                        )
                    )
                    self.setWindowTitle(entity_label(Telegram, plural=True))
        self._reload_list()
        self._update_state()

    # --- служебное ---

    def _service(self):
        """Возвращает сервис документа текущей записи."""
        if isinstance(self._document, ScientificMaterial):
            return ScientificMaterialService(self.session, self.storage_root)
        return TelegramService(self.session, self.storage_root)

    def _record_path(self, record: FileRecord) -> Path:
        """Возвращает полный путь файла записи в хранилище."""
        return self.storage_root / record.path / f"{record.name}.{record.extension}"

    def _reload_list(self) -> None:
        self.list_widget.clear()
        for record in self._records:
            path = self._record_path(record)
            text = f"{record.name}.{record.extension}"
            item = QListWidgetItem(self._icon(path), text)
            item.setData(Qt.UserRole, record.id)
            item.setData(Qt.UserRole + 1, str(path))
            if not path.exists():
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(BROKEN_FILE_COLOR)
                item.setToolTip(STRINGS.tooltip_file_missing.format(path=path))
            self.list_widget.addItem(item)

    def _icon(self, path: Path) -> QIcon:
        """Возвращает стандартный значок для файла."""
        if path.exists():
            return self._icon_provider.icon(QFileInfo(str(path)))
        return self._icon_provider.icon(QFileIconProvider.File)

    def _update_state(self) -> None:
        """Включает кнопки только при привязанной записи."""
        enabled = self._document is not None and self._thread is None
        self.add_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)

    def _selected_records(self) -> List[FileRecord]:
        """Возвращает записи, выбранные в списке."""
        ids = {item.data(Qt.UserRole) for item in self.list_widget.selectedItems()}
        return [record for record in self._records if record.id in ids]

    def _check_outgoing(self) -> bool:
        """Проверяет, заданы ли исходящий номер и дата (нужны для папки)."""
        if self._document.outgoing_number and self._document.outgoing_date:
            return True
        QMessageBox.warning(
            self, STRINGS.title_attention, STRINGS.files_no_outgoing
        )
        return False

    # --- добавление файлов ---

    def _add_files_dialog(self) -> None:
        """Открывает диалог выбора файлов для прикрепления."""
        paths, _ = QFileDialog.getOpenFileNames(self, STRINGS.dialog_select_files)
        if paths:
            self._add_paths([Path(path) for path in paths])

    def _add_paths(self, paths: List[Path]) -> None:
        """Прикрепляет файлы: копирование в потоке, затем привязка в БД."""
        if self._document is None or self._thread is not None:
            return
        if not self._check_outgoing():
            return
        sources = [Path(path) for path in paths if Path(path).is_file()]
        if not sources:
            return

        try:
            inside = [
                path for path in sources if is_inside_storage(path, self.storage_root)
            ]
            outside = [
                path
                for path in sources
                if not is_inside_storage(path, self.storage_root)
            ]
            # Файлы внутри хранилища дублируются — только привязка
            if inside:
                self._service().link_existing_files(self._document, inside)

            pairs = self._resolve_conflicts(outside)
            if not pairs and not inside:
                return
            if pairs:
                self._run_copy_thread(pairs)
                return
            self.session.commit()
            self.refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка прикрепления файлов")
            self.session.rollback()
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.files_add_error.format(error=exc)
            )

    def _resolve_conflicts(self, sources: List[Path]) -> List[tuple]:
        """Спрашивает о совпадениях имён; возвращает пары (источник, назначение)."""
        service = self._service()
        targets = service.plan_copy_targets(self._document, sources)
        pairs = []
        for source, target in targets:
            if not target.exists():
                pairs.append((source, target))
                continue
            box = QMessageBox(self)
            box.setWindowTitle(STRINGS.title_attention)
            box.setIcon(QMessageBox.Question)
            box.setText(
                STRINGS.files_conflict_text.format(name=source.name)
            )
            replace_btn = box.addButton(
                STRINGS.files_replace, QMessageBox.AcceptRole
            )
            rename_btn = box.addButton(
                STRINGS.files_rename_new, QMessageBox.ActionRole
            )
            skip_btn = box.addButton(STRINGS.files_skip, QMessageBox.RejectRole)
            box.exec_()
            clicked = box.clickedButton()
            if clicked is replace_btn:
                pairs.append((source, target))
            elif clicked is rename_btn:
                pairs.append(
                    (source, unique_target_path(target.parent, source.name))
                )
            elif clicked is skip_btn:
                continue
            else:  # закрыто окно — считаем отменой
                break
        return pairs

    def _run_copy_thread(self, pairs: List[tuple]) -> None:
        """Запускает копирование в отдельном потоке с прогресс-диалогом."""
        progress = QProgressDialog(self)
        progress.setWindowTitle(STRINGS.tooltip_add_files)
        progress.setWindowModality(Qt.WindowModal)
        progress.setRange(0, len(pairs))
        progress.setCancelButtonText(STRINGS.button_cancel)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.canceled.connect(lambda: worker.cancel() if worker else None)

        thread = QThread(self)
        worker = CopyFilesWorker(pairs)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progressed.connect(progress.setLabelText)
        worker.step.connect(progress.setValue)

        def _done(completed: List[tuple]) -> None:
            progress.close()
            self._finish_copy(thread, worker)
            if completed:
                try:
                    self._service().attach_copied_files(self._document, completed)
                    self.session.commit()
                    QMessageBox.information(
                        self,
                        STRINGS.tooltip_add_files,
                        STRINGS.files_attached_info.format(count=len(completed)),
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    logger.exception("Ошибка привязки файлов")
                    self.session.rollback()
                    QMessageBox.critical(
                        self,
                        STRINGS.title_error,
                        STRINGS.files_add_error.format(error=exc),
                    )
            self.refresh()

        def _failed(message: str) -> None:
            progress.close()
            self._finish_copy(thread, worker)
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.files_add_error.format(error=message)
            )
            self.refresh()

        worker.finished.connect(_done)
        worker.failed.connect(_failed)
        self._thread = thread
        self._update_state()
        thread.start()

    def _finish_copy(self, thread: QThread, worker: CopyFilesWorker) -> None:
        """Останавливает поток копирования и освобождает ресурсы."""
        thread.quit()
        thread.wait(2000)
        worker.deleteLater()
        thread.deleteLater()
        self._thread = None
        self._update_state()

    # --- удаление, открытие, контекстное меню ---

    def _remove_selected(self) -> None:
        """Открепляет выбранные файлы; неразделённые удаляются с диска."""
        records = self._selected_records()
        if not records:
            return
        reply = QMessageBox.question(
            self,
            STRINGS.title_confirm,
            STRINGS.files_detach_confirm.format(count=len(records)),
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._service().detach_files(self._document, records)
            self.session.commit()
            self.refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка открепления файлов")
            self.session.rollback()
            QMessageBox.critical(self, STRINGS.title_error, str(exc))

    def _open_item(self, item: QListWidgetItem) -> None:
        """Открывает файл средствами операционной системы."""
        path = Path(item.data(Qt.UserRole + 1) or "")
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
        item = self.list_widget.itemAt(position)
        if item is None:
            return
        menu = QMenu(self)
        rename_action = menu.addAction(STRINGS.action_rename)
        reveal_action = menu.addAction(STRINGS.action_reveal)
        chosen = menu.exec_(self.list_widget.viewport().mapToGlobal(position))
        if chosen is rename_action:
            self._rename_selected()
        elif chosen is reveal_action:
            self._reveal_selected()

    def _rename_selected(self) -> None:
        """Переименовывает выбранные файлы (по одному, с подтверждением)."""
        records = self._selected_records()
        if not records:
            return
        if len(records) > 1:
            reply = QMessageBox.question(
                self,
                STRINGS.title_confirm,
                STRINGS.files_rename_many.format(count=len(records)),
            )
            if reply != QMessageBox.Yes:
                return
        service = self._service()
        try:
            for record in records:
                old_name = f"{record.name}.{record.extension}"
                new_name, ok = QInputDialog.getText(
                    self,
                    STRINGS.files_rename_title,
                    STRINGS.files_rename_prompt,
                    text=old_name,
                )
                if not ok:
                    break
                if new_name.strip() and new_name.strip() != old_name:
                    service.rename_file(record, new_name.strip())
            self.session.commit()
            self.refresh()
        except DocumentServiceError as exc:
            self.session.rollback()
            QMessageBox.critical(self, STRINGS.title_error, str(exc))

    def _reveal_selected(self) -> None:
        """Открывает папку файла в проводнике ОС (файл выделен)."""
        records = self._selected_records()
        if not records:
            return
        path = self._record_path(records[0])
        folder = path.parent
        if not folder.exists():
            QMessageBox.warning(
                self,
                STRINGS.title_attention,
                STRINGS.tooltip_file_missing.format(path=path),
            )
            return
        if os.name == "nt":
            # Windows: проводник с выделенным файлом
            try:
                subprocess.Popen(_explorer_select_command(path))
            except OSError:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
