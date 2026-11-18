"""Экспорт изменений в ZIP-архив."""

import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import (
    DEFAULT_CHANGES_RETENTION_DAYS,
    ChangeOperation,
    Role,
)
from internal_correspondence.core.domain_pack import dir_name, get_domain_pack
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.importexport.branch_scope import (
    branches_for_change,
    pending_branch_ids,
)
from internal_correspondence.orm.models import Branch, Change, FileRecord, MissingRequest
from internal_correspondence.orm.utils import parse_primary_key, resolve_entity_class
from internal_correspondence.services.change_tracking import purge_expired_changes

logger = get_logger("export_service")

# Тип обратного вызова прогресса: (готовых шагов, всего шагов, пояснение)
ProgressCallback = Optional[Callable[[int, int, str], None]]

# Символы, недопустимые в именах файлов Windows
_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def _export_timestamp() -> str:
    """Возвращает метку времени архива (UTC) в формате ГГГГ-ММ-ДД_чч_мм."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H_%M")


def _safe_filename_part(value: str) -> str:
    """Удаляет из части имени файла символы, недопустимые в Windows."""
    return _UNSAFE_FILENAME_CHARS.sub("_", value).strip() or "—"


def archive_filename(timestamp: str, direction: str, branch_short_name: str) -> str:
    """Возвращает имя экспортного архива: «<время> для/от <филиал>.zip»."""
    return f"{timestamp} {direction} {_safe_filename_part(branch_short_name)}.zip"


class ExportService:
    """Формирует экспортные ZIP-архивы с изменёнными сущностями и файлами.

    Режимы:
    - филиал — один архив со всеми неэкспортированными изменениями
      (``export_branch``), имя «<время> от <сокращение филиала>.zip»;
    - головной офис — отдельный архив на каждый выбранный филиал
      (``export_for_branches``): изменения записей филиала плюс полный
      набор изменений справочников, имя «<время> для <сокращение>.zip».

    Метка ``exported_at`` проставляется только после успешной записи всех
    архивов пакета: при ошибке частичные файлы удаляются, а изменения
    остаются неэкспортированными.
    """

    def __init__(
        self,
        session: Session,
        storage_root: Path,
        retention_days: int = DEFAULT_CHANGES_RETENTION_DAYS,
        role: str = Role.HEAD_OFFICE.value,
        branch_id: Optional[str] = None,
        progress_cb: ProgressCallback = None,
    ) -> None:
        self.session = session
        self.storage_root = storage_root
        self.retention_days = retention_days
        self.role = role
        self.branch_id = branch_id
        self.progress_cb = progress_cb
        self.export_dir = storage_root / dir_name("export")
        self.export_dir.mkdir(parents=True, exist_ok=True)

    # --- публичный интерфейс ---

    def pending_branches(self) -> List[Branch]:
        """Возвращает филиалы с неэкспортированными изменениями (для диалога ГО)."""
        ids = pending_branch_ids(self.session)
        if not ids:
            return []
        return (
            self.session.query(Branch).filter(Branch.id.in_(ids)).order_by(Branch.id).all()
        )

    def export(self, output_path: Optional[Path] = None) -> Path:
        """Формирует единый экспортный архив со всеми изменениями.

        Сохранён для совместимости и простых сценариев; ролевой экспорт
        выполняется через ``export_branch``/``export_for_branches``.
        """
        changes = self._unexported_changes()
        if not changes:
            raise ExportError("Нет изменений для экспорта")

        export_data = self._build_export_data(changes)
        if not export_data:
            raise ExportError("Нет данных для экспорта")

        file_records = self._collect_files(export_data)
        if output_path is None:
            output_path = self.export_dir / f"{_export_timestamp()}.zip"

        self._pack_archive(output_path, export_data, file_records, changes)
        self._mark_exported(changes)
        purge_expired_changes(self.session, self.retention_days)
        logger.info("Экспорт завершён: %s", output_path)
        return output_path

    def export_branch(self, output_path: Optional[Path] = None) -> Path:
        """Формирует архив филиала «<время> от <сокращение>.zip» со всеми изменениями."""
        changes = self._unexported_changes()
        if not changes:
            raise ExportError("Нет изменений для экспорта")
        export_data = self._build_export_data(changes)
        if not export_data:
            raise ExportError("Нет данных для экспорта")
        file_records = self._collect_files(export_data)

        if output_path is None:
            branch = self.session.get(Branch, self.branch_id) if self.branch_id else None
            short = branch.short_name if branch is not None else "филиал"
            output_path = self.export_dir / archive_filename(
                _export_timestamp(), "от", short
            )

        self._write_archives([(output_path, export_data, file_records, changes)])
        return output_path

    def export_for_branches(self, branch_ids: Sequence[str]) -> List[Path]:
        """Формирует по архиву для каждого выбранного филиала.

        В каждый архив входят изменения записей этого филиала (документы,
        ОШС, оценки, адресация, файлы — см. ``branch_scope``) и полный набор
        изменений справочников. Изменения помечаются экспортированными
        только после успешной записи всех архивов.
        """
        if self.role != Role.HEAD_OFFICE.value:
            raise ExportError("Экспорт по филиалам доступен только в головном офисе")
        if not branch_ids:
            raise ExportError("Не выбраны филиалы для экспорта")

        changes = self._unexported_changes()
        if not changes:
            raise ExportError("Нет изменений для экспорта")

        buckets: Dict[str, List[Change]] = {branch_id: [] for branch_id in branch_ids}
        reference_changes: List[Change] = []
        for change in changes:
            resolved = branches_for_change(self.session, change)
            if resolved is None:
                reference_changes.append(change)
                continue
            for branch_id in resolved:
                if branch_id in buckets:
                    buckets[branch_id].append(change)

        branches = {
            branch.id: branch
            for branch in self.session.query(Branch)
            .filter(Branch.id.in_(list(buckets)))
            .all()
        }
        timestamp = _export_timestamp()

        plans: List[Tuple[Path, Dict[str, Dict[str, Dict[str, Any]]], List[FileRecord], List[Change]]] = []
        for branch_id, bucket in buckets.items():
            branch_changes = bucket + reference_changes
            export_data = self._build_export_data(branch_changes)
            if not export_data:
                continue
            file_records = self._collect_files(export_data)
            branch = branches.get(branch_id)
            short = branch.short_name if branch is not None else branch_id
            output_path = self.export_dir / archive_filename(timestamp, "для", short)
            plans.append((output_path, export_data, file_records, branch_changes))

        if not plans:
            raise ExportError("Нет данных для экспорта")

        self._write_archives(plans)
        return [plan[0] for plan in plans]

    # --- внутренние этапы ---

    def _unexported_changes(self) -> List[Change]:
        """Возвращает неэкспортированные изменения в порядке следования."""
        return (
            self.session.query(Change).filter(Change.exported_at.is_(None)).all()
        )

    def _progress(self, current: int, total: int, message: str) -> None:
        """Сообщает о ходе экспорта (если задан обработчик прогресса)."""
        if self.progress_cb is not None:
            self.progress_cb(current, total, message)

    def _write_archives(self, plans) -> None:
        """Пишет архивы пакета; при ошибке удаляет частичные файлы."""
        written: List[Path] = []
        try:
            for output_path, export_data, file_records, changes in plans:
                self._pack_archive(output_path, export_data, file_records, changes)
                written.append(output_path)
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            logger.exception("Ошибка записи экспортных архивов; частичные файлы удалены")
            raise
        total_changes = [change for plan in plans for change in plan[3]]
        # Помечаем экспортированными только уникальные записи Change
        # (справочные изменения входят в несколько архивов).
        unique_changes: Dict[int, Change] = {change.id: change for change in total_changes}
        self._mark_exported(list(unique_changes.values()))
        self._consume_missing_requests()
        purge_expired_changes(self.session, self.retention_days)
        self.session.flush()
        for output_path in written:
            logger.info("Экспорт завершён: %s", output_path)

    def _build_export_data(self, changes: List[Change]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Формирует словарь экспорта: сущность -> первичный ключ -> изменённые поля."""
        export_data: Dict[str, Dict[str, Dict[str, Any]]] = {}
        deleted_keys: Set[Tuple[str, str]] = set()
        total = max(len(changes), 1)
        done = 0

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
            done += 1
            self._progress(done, total, change.entity_name)

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

    def _summary(self, changes: List[Change]) -> Dict[str, Dict[str, int]]:
        """Сводка изменений для meta.json: имя таблицы -> добавлено/изменено/удалено."""
        summary: Dict[str, Dict[str, int]] = {}
        for change in changes:
            entity_class = resolve_entity_class(change.entity_name)
            table = entity_class.__tablename__ if entity_class is not None else change.entity_name
            bucket = summary.setdefault(
                table, {"added": 0, "updated": 0, "deleted": 0}
            )
            if change.operation_type == ChangeOperation.CREATE.value:
                bucket["added"] += 1
            elif change.operation_type == ChangeOperation.DELETE.value:
                bucket["deleted"] += 1
            else:
                bucket["updated"] += 1
        return summary

    def _missing_payload(self) -> List[Dict[str, Any]]:
        """Возвращает накопленные запросы контрагенту для missing.json."""
        requests = (
            self.session.query(MissingRequest).order_by(MissingRequest.id).all()
        )
        return [
            {
                "entity_name": request.entity_name,
                "entity_pk": request.entity_pk,
                "branch_id": request.branch_id,
                "created_at": request.created_at.isoformat() if request.created_at else None,
            }
            for request in requests
        ]

    def _consume_missing_requests(self) -> None:
        """Очищает таблицу запросов после включения их в экспорт."""
        consumed = self.session.query(MissingRequest).delete()
        if consumed:
            logger.info("В экспорт включено запросов контрагенту: %s", consumed)

    def _pack_archive(
        self,
        output_path: Path,
        export_data: Dict[str, Any],
        file_records: List[FileRecord],
        changes: List[Change],
    ) -> None:
        """Упаковывает JSON и файлы в ZIP-архив."""
        pack = get_domain_pack()
        meta = {
            "app": "internal-correspondence",
            "pack_id": pack.id,
            "pack_version": pack.version,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "summary": self._summary(changes),
        }
        missing = self._missing_payload()
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
            zf.writestr("export.json", json.dumps(export_data, ensure_ascii=False, indent=2))
            if missing:
                zf.writestr(
                    "missing.json", json.dumps(missing, ensure_ascii=False, indent=2)
                )
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
