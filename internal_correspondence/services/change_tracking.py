"""Сервис отслеживания изменений сущностей (delta-tracking)."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import delete, event, inspect
from sqlalchemy.orm import Session, attributes

from internal_correspondence.core.constants import ChangeOperation
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import Change


def _utc_now() -> datetime:
    """Возвращает текущее время в UTC в виде "наивного" datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


logger = get_logger("change_tracking")

# Множество имён таблиц, за которыми ведётся учёт изменений
_TRACKED_TABLES = {
    "territorial_units",
    "branches",
    "departments",
    "working_groups",
    "academic_titles",
    "employees",
    "scientific_tasks",
    "countries",
    "consumers",
    "sources",
    "leaders",
    "file_records",
    "scientific_materials",
    "telegrams",
    "report_addresses",
    "evaluations",
    "evaluation_lists",
}

# Служебные поля, которые не попадают в changed_fields
_SERVICE_FIELDS = {"change_id"}

# Гард предотвращает множественную регистрацию слушателей в тестах
_CHANGE_TRACKING_REGISTERED = False


def _entity_primary_key(instance: Base) -> str:
    """Возвращает строковое представление первичного ключа объекта."""
    pk = instance.__mapper__.primary_key_from_instance(instance)
    if pk is None or any(value is None for value in pk):
        return ""
    values = [str(value) for value in pk]
    return "_".join(values)


def _ensure_primary_key(instance: Base) -> None:
    """Назначает значения первичного ключа по умолчанию до вставки строки."""
    for column in instance.__mapper__.primary_key:
        if getattr(instance, column.key, None) is not None:
            continue
        default = column.default
        if default is None or not default.is_callable:
            continue
        setattr(instance, column.key, default.arg(None))


def _canonical_relationships(mapper) -> List[Any]:
    """Возвращает связи N-N, которыми владеет данная сущность.

    Владельцем считается сторона, чей первичный ключ объявлен первым
    в ассоциативной таблице. Это исключает двойное отслеживание одной
    и той же связи с обеих сторон.
    """
    result: List[Any] = []
    for relationship in mapper.relationships:
        if relationship.secondary is None:
            continue
        secondary_columns = list(relationship.secondary.columns)
        if not secondary_columns:
            continue
        for foreign_key in secondary_columns[0].foreign_keys:
            if foreign_key.column.table is mapper.local_table:
                result.append(relationship)
                break
    return result


def _get_changed_fields(instance: Base) -> Set[str]:
    """Возвращает множество имён изменённых колонок и связей N-N объекта."""
    changed: Set[str] = set()
    state = inspect(instance)
    if not state:
        return changed
    column_keys = set(instance.__mapper__.columns.keys())
    for attr_name in state.attrs.keys():
        if attr_name not in column_keys or attr_name in _SERVICE_FIELDS:
            continue
        hist = state.get_history(attr_name, attributes.PASSIVE_OFF)
        if hist.has_changes():
            changed.add(attr_name)

    for relationship in _canonical_relationships(instance.__mapper__):
        if relationship.key in _SERVICE_FIELDS:
            continue
        hist = state.get_history(relationship.key, attributes.PASSIVE_NO_INITIALIZE)
        if hist.has_changes():
            changed.add(relationship.key)
    return changed


def _find_change(session: Session, entity_name: str, entity_pk: str) -> Optional[Change]:
    """Возвращает запись Change для пары (имя сущности, первичный ключ)."""
    return (
        session.query(Change)
        .filter(Change.entity_name == entity_name, Change.entity_pk == entity_pk)
        .one_or_none()
    )


def _linked_change(session: Session, instance: Base) -> Optional[Change]:
    """Возвращает запись Change, относящуюся к объекту.

    Сначала ищет по change_id объекта, затем — по паре (имя сущности,
    первичный ключ): ссылка могла быть сброшена после экспорта.
    """
    change_id = getattr(instance, "change_id", None)
    if change_id:
        change = session.get(Change, change_id)
        if change is not None:
            return change
    return _find_change(
        session, instance.__class__.__name__, _entity_primary_key(instance)
    )


def _mark_created(session: Session, instance: Base) -> None:
    """Создаёт или перезаписывает запись Change для нового объекта.

    Если запись Change с такой парой (сущность, ключ) уже существует
    (сущность удалялась ранее), она перезаписывается как создание:
    идентификатор сохраняется, история записей не плодится.
    """
    entity_name = instance.__class__.__name__
    entity_pk = _entity_primary_key(instance)
    if not entity_pk:
        return

    columns = {
        name
        for name in set(instance.__mapper__.columns.keys()) - _SERVICE_FIELDS
        if getattr(instance, name, None) is not None
    }
    relationships = {
        relationship.key
        for relationship in _canonical_relationships(instance.__mapper__)
        if getattr(instance, relationship.key, None)
    }
    fields_set = (columns | relationships) - _SERVICE_FIELDS
    if not fields_set:
        return

    change = _find_change(session, entity_name, entity_pk)
    if change is not None:
        change.operation_type = ChangeOperation.CREATE.value
        change.changed_fields = sorted(fields_set)
        change.changed_at = _utc_now()
        change.exported_at = None
        instance.change = change
        logger.debug("Перезаписана запись Change для %s pk=%s", entity_name, entity_pk)
        return

    change = Change(
        entity_name=entity_name,
        entity_pk=entity_pk,
        changed_at=_utc_now(),
        changed_fields=sorted(fields_set),
        operation_type=ChangeOperation.CREATE.value,
    )
    session.add(change)
    # Не вызываем session.flush() внутри before_flush — объект Change
    # будет сохранён в рамках текущего flush, после чего SQLAlchemy
    # присвоит значение change.id автоматически.
    instance.change = change
    logger.debug("Создана запись Change для %s pk=%s", entity_name, entity_pk)


