"""Сервисы для работы с научными материалами и телеграммами."""

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session

from internal_correspondence.core.domain_pack import dir_name
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.models import FileRecord, ScientificMaterial, Telegram
from internal_correspondence.services.base_service import BaseService
from internal_correspondence.services.file_service import (
    cleanup_empty_dirs,
    is_inside_storage,
)

logger = get_logger("document_service")

# Документы, к которым прикрепляются файлы
Document = Union[ScientificMaterial, Telegram]


class DocumentServiceError(Exception):
    """Ошибка бизнес-логики документов."""

    pass


class DocumentFilesMixin:
    """Общая логика прикрепления файлов к документам.

    Ожидает от наследника атрибут ``storage_root`` и классовый атрибут
    ``_files_dir_key`` — ключ поддиректории хранилища для типа документа
    в пакете предметной области.
    """

    storage_root: Path
    _files_dir_key: str

    def _attach_file(self, document: Document, source_path: Path) -> FileRecord:
        """Прикрепляет файл к документу, копируя его в хранилище."""
        if not source_path.exists():
            raise DocumentServiceError(f"Файл не найден: {source_path}")

        relative_dir = self._file_relative_dir(document)
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

        file_record = FileRecord(
            name=file_name,
            extension=extension,
            path=str(relative_dir).replace("\\", "/"),
        )
        self.session.add(file_record)
        document.files.append(file_record)
        self.session.flush()
        return file_record

    def _file_relative_dir(self, document: Document) -> Path:
        """Возвращает относительную директорию для файлов документа."""
        if document.outgoing_date is not None:
            date_str = document.outgoing_date.isoformat()
        else:
            date_str = "unknown"
        number = document.outgoing_number or str(document.id)
        return Path(dir_name("files")) / dir_name(self._files_dir_key) / date_str / number

    def plan_copy_targets(
        self, document: Document, source_paths: List[Path]
    ) -> List[tuple]:
        """Возвращает пары (источник, назначение) для файлов вне хранилища.

        Файлы внутри хранилища копированию не подлежат (см.
        :meth:`link_existing_files`). Назначение вычисляется по исходящему
        номеру и дате документа; разрешение конфликтов имён — на вызывающей
        стороне (виджет спрашивает пользователя).
        """
        relative_dir = self._file_relative_dir(document)
        target_dir = self.storage_root / relative_dir
        return [
            (source, target_dir / source.name)
            for source in source_paths
            if not is_inside_storage(source, self.storage_root)
        ]

    def link_existing_files(
        self, document: Document, paths: List[Path]
    ) -> List[FileRecord]:
        """Привязывает файлы из хранилища без копирования (только связь)."""
        records = []
        for path in paths:
            relative = path.resolve().relative_to(self.storage_root.resolve())
            record = self._find_or_create_record(relative.parent, path.name)
            if record not in document.files:
                document.files.append(record)
            records.append(record)
        self.session.flush()
        return records

    def attach_copied_files(
        self, document: Document, pairs: List[tuple]
    ) -> List[FileRecord]:
        """Привязывает уже скопированные в хранилище файлы (только связь в БД)."""
        records = []
        for _source, target in pairs:
            relative = target.resolve().relative_to(self.storage_root.resolve())
            record = self._find_or_create_record(relative.parent, target.name)
            if record not in document.files:
                document.files.append(record)
            records.append(record)
        self.session.flush()
        return records

    def detach_files(self, document: Document, records: List[FileRecord]) -> None:
        """Открепляет файлы; неразделённые записи удаляются с диска.

        Для каждого файла, не привязанного больше ни к одной записи,
        удаляется запись FileRecord и сам файл; пустые папки хранилища
        удаляются рекурсивно вплоть до корневой папки типа документа.
        """
        base_dir = self.storage_root / dir_name("files") / dir_name(self._files_dir_key)
        for record in records:
            if record in document.files:
                document.files.remove(record)
            self.session.flush()
            if record.materials or record.telegrams:
                continue  # файл разделён с другими записями — только отвязка
            file_path = (
                self.storage_root / record.path / f"{record.name}.{record.extension}"
            )
            parent = file_path.parent
            self.session.delete(record)
            self.session.flush()
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError as exc:
                    logger.warning("Не удалось удалить файл %s: %s", file_path, exc)
                    continue
            cleanup_empty_dirs(parent, base_dir)

    def rename_file(self, record: FileRecord, new_name: str) -> None:
        """Переименовывает файл на диске и обновляет запись в БД."""
        new_name = new_name.strip()
        if not new_name:
            raise DocumentServiceError("Имя файла не задано")
        old_path = (
            self.storage_root / record.path / f"{record.name}.{record.extension}"
        )
        target = old_path.with_name(new_name)
        if target.exists() and target != old_path:
            raise DocumentServiceError(f"Файл с именем {new_name} уже существует")
        if old_path.exists() and old_path != target:
            try:
                old_path.rename(target)
            except OSError as exc:
                raise DocumentServiceError(f"Не удалось переименовать файл: {exc}")
        record.name = target.stem
        record.extension = target.suffix.lstrip(".")
        self.session.flush()

    def _find_or_create_record(self, relative: Path, file_name: str) -> FileRecord:
        """Возвращает существующую запись файла или создаёт новую."""
        record = (
            self.session.query(FileRecord)
            .filter_by(
                path=str(relative).replace("\\", "/"),
                name=Path(file_name).stem,
                extension=Path(file_name).suffix.lstrip("."),
            )
            .first()
        )
        if record is None:
            record = FileRecord(
                name=Path(file_name).stem,
                extension=Path(file_name).suffix.lstrip("."),
                path=str(relative).replace("\\", "/"),
            )
            self.session.add(record)
            self.session.flush()
        return record


class ScientificMaterialService(DocumentFilesMixin, BaseService[ScientificMaterial]):
    """Сервис научных материалов с прикреплением файлов."""

    _files_dir_key = "material_files"

    def __init__(self, session: Session, storage_root: Path) -> None:
        super().__init__(session, ScientificMaterial)
        self.storage_root = storage_root

    def create_with_files(
        self,
        data: Dict[str, Any],
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
        data: Dict[str, Any],
        new_files: Optional[List[Path]] = None,
    ) -> ScientificMaterial:
        """Обновляет материал и добавляет новые файлы."""
        self.update(material, data)
        if new_files:
            for file_path in new_files:
                self._attach_file(material, file_path)
        return material


class TelegramService(DocumentFilesMixin, BaseService[Telegram]):
    """Сервис телеграмм с прикреплением файлов."""

    _files_dir_key = "telegram_files"

    def __init__(self, session: Session, storage_root: Path) -> None:
        super().__init__(session, Telegram)
        self.storage_root = storage_root

    def create_with_files(
        self,
        data: Dict[str, Any],
        file_paths: Optional[List[Path]] = None,
    ) -> Telegram:
        """Создаёт телеграмму и копирует прикреплённые файлы в хранилище."""
        telegram = self.create(data)
        self.session.flush()
        if file_paths:
            for file_path in file_paths:
                self._attach_file(telegram, file_path)
        return telegram

    def update_with_files(
        self,
        telegram: Telegram,
        data: Dict[str, Any],
        new_files: Optional[List[Path]] = None,
    ) -> Telegram:
        """Обновляет телеграмму и добавляет новые файлы."""
        self.update(telegram, data)
        if new_files:
            for file_path in new_files:
                self._attach_file(telegram, file_path)
        return telegram
