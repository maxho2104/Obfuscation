"""Сервисы для работы с научными материалами и телеграммами."""

import shutil
import uuid
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import (
    MATERIAL_FILES_DIR,
    TELEGRAM_FILES_DIR,
)
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.models import FileRecord, ScientificMaterial, Telegram
from internal_correspondence.services.base_service import BaseService

logger = get_logger("document_service")


class DocumentServiceError(Exception):
    """Ошибка бизнес-логики документов."""

    pass


class ScientificMaterialService(BaseService[ScientificMaterial]):
    """Сервис научных материалов с прикреплением файлов."""

    def __init__(self, session: Session, storage_root: Path) -> None:
        super().__init__(session, ScientificMaterial)
        self.storage_root = storage_root

    def create_with_files(
        self,
        data: Dict[str, any],
        file_paths: Optional[List[Path]] = None,
    ) -> ScientificMaterial:
        """Создаёт материал и копирует прикреплённые файлы в хранилище."""
        material = self.create(data)
        self.session.flush()
        if file_paths:
            for file_path in file_paths:
                self._attach_file(material, file_path)
        return material

    def update_with_files(
        self,
        material: ScientificMaterial,
        data: Dict[str, any],
        new_files: Optional[List[Path]] = None,
    ) -> ScientificMaterial:
        """Обновляет материал и добавляет новые файлы."""
        self.update(material, data)
        if new_files:
            for file_path in new_files:
                self._attach_file(material, file_path)
        return material

    def _attach_file(self, material: ScientificMaterial, source_path: Path) -> FileRecord:
        """Прикрепляет файл к материалу, копируя его в хранилище."""
        if not source_path.exists():
            raise DocumentServiceError(f"Файл не найден: {source_path}")

        relative_dir = self._file_relative_dir(material)
        target_dir = self.storage_root / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Если файл уже внутри хранилища — не копируем, создаём только ссылку
        try:
            source_path.relative_to(self.storage_root)
            is_inside_storage = True
        except ValueError:
            is_inside_storage = False

        file_name = source_path.stem
        extension = source_path.suffix.lstrip(".")
        target_path = target_dir / f"{file_name}.{extension}"

        if not is_inside_storage:
            shutil.copy2(source_path, target_path)
            logger.debug("Скопирован файл %s -> %s", source_path, target_path)
        else:
            target_path = source_path

        file_record = FileRecord(
            name=file_name,
            extension=extension,
            path=str(relative_dir).replace("\\", "/"),
        )
        self.session.add(file_record)
        material.files.append(file_record)
        self.session.flush()
        return file_record

    def _file_relative_dir(self, material: ScientificMaterial) -> Path:
        """Возвращает относительную директорию для файлов материала."""
        date_str = material.outgoing_date.isoformat() if material.outgoing_date else "unknown"
        return Path("Файлы") / MATERIAL_FILES_DIR / date_str / (material.outgoing_number or str(material.id))


class TelegramService(BaseService[Telegram]):
    """Сервис телеграмм с прикреплением файлов."""

    def __init__(self, session: Session, storage_root: Path) -> None:
        super().__init__(session, Telegram)
        self.storage_root = storage_root

    def create_with_files(
        self,
        data: Dict[str, any],
        file_paths: Optional[List[Path]] = None,
    ) -> Telegram:
        telegram = self.create(data)
        self.session.flush()
        if file_paths:
            for file_path in file_paths:
                self._attach_file(telegram, file_path)
        return telegram

    def update_with_files(
        self,
        telegram: Telegram,
        data: Dict[str, any],
        new_files: Optional[List[Path]] = None,
    ) -> Telegram:
        self.update(telegram, data)
        if new_files:
            for file_path in new_files:
                self._attach_file(telegram, file_path)
        return telegram

    def _attach_file(self, telegram: Telegram, source_path: Path) -> FileRecord:
        if not source_path.exists():
            raise DocumentServiceError(f"Файл не найден: {source_path}")

        relative_dir = self._file_relative_dir(telegram)
        target_dir = self.storage_root / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            source_path.relative_to(self.storage_root)
            is_inside_storage = True
        except ValueError:
            is_inside_storage = False

        file_name = source_path.stem
        extension = source_path.suffix.lstrip(".")
        target_path = target_dir / f"{file_name}.{extension}"

        if not is_inside_storage:
            shutil.copy2(source_path, target_path)

        file_record = FileRecord(
            name=file_name,
            extension=extension,
            path=str(relative_dir).replace("\\", "/"),
        )
        self.session.add(file_record)
        telegram.files.append(file_record)
        self.session.flush()
        return file_record

    def _file_relative_dir(self, telegram: Telegram) -> Path:
        date_str = telegram.outgoing_date.isoformat() if telegram.outgoing_date else "unknown"
        return Path("Файлы") / TELEGRAM_FILES_DIR / date_str / (telegram.outgoing_number or str(telegram.id))