def _mark_updated(session: Session, instance: Base, changed_fields: Iterable[str]) -> None:
    """Обновляет запись Change для изменённого объекта.

    Если запись ещё не экспортировалась (exported_at пустое), множество
    полей объединяется с прежними. Иначе операция фиксируется как
    изменение и в changed_fields попадают только поля, изменённые
    после последнего экспорта.
    """
    entity_name = instance.__class__.__name__
    entity_pk = _entity_primary_key(instance)
    if not entity_pk:
        return

    fields_set = set(changed_fields) - _SERVICE_FIELDS
    if not fields_set:
        return

    change = _linked_change(session, instance)
    if change is None:
        change = Change(
            entity_name=entity_name,
            entity_pk=entity_pk,
            changed_at=_utc_now(),
            changed_fields=sorted(fields_set),
            operation_type=ChangeOperation.UPDATE.value,
        )
        session.add(change)
        instance.change = change
        logger.debug("Создана запись Change для %s pk=%s", entity_name, entity_pk)
        return

    if change.exported_at is None:
        existing_fields = set(change.changed_fields or [])
        existing_fields.update(fields_set)
        change.changed_fields = sorted(existing_fields)
    else:
        change.operation_type = ChangeOperation.UPDATE.value
        change.changed_fields = sorted(fields_set)
        change.exported_at = None
    change.changed_at = _utc_now()
    if getattr(instance, "change_id", None) is None:
        instance.change = change
    logger.debug("Обновлена запись Change для %s pk=%s", entity_name, entity_pk)


def _mark_deleted(session: Session, instance: Base) -> None:
    """Помечает удаление объекта в записи Change.

    Если объект создавался и не экспортировался, запись Change просто
    удаляется — след объекта не уходит за пределы локальной БД.
    Иначе операция фиксируется как удаление с пустым множеством полей.
    """
    entity_name = instance.__class__.__name__
    entity_pk = _entity_primary_key(instance)
    if not entity_pk:
        return

    change = _linked_change(session, instance)
    if change is None:
        change = Change(
            entity_name=entity_name,
            entity_pk=entity_pk,
            changed_at=_utc_now(),
            changed_fields=[],
            operation_type=ChangeOperation.DELETE.value,
        )
        session.add(change)
        logger.debug("Создана запись Change об удалении для %s pk=%s", entity_name, entity_pk)
        return

    if (
        change.operation_type == ChangeOperation.CREATE.value
        and change.exported_at is None
    ):
        session.delete(change)
        logger.debug("Удалена запись Change для %s pk=%s", entity_name, entity_pk)
        return

    change.operation_type = ChangeOperation.DELETE.value
    change.changed_fields = []
    change.changed_at = _utc_now()
    change.exported_at = None
    logger.debug("Отмечено удаление Change для %s pk=%s", entity_name, entity_pk)


def _on_before_flush(session: Session, _flush_context, _instances) -> None:
    """Обработчик события before_flush для создания/обновления Change."""
    for instance in session.new:
        if isinstance(instance, Base) and instance.__tablename__ in _TRACKED_TABLES:
            _ensure_primary_key(instance)
            _mark_created(session, instance)

    for instance in session.dirty:
        if isinstance(instance, Base) and instance.__tablename__ in _TRACKED_TABLES:
            changed = _get_changed_fields(instance)
            if changed:
                _mark_updated(session, instance, changed)

    for instance in session.deleted:
        if isinstance(instance, Base) and instance.__tablename__ in _TRACKED_TABLES:
            _mark_deleted(session, instance)


def purge_expired_changes(session: Session, retention_days: int) -> int:
    """Удаляет экспортированные записи Change старше срока хранения.

    Неэкспортированные записи (exported_at IS NULL) не затрагиваются.
    Срок <= 0 означает бессрочное хранение. Возвращает число удалённых записей.
    """
    if retention_days <= 0:
        return 0
    threshold = _utc_now() - timedelta(days=retention_days)
    result = session.execute(
        delete(Change).where(
            Change.exported_at.isnot(None),
            Change.exported_at < threshold,
        )
    )
    deleted_count = result.rowcount or 0
    if deleted_count:
        logger.info("Удалено устаревших записей Change: %s", deleted_count)
    return deleted_count


def register_change_tracking() -> None:
    """Регистрирует слушателя SQLAlchemy для отслеживания изменений.

    Идемпотентна: повторные вызовы не добавляют дублирующих слушателей.
    """
    global _CHANGE_TRACKING_REGISTERED
    if _CHANGE_TRACKING_REGISTERED:
        return
    event.listen(Session, "before_flush", _on_before_flush)
    _CHANGE_TRACKING_REGISTERED = True
    logger.info("Change-tracking зарегистрирован")


def serialize_change(change: Change) -> Dict[str, Any]:
    """Сериализует запись Change в словарь."""
    return {
        "id": str(change.id),
        "entity_name": change.entity_name,
        "entity_pk": change.entity_pk,
        "changed_at": change.changed_at.isoformat() if change.changed_at else None,
        "changed_fields": change.changed_fields or [],
        "operation_type": change.operation_type,
        "exported_at": change.exported_at.isoformat() if change.exported_at else None,
    }


def clear_change(session: Session, instance: Base) -> None:
    """Сбрасывает change_id у объекта и удаляет связанную запись Change."""
    change_id = getattr(instance, "change_id", None)
    if not change_id:
        return
    change = session.get(Change, change_id)
    if change:
        session.delete(change)
    instance.change_id = None  # type: ignore[attr-defined]
