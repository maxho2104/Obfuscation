"""Импорт изменений из ZIP-архива с разрешением зависимостей."""

import json
import shutil
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, Uuid
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import Role
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import Change, FileRecord
from internal_correspondence.services.change_tracking import clear_change

logger = get_logger("import_service")

# Служебные поля, которые не импортируются из JSON
_SERVICE_FIELDS = {"change_id", "row_version", "created_at", "updated_at"}


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
        self._payload: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._status: Dict[Tuple[str, str], str] = {}
        self._instances: Dict[Tuple[str, str], Base] = {}
        self._model_classes_cache: Optional[Dict[str, type]] = None

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

            if not isinstance(export_data, dict):
                raise ImportError("Некорректный формат export.json")

            stats = self._apply_payload(export_data)
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

    def _apply_payload(self, payload: Dict[str, Any]) -> Dict[str, int]:
        """Применяет данные экспорта к локальной БД."""
        self._payload = {}
        self._status = {}
        self._instances = {}

        for entity_name, entries in payload.items():
            if not isinstance(entries, dict):
                logger.warning("Пропущена служебная секция: %s", entity_name)
                continue
            if self._resolve_entity_class(entity_name) is None:
                logger.warning("Неизвестная сущность: %s", entity_name)
                continue
            self._payload[entity_name] = {
                str(pk): data for pk, data in entries.items() if isinstance(data, dict)
            }

        stats = {"imported": 0, "deleted": 0, "skipped": 0}
        deletions: List[Tuple[str, str]] = []

        for entity_name, entries in self._payload.items():
            for pk_key, fields in entries.items():
                if fields.get("deleted"):
                    deletions.append((entity_name, pk_key))
                    continue
                status = self._apply_entry(entity_name, pk_key, fields, frozenset())
                stats[status] += 1

        for entity_name, pk_key in deletions:
            status = self._delete_entry(entity_name, pk_key)
            stats[status] += 1

        return stats

    def _apply_entry(
        self,
        entity_name: str,
        pk_key: str,
        fields: Dict[str, Any],
        stack: Set[Tuple[str, str]],
    ) -> str:
        """Создаёт или обновляет одну запись из экспортного JSON."""
        key = (entity_name, pk_key)
        cached = self._status.get(key)
        if cached is not None:
            return cached

        entity_class = self._resolve_entity_class(entity_name)
        if entity_class is None:
            self._status[key] = "skipped"
            return "skipped"

        self._status[key] = "skipped"
        try:
            instance = self._upsert(entity_class, pk_key, fields, set(stack) | {key})
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка импорта сущности %s pk=%s", entity_name, pk_key)
            self.conflicts.append({
                "entity_name": entity_name,
                "entity_pk": pk_key,
                "action": "apply",
                "error": str(exc),
            })
            return "skipped"

        if instance is None:
            return "skipped"

        self._status[key] = "imported"
        self._instances[key] = instance
        return "imported"

    def _upsert(
        self,
        entity_class: type,
        pk_key: str,
        fields: Dict[str, Any],
        stack: Set[Tuple[str, str]],
    ) -> Optional[Base]:
        """Создаёт или обновляет запись, предварительно разрешая зависимости."""
        data = {name: value for name, value in fields.items() if name != "deleted"}
        relationship_specs = self._relationship_specs(entity_class)
        column_data = {name: value for name, value in data.items() if name not in relationship_specs}
        relation_data = {name: value for name, value in data.items() if name in relationship_specs}

        pk_values = self._parse_pk(pk_key, entity_class)
        instance = self.session.get(entity_class, pk_values)

        if instance is not None:
            allowed = set(
                self._allowed_fields_for_update(entity_class.__name__, list(data.keys()))
            )
            column_data = {name: value for name, value in column_data.items() if name in allowed}
            relation_data = {name: value for name, value in relation_data.items() if name in allowed}
            if not column_data and not relation_data:
                return None

        self._resolve_dependencies(entity_class, column_data, stack)

        if instance is None:
            instance = self._create_entity(entity_class, pk_values, column_data)
        else:
            self._update_entity(instance, column_data)

        self._apply_relationships(instance, relation_data, stack)

        self.session.flush()
        clear_change(self.session, instance)
        self.session.flush()
        return instance

    def _create_entity(self, entity_class: type, pk_values: Any, data: Dict[str, Any]) -> Base:
        """Создаёт новую сущность с заданным первичным ключом."""
        instance = entity_class()
        pk_columns = list(entity_class.__mapper__.primary_key)
        if len(pk_columns) == 1:
            setattr(instance, pk_columns[0].key, pk_values)
        else:
            for column, value in zip(pk_columns, pk_values):
                setattr(instance, column.key, value)

        for name, value in self._model_kwargs(entity_class, data).items():
            setattr(instance, name, value)

        self.session.add(instance)
        return instance

    def _update_entity(self, instance: Base, data: Dict[str, Any]) -> None:
        """Обновляет существующую сущность."""
        for name, value in self._model_kwargs(instance.__class__, data).items():
            setattr(instance, name, value)

        if hasattr(instance, "row_version"):
            instance.row_version = (instance.row_version or 0) + 1  # type: ignore[attr-defined]

    def _resolve_dependencies(
        self,
        entity_class: type,
        data: Dict[str, Any],
        stack: Set[Tuple[str, str]],
    ) -> None:
        """Создаёт отсутствующие сущности, на которые ссылаются внешние ключи."""
        foreign_keys = self._foreign_key_targets(entity_class)
        for field_name, value in data.items():
            target_class = foreign_keys.get(field_name)
            if target_class is None or value is None:
                continue
            self._ensure_dependency(target_class, self._pk_key(value), stack)

    def _ensure_dependency(
        self,
        target_class: type,
        target_pk_key: str,
        stack: Set[Tuple[str, str]],
    ) -> Base:
        """Возвращает зависимость из БД, создавая её при наличии в JSON."""
        target_pk = self._parse_pk(target_pk_key, target_class)
        existing = self.session.get(target_class, target_pk)
        if existing is not None:
            return existing

        target_name = target_class.__name__
        target_fields = self._payload.get(target_name, {}).get(target_pk_key)
        if target_fields is None or target_fields.get("deleted"):
            raise ValueError(f"Не найдена зависимость {target_name} pk={target_pk_key}")

        if self._apply_entry(target_name, target_pk_key, target_fields, stack) != "imported":
            raise ValueError(f"Не удалось импортировать зависимость {target_name} pk={target_pk_key}")

        instance = self.session.get(target_class, target_pk)
        if instance is None:
            raise ValueError(f"Зависимость {target_name} pk={target_pk_key} не сохранилась")
        return instance

    def _apply_relationships(
        self,
        instance: Base,
        relation_data: Dict[str, Any],
        stack: Set[Tuple[str, str]],
    ) -> None:
        """Применяет состав связей N-N, создавая отсутствующие записи из JSON."""
        if not relation_data:
            return

        specs = self._relationship_specs(instance.__class__)
        for name, values in relation_data.items():
            target_class = specs.get(name)
            if target_class is None:
                continue
            if values is None:
                values = []
            if not isinstance(values, (list, tuple)):
                raise ValueError(f"Ожидался список первичных ключей для связи {name}")

            resolved: List[Base] = []
            for value in values:
                pk_value = value.get("id") if isinstance(value, dict) else value
                resolved.append(
                    self._ensure_dependency(target_class, self._pk_key(pk_value), stack)
                )
            setattr(instance, name, resolved)

    def _relationship_specs(self, entity_class: type) -> Dict[str, type]:
        """Возвращает связи N-N модели: имя атрибута -> класс связанной сущности."""
        return {
            relationship.key: relationship.mapper.class_
            for relationship in entity_class.__mapper__.relationships
            if relationship.secondary is not None
        }

    def _delete_entry(self, entity_name: str, pk_key: str) -> str:
        """Удаляет сущность по экспортной записи об удалении."""
        entity_class = self._resolve_entity_class(entity_name)
        if entity_class is None:
            return "skipped"

        try:
            pk = self._parse_pk(pk_key, entity_class)
        except (TypeError, ValueError):
            logger.warning("Некорректный первичный ключ: %s pk=%s", entity_name, pk_key)
            return "skipped"

        instance = self.session.get(entity_class, pk)
        if instance is None:
            return "skipped"

        try:
            self.session.delete(instance)
            self.session.flush()
            self._discard_changes(entity_name, pk_key)
            self.session.flush()
            return "deleted"
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка удаления сущности %s", entity_name)
            self.conflicts.append({
                "entity_name": entity_name,
                "entity_pk": pk_key,
                "action": "delete",
                "error": str(exc),
            })
            return "skipped"

    def _discard_changes(self, entity_name: str, pk_key: str) -> None:
        """Удаляет служебные записи Change, созданные импортом."""
        changes = (
            self.session.query(Change)
            .filter(Change.entity_name == entity_name, Change.entity_pk == pk_key)
            .all()
        )
        for change in changes:
            self.session.delete(change)

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

    def _model_kwargs(self, entity_class: type, data: Dict[str, Any]) -> Dict[str, Any]:
        """Оставляет атрибуты колонок модели и приводит значения к типам колонок."""
        columns = {column.key: column for column in entity_class.__mapper__.columns}
        pk_keys = {column.key for column in entity_class.__mapper__.primary_key}
        kwargs: Dict[str, Any] = {}
        for name, value in data.items():
            column = columns.get(name)
            if column is None or name in _SERVICE_FIELDS or name in pk_keys:
                continue
            kwargs[name] = self._coerce_value(column, value)
        return kwargs

    def _coerce_value(self, column: Any, value: Any) -> Any:
        """Приводит значение из JSON к типу колонки ORM-модели."""
        if value is None:
            return None
        column_type = column.type
        try:
            if isinstance(column_type, DateTime):
                return datetime.fromisoformat(str(value))
            if isinstance(column_type, Date):
                return date.fromisoformat(str(value).split("T")[0])
            if isinstance(column_type, Boolean):
                if isinstance(value, str):
                    return value.strip().lower() in {"1", "true", "yes", "да"}
                return bool(value)
            if isinstance(column_type, Uuid):
                return uuid.UUID(str(value))
            if isinstance(column_type, Integer):
                return int(value)
            if isinstance(column_type, (Numeric, Float)):
                return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Некорректное значение для поля {column.key}: {value!r}"
            ) from exc
        return value

    def _foreign_key_targets(self, entity_class: type) -> Dict[str, type]:
        """Возвращает соответствие колонок внешних ключей и классов-целей."""
        targets: Dict[str, type] = {}
        models_by_table = self._model_classes()
        for column in entity_class.__mapper__.columns:
            for foreign_key in column.foreign_keys:
                target_class = models_by_table.get(foreign_key.column.table.name)
                if target_class is not None:
                    targets[column.key] = target_class
                    break
        return targets

    def _model_classes(self) -> Dict[str, type]:
        """Возвращает соответствие имён таблиц и ORM-классов."""
        if self._model_classes_cache is None:
            from internal_correspondence.orm import models

            mapping: Dict[str, type] = {}
            for name in dir(models):
                obj = getattr(models, name)
                if isinstance(obj, type) and issubclass(obj, Base) and hasattr(obj, "__tablename__"):
                    mapping[obj.__tablename__] = obj
            self._model_classes_cache = mapping
        return self._model_classes_cache

    def _resolve_entity_class(self, entity_name: str) -> Optional[type]:
        """Возвращает класс ORM-модели по имени сущности."""
        from internal_correspondence.orm import models
        return getattr(models, entity_name, None)

    @staticmethod
    def _pk_key(value: Any) -> str:
        """Приводит значение первичного ключа к строковому виду экспорта."""
        if isinstance(value, (tuple, list)):
            return "_".join(str(item) for item in value)
        return str(value)

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
        """Восстанавливает прикреплённые файлы в файловом хранилище.

        Файл размещается по пути из импортированной записи ``FileRecord``,
        чтобы ссылки на вложения в БД оставались действительными.
        """
        files_dir = extract_dir / "files"
        if not files_dir.exists():
            return
        storage_root = self.storage_root.resolve()
        for file_dir in files_dir.iterdir():
            if not file_dir.is_dir():
                continue

            try:
                file_record = self.session.get(FileRecord, uuid.UUID(file_dir.name))
            except ValueError:
                file_record = None

            for source_file in file_dir.iterdir():
                if not source_file.is_file():
                    continue

                target_dir = None
                target_name = source_file.name
                if file_record is not None:
                    candidate = (storage_root / file_record.path).resolve()
                    if candidate == storage_root or storage_root in candidate.parents:
                        target_dir = candidate
                        target_name = f"{file_record.name}.{file_record.extension}"
                if target_dir is None:
                    target_dir = storage_root / "Файлы" / "Импорт" / file_dir.name

                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target_dir / target_name)
                logger.debug("Восстановлен файл %s", target_dir / target_name)


class ImportError(Exception):
    """Ошибка импорта архива."""

    pass
