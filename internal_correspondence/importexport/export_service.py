"""Экспорт изменений в ZIP-архив."""

import json
import os
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import DELETION_MARKER, EXPORT_DIR
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import Change, FileRecord
from internal_correspondence.services.change_tracking import clear_change

logger = get_logger("export_service")


class ExportService:
    """Формирует экспортный ZIP-архив с изменёнными сущностями и файлами."""

    def __init__(self, session: Session, storage_root: Path) -> None:
        self.session = session
        self.storage_root = storage_root
        self.export_dir = storage_root / EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export(self, output_path: Optional[Path] = None) -> Path:
        """Формирует экспортный архив и возвращает путь к нему."""
        changes = self.session.query(Change).all()
        if not changes:
            raise ExportError("Нет изменений для экспорта")

        export_data = self._build_export_data(changes)
        file_records = self._collect_files(export_data)

        if output_path is None:
            filename = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.zip"
            output_path = self.export_dir / filename

        self._pack_archive(output_path, export_data, file_records)
        self._clear_changes(changes)
        logger.info("Экспорт завершён: %s", output_path)
        return output_path

    def _build_export_data(self, changes: List[Change]) -> Dict[str, Any]:
        """Формирует словарь экспорта на основе записей Change."""
        export_data: Dict[str, Any] = {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "changes": [],
        }
        for change in changes:
            record = self._serialize_change(change)
            export_data["changes"].append(record)
        return export_data

    def _serialize_change(self, change: Change) -> Dict[str, Any]:
        """Сериализует одну запись Change вместе с данными сущности."""
        entity_class = self._resolve_entity_class(change.entity_name)
        record: Dict[str, Any] = {
            "entity_name": change.entity_name,
            "entity_pk": change.entity_pk,
            "changed_at": change.changed_at.isoformat() if change.changed_at else None,
            "changed_fields": change.changed_fields or [],
        }

        if DELETION_MARKER in (change.changed_fields or []):
            record["deleted"] = True
            return record

        if entity_class is None:
            logger.warning("Неизвестная сущность: %s", change.entity_name)
            return record

        instance = self.session.get(entity_class, self._parse_pk(change.entity_pk, entity_class))
        if instance is None:
            logger.warning("Сущность не найдена: %s pk=%s", change.entity_name, change.entity_pk)
            return record

        fields = [f for f in (change.changed_fields or []) if f != DELETION_MARKER]
        record["data"] = instance.to_dict(fields)
        return record

    def _resolve_entity_class(self, entity_name: str) -> Optional[type]:
        """Возвращает класс ORM-модели по имени сущности."""
        from internal_correspondence.orm import models
        return getattr(models, entity_name, None)

    def _parse_pk(self, pk_str: str, entity_class: type) -> Any:
        """Преобразует строковое представление PK в тип первичного ключа."""
        pk_columns = entity_class.__mapper__.primary_key
        if len(pk_columns) == 1:
            col_type = pk_columns[0].type
            # UUID
            if "UUID" in str(type(col_type)).upper():
                return uuid.UUID(pk_str)
            # Integer
            if "INTEGER" in str(type(col_type)).upper():
                try:
                    return int(pk_str)
                except ValueError:
                    return pk_str
            return pk_str
        # Составной ключ (не используется в проекте)
        return pk_str.split("_")

    def _collect_files(self, export_data: Dict[str, Any]) -> List[FileRecord]:
        """Собирает прикреплённые файлы для включения в архив."""
        file_ids: set = set()
        for record in export_data.get("changes", []):
            data = record.get("data", {})
            files = data.get("files", [])
            for file_ref in files:
                if isinstance(file_ref, dict) and "id" in file_ref:
                    file_ids.add(uuid.UUID(file_ref["id"]))
                elif isinstance(file_ref, str):
                    try:
                        file_ids.add(uuid.UUID(file_ref))
                    except ValueError:
                        pass

        files = []
        for file_id in file_ids:
            file_record = self.session.get(FileRecord, file_id)
            if file_record:
                files.append(file_record)
        return files

    def _pack_archive(
        self,
        output_path: Path,
        export_data: Dict[str, Any],
        file_records: List[FileRecord],
    ) -> None:
        """Упаковывает JSON и файлы в ZIP-архив."""
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("export.json", json.dumps(export_data, ensure_ascii=False, indent=2))
            for file_record in file_records:
                source_path = self.storage_root / file_record.path / f"{file_record.name}.{file_record.extension}"
                if source_path.exists():
                    arcname = f"files/{file_record.id}/{file_record.name}.{file_record.extension}"
                    zf.write(source_path, arcname)
                else:
                    logger.warning("Файл не найден: %s", source_path)

    def _clear_changes(self, changes: List[Change]) -> None:
        """Удаляет записи Change после успешного экспорта."""
        for change in changes:
            self.session.delete(change)
        self.session.flush()


class ExportError(Exception):
    """Ошибка формирования экспортного архива."""

    pass
