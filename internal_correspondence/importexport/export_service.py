"""Экспорт изменений в ZIP-архив."""

import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import (
    DEFAULT_CHANGES_RETENTION_DAYS,
    ChangeOperation,
)
from internal_correspondence.core.domain_pack import dir_name, get_domain_pack
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.models import Change, FileRecord
from internal_correspondence.orm.utils import parse_primary_key, resolve_entity_class
from internal_correspondence.services.change_tracking import purge_expired_changes

logger = get_logger("export_service")


class ExportService:
    """Формирует экспортный ZIP-архив с изменёнными сущностями и файлами."""

    def __init__(
        self,
        session: Session,
        storage_root: Path,
        retention_days: int = DEFAULT_CHANGES_RETENTION_DAYS,
    ) -> None:
        self.session = session
        self.storage_root = storage_root
        self.retention_days = retention_days
        self.export_dir = storage_root / dir_name("export")
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export(self, output_path: Optional[Path] = None) -> Path:
        """Формирует экспортный архив и возвращает путь к нему."""
        changes = (
            self.session.query(Change).filter(Change.exported_at.is_(None)).all()
        )
        if not changes:
            raise ExportError("Нет изменений для экспорта")

        export_data = self._build_export_data(changes)
        if not export_data:
            raise ExportError("Нет данных для экспорта")

        file_records = self._collect_files(export_data)

        if output_path is None:
            filename = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.zip"
            output_path = self.export_dir / filename

        self._pack_archive(output_path, export_data, file_records)
        self._mark_exported(changes)
        purge_expired_changes(self.session, self.retention_days)
        logger.info("Экспорт завершён: %s", output_path)
        return output_path

    def _build_export_data(self, changes: List[Change]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Формирует словарь экспорта: сущность -> первичный ключ -> изменённые поля."""
        export_data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        deleted_keys: Set[Tuple[str, str]] = set()

        for change in changes:
            if change.operation_type != ChangeOperation.DELETE.value:
                continue
            deleted_keys.add((change.entity_name, change.entity_pk))
            export_data.setdefault(change.entity_name, {})[change.entity_pk] = {"deleted": True}

        for change in changes:
            if change.operation_type == ChangeOperation.DELETE.value:
                continue
            if (change.entity_name, change.entity_pk) in deleted_keys:
                continue

            entity_class = resolve_entity_class(change.entity_name)
            if entity_class is None:
                logger.warning("Неизвестная сущность: %s", change.entity_name)
                continue

            fields = self._column_fields(entity_class, change.changed_fields or [])
            relationships = self._relationship_fields(entity_class, change.changed_fields or [])
            if not fields and not relationships:
                logger.warning(
                    "Нет изменяемых полей для экспорта: %s pk=%s",
                    change.entity_name,
                    change.entity_pk,
                )
                continue

            instance = self.session.get(
                entity_class,
                parse_primary_key(change.entity_pk, entity_class),
            )
            if instance is None:
                logger.warning(
                    "Сущность не найдена: %s pk=%s",
                    change.entity_name,
                    change.entity_pk,
                )
                continue

            bucket = export_data.setdefault(change.entity_name, {})
            record = bucket.setdefault(change.entity_pk, {})
            if fields:
                record.update(instance.to_dict(fields))
            for name in relationships:
                record[name] = self._serialize_relationship(instance, name)

        return export_data

    def _column_fields(self, entity_class: type, fields: List[str]) -> List[str]:
        """Оставляет только имена колонок ORM-модели."""
        columns = set(entity_class.__mapper__.columns.keys())
        return [field for field in fields if field in columns]

    def _relationship_fields(self, entity_class: type, fields: List[str]) -> List[str]:
        """Оставляет только имена связей N-N ORM-модели."""
        relationships = {
            relationship.key
            for relationship in entity_class.__mapper__.relationships
            if relationship.secondary is not None
        }
        return [field for field in fields if field in relationships]

    def _serialize_relationship(self, instance: Any, name: str) -> List[str]:
        """Сериализует состав связи N-N как список первичных ключей."""
        related = getattr(instance, name, None) or []
        return sorted(self._instance_pk(item) for item in related)

    @staticmethod
    def _instance_pk(instance: Any) -> str:
        """Возвращает строковое представление первичного ключа объекта."""
        pk = instance.__mapper__.primary_key_from_instance(instance)
        return "_".join(str(value) for value in pk)

    def _collect_files(self, export_data: Dict[str, Dict[str, Any]]) -> List[FileRecord]:
        """Собирает прикреплённые файлы для включения в архив.

        В архив попадают как файлы, перечисленные в связях ``files``
        экспортируемых записей, так и сами изменённые записи ``FileRecord``.
        """
        file_ids: set = set()
        for entities in export_data.values():
            for record in entities.values():
                for file_ref in record.get("files", []) or []:
                    if isinstance(file_ref, dict) and "id" in file_ref:
                        self._add_file_id(file_ids, file_ref["id"])
                    elif isinstance(file_ref, str):
                        self._add_file_id(file_ids, file_ref)

        for pk, record in export_data.get("FileRecord", {}).items():
            if isinstance(record, dict) and record.get("deleted"):
                continue
            self._add_file_id(file_ids, pk)

        files = []
        for file_id in file_ids:
            file_record = self.session.get(FileRecord, file_id)
            if file_record:
                files.append(file_record)
        return files

    @staticmethod
    def _add_file_id(file_ids: set, value: Any) -> None:
        """Добавляет идентификатор файла в набор, если он корректен."""
        try:
            file_ids.add(uuid.UUID(str(value)))
        except ValueError:
            logger.warning("Некорректный идентификатор файла: %s", value)

    def _pack_archive(
        self,
        output_path: Path,
        export_data: Dict[str, Any],
        file_records: List[FileRecord],
    ) -> None:
        """Упаковывает JSON и файлы в ZIP-архив."""
        pack = get_domain_pack()
        meta = {
            "app": "internal-correspondence",
            "pack_id": pack.id,
            "pack_version": pack.version,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
            zf.writestr("export.json", json.dumps(export_data, ensure_ascii=False, indent=2))
            storage_root = self.storage_root.resolve()
            for file_record in file_records:
                source_path = (
                    storage_root
                    / file_record.path
                    / f"{file_record.name}.{file_record.extension}"
                ).resolve()
                if storage_root not in source_path.parents:
                    logger.warning("Некорректный путь файла: %s", file_record.path)
                    continue
                if source_path.exists():
                    arcname = f"files/{file_record.id}/{file_record.name}.{file_record.extension}"
                    zf.write(source_path, arcname)
                else:
                    logger.warning("Файл не найден: %s", source_path)

    def _mark_exported(self, changes: List[Change]) -> None:
        """Отмечает записи Change экспортированными и сбрасывает change_id.

        Записи Change сохраняются (с датой экспорта) для дельта-учёта
        последующих изменений и удаляются позже по сроку хранения.
        """
        exported_at = datetime.now(timezone.utc).replace(tzinfo=None)
        for change in changes:
            entity_class = resolve_entity_class(change.entity_name)
            if entity_class is not None:
                try:
                    pk = parse_primary_key(change.entity_pk, entity_class)
                except (TypeError, ValueError):
                    pk = None
                if pk is not None:
                    instance = self.session.get(entity_class, pk)
                    if instance is not None and getattr(instance, "change_id", None) == change.id:
                        instance.change_id = None  # type: ignore[attr-defined]
            change.exported_at = exported_at
        self.session.flush()


class ExportError(Exception):
    """Ошибка формирования экспортного архива."""

    pass
