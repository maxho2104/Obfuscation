"""Виджет списка прикреплённых файлов."""

from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QFileInfo, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFileIconProvider,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.models import FileRecord

logger = get_logger("attached_files_widget")

# Цвет отображения файла, ссылка на который в БД «битая»
BROKEN_FILE_COLOR = QColor(190, 40, 40)


class FileListWidget(QListWidget):
    """Список файлов с компактными кнопками действий внутри поля."""

    BUTTON_SIZE = 35
    MARGIN = 8
    GAP = 2

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.add_button = QPushButton("+", self)
        self.add_button.setProperty("role", "successCompact")
        self.add_button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)

        self.remove_button = QPushButton("-", self)
        self.remove_button.setProperty("role", "dangerCompact")
        self.remove_button.setFixedSize(self.BUTTON_SIZE, self.BUTTON_SIZE)

        bottom_margin = self.BUTTON_SIZE + self.MARGIN * 2
        self.setViewportMargins(0, 0, 0, bottom_margin)

    def resizeEvent(self, event) -> None:  # noqa: N802 - имя метода Qt
        """Прижимает кнопки к нижнему правому углу списка."""
        super().resizeEvent(event)
        y = self.height() - self.BUTTON_SIZE - self.MARGIN
        remove_x = self.width() - self.BUTTON_SIZE - self.MARGIN
        add_x = remove_x - self.BUTTON_SIZE - self.GAP
        self.add_button.move(add_x, y)
        self.remove_button.move(remove_x, y)
        self.add_button.raise_()
        self.remove_button.raise_()


class AttachedFilesWidget(QWidget):
    """Виджет для отображения и управления прикреплёнными файлами."""

    def __init__(self, storage_root: Path, parent=None) -> None:
        super().__init__(parent)
        self.storage_root = storage_root
        self.file_records: List[FileRecord] = []
        self.new_files: List[Path] = []
        self._icon_provider = QFileIconProvider()
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = FileListWidget()
        self.list_widget.setObjectName("fileList")
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.list_widget)

        self.add_btn = self.list_widget.add_button
        self.add_btn.setToolTip("Добавить файлы")
        self.add_btn.clicked.connect(self._add_files)

        self.remove_btn = self.list_widget.remove_button
        self.remove_btn.setToolTip("Открепить выбранные файлы")
        self.remove_btn.clicked.connect(self._remove_files)

    def set_files(self, file_records: List[FileRecord]) -> None:
        """Устанавливает текущий список прикреплённых файлов из БД."""
        self.file_records = list(file_records)
        self.new_files.clear()
        self._refresh_list()

    def get_new_files(self) -> List[Path]:
        """Возвращает список вновь выбранных файлов для копирования."""
        return list(self.new_files)

    def get_records_to_remove(self) -> List[FileRecord]:
        """Возвращает записи FileRecord, отмеченные на удаление."""
        # В текущей реализации удаление из виджета означает удаление из БД
        return []

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for record in self.file_records:
            text = f"{record.name}.{record.extension}"
            file_path = self.file_path(record)
            item = QListWidgetItem(self._icon(file_path), text)
            item.setData(Qt.UserRole, record.id)
            if not file_path.exists():
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(BROKEN_FILE_COLOR)
                item.setToolTip(f"Файл отсутствует в хранилище: {file_path}")
            self.list_widget.addItem(item)

        for path in self.new_files:
            item = QListWidgetItem(self._icon(path), f"{path.name} (новый)")
            item.setData(Qt.UserRole, str(path))
            self.list_widget.addItem(item)

    def _icon(self, path: Path):
        """Возвращает стандартный значок для файла."""
        if path.exists():
            return self._icon_provider.icon(QFileInfo(str(path)))
        return self._icon_provider.icon(QFileIconProvider.File)

    def file_path(self, record: FileRecord) -> Path:
        """Возвращает путь к файлу записи в файловом хранилище."""
        return self.storage_root / record.path / f"{record.name}.{record.extension}"

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Выберите файлы")
        for path in paths:
            self.new_files.append(Path(path))
        self._refresh_list()

    def _remove_files(self) -> None:
        selected = self.list_widget.selectedItems()
        if not selected:
            return
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Открепить выбранные файлы ({len(selected)})?",
        )
        if reply != QMessageBox.Yes:
            return

        for item in selected:
            data = item.data(Qt.UserRole)
            if isinstance(data, str):
                path = Path(data)
                if path in self.new_files:
                    self.new_files.remove(path)
            else:
                record = next((r for r in self.file_records if r.id == data), None)
                if record:
                    self.file_records.remove(record)
        self._refresh_list()
