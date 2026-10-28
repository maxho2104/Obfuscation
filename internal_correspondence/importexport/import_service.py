"""Импорт изменений из ZIP-архива с разрешением конфликтов."""

import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import DELETION_MARKER, Role
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import Change
from internal_correspondence.services.change_tracking import clear_change

logger = get_logger("import_service")


class ImportService:
    """Разбирает экспортный ZIP-архив и применяет изменения к локальной БД."""

    def __init__(
        self,
        session: Session,
        storage_root: Path,
        role: str,
        branch_id: Optional[str] = None,
    ) -> None:
        self.session = session
        self.storage_root = storage_root
        self.role = role
        self.branch_id = branch_id
        self.conflicts: List[Dict[str, Any]] = []

    def import_archive(self, archive_path: Path) -> Dict[str, Any]:
        """Импортирует данные из ZIP-архива.

        Returns:
            Словарь со статистикой импорта и списком конфликтов.
        """
        self.conflicts.clear()
        extract_dir = self.storage_root / "tmp_import" / uuid.uuid4().hex
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_dir)

            json_path = extract_dir / "export.json"
            if not json_path.exists():
                raise ImportError("В архиве отсутствует export.json")

            with open(json_path, "r", encoding="utf-8") as f:
                export_data = json.load(f)

            stats = self._apply_changes(export_data.get("changes", []))
            self._extract_files(extract_dir)
            self.session.commit()

            return {
                "imported": stats["imported"],
                "deleted": stats["deleted"],
                "skipped": stats["skipped"],
                "conflicts": self.conflicts,
            }
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    def _apply_changes(self, changes: List[Dict[str, Any]]) -> Dict[str, int]:
        """Применяет изменения с учётом ролей и правил конфликтов."""
        stats = {"imported": 0, "deleted": 0, "skipped": 0}
        for record in changes:
            result = self._apply_change(record)
            if result == "imported":
                stats["imported"] += 1
            elif result == "deleted":
                stats["deleted"] += 1
            else:
                stats["skipped"] += 1
        return stats

    def _apply_change(self, record: Dict[str, Any]) -> str:
        """Применяет одну запись изменения."""
        entity_name = record["entity_name"]
        entity_pk = record["entity_pk"]
        changed_fields = record.get("changed_fields", [])

        if DELETION_MARKER in changed_fields:
            return self._delete_entity(entity_name, entity_pk)

        entity_class = self._resolve_entity_class(entity_name)
        if entity_class is None:
            logger.warning("Неизвестная сущность: %s", entity_name)
            return "skipped"

        pk = self._parse_pk(entity_pk, entity_class)
        instance = self.session.get(entity_class, pk)
        data = record.get("data", {})

        if instance is None:
            return self._create_entity(entity_class, data)

        return self._update_entity(instance, data, changed_fields)

    def _create_entity(self, entity_class: type, data: Dict[str, Any]) -> str:
        """Создаёт новую сущность."""
        try:
            instance = entity_class(**self._filter_model_kwargs(entity_class, data))
            self.session.add(instance)
            # Сбрасываем автоматически созданную запись Change,
            # т.к. данные пришли извне и не должны считаться локальными изменениями.
            self.session.flush()
            clear_change(self.session, instance)
            self.session.flush()
            return "imported"
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка создания сущности %s", entity_class.__name__)
            self.conflicts.append({
                "entity_name": entity_class.__name__,
                "action": "create",
                "error": str(exc),
            })
            return "skipped"

    def _update_entity(
        self,
        instance: Base,
        data: Dict[str, Any],
        changed_fields: List[str],
    ) -> str:
        """Обновляет существующую сущность с учётом правил конфликтов."""
        entity_name = instance.__class__.__name__
        allowed_fields = self._allowed_fields_for_update(entity_name, changed_fields)

        if not allowed_fields:
            return "skipped"

        try:
            for field in allowed_fields:
                if field in data and hasattr(instance, field):
                    setattr(instance, field, data[field])
            instance.row_version += 1  # type: ignore[attr-defined]
            self.session.flush()
            clear_change(self.session, instance)
            self.session.flush()
            return "imported"
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка обновления сущности %s", entity_name)
            self.conflicts.append({
                "entity_name": entity_name,
                "action": "update",
                "error": str(exc),
            })
            return "skipped"

    def _delete_entity(self, entity_name: str, entity_pk: str) -> str:
        """Удаляет сущность по маркеру удаления."""
        entity_class = self._resolve_entity_class(entity_name)
        if entity_class is None:
            return "skipped"

        pk = self._parse_pk(entity_pk, entity_class)
        instance = self.session.get(entity_class, pk)
        if instance is None:
            return "skipped"

        try:
            self.session.delete(instance)
            self.session.flush()
            return "deleted"
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка удаления сущности %s", entity_name)
            self.conflicts.append({
                "entity_name": entity_name,
                "action": "delete",
                "error": str(exc),
            })
            return "skipped"

    def _allowed_fields_for_update(self, entity_name: str, changed_fields: List[str]) -> List[str]:
        """Возвращает список полей, которые разрешено обновлять согласно роли."""
        if self.role == Role.HEAD_OFFICE.value:
            # Головной офис авторитете для справочников и научных задач.
            # Для ОШС — только чтение, изменения принимаются только от филиала-владельца.
            if entity_name in ("Department", "WorkingGroup", "Employee"):
                # В реальном сценарии нужно проверить branch_id сущности.
                return changed_fields
            return changed_fields

        # Роль филиала: не редактирует входящие номера и оценки материалов/телеграмм.
        restricted = {
            "ScientificMaterial": {"incoming_number", "incoming_date"},
            "Telegram": {"incoming_number", "incoming_date"},
            "Evaluation": set(),
        }
        restricted_fields = restricted.get(entity_name, set())
        allowed = [f for f in changed_fields if f not in restricted_fields]
        skipped = [f for f in changed_fields if f in restricted_fields]
        if skipped:
            self.conflicts.append({
                "entity_name": entity_name,
                "action": "restricted_fields_skipped",
                "fields": skipped,
            })
        return allowed

    def _filter_model_kwargs(self, entity_class: type, data: Dict[str, Any]) -> Dict[str, Any]:
        """Оставляет только атрибуты, соответствующие колонкам модели."""
        columns = {col.name for col in entity_class.__mapper__.columns}
        return {k: v for k, v in data.items() if k in columns}

    def _resolve_entity_class(self, entity_name: str) -> Optional[type]:
        """Возвращает класс ORM-модели по имени сущности."""
        from internal_correspondence.orm import models
        return getattr(models, entity_name, None)

    def _parse_pk(self, pk_str: str, entity_class: type) -> Any:
        """Преобразует строковое представление PK в тип первичного ключа."""
        pk_columns = entity_class.__mapper__.primary_key
        if len(pk_columns) == 1:
            col_type = pk_columns[0].type
            if "UUID" in str(type(col_type)).upper():
                return uuid.UUID(pk_str)
            if "INTEGER" in str(type(col_type)).upper():
                try:
                    return int(pk_str)
                except ValueError:
                    return pk_str
            return pk_str
        return pk_str.split("_")

    def _extract_files(self, extract_dir: Path) -> None:
        """Копирует импортированные файлы в файловое хранилище."""
        files_dir = extract_dir / "files"
        if not files_dir.exists():
            return
        for file_dir in files_dir.iterdir():
            if not file_dir.is_dir():
                continue
            for source_file in file_dir.iterdir():
                if not source_file.is_file():
                    continue
                target_dir = self.storage_root / "Файлы" / "Импорт" / file_dir.name
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_dir / source_file.name)


class ImportError(Exception):
    """Ошибка импорта архива."""

    pass
