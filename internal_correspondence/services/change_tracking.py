"""Сервис отслеживания изменений сущностей (delta-tracking)."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Set


def _utc_now() -> datetime:
    """Возвращает текущее время в UTC в виде "наивного" datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session, attributes

from internal_correspondence.core.constants import DELETION_MARKER
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import Change

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
_SERVICE_FIELDS = {"change_id", "row_version", "created_at", "updated_at"}

# Глард предотвращает множественную регистрацию слушателей в тестах
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


def _get_changed_fields(instance: Base) -> Set[str]:
    """Возвращает множество имён изменённых колонок объекта."""
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
    return changed


def _mark_change(
    session: Session,
    instance: Base,
    changed_fields: Iterable[str],
) -> None:
    """Создаёт или обновляет запись Change для объекта."""
    table_name = instance.__tablename__
    if table_name not in _TRACKED_TABLES:
        return

    entity_name = instance.__class__.__name__
    entity_pk = _entity_primary_key(instance)
    if not entity_pk:
        return

    fields_set: Set[str] = set(changed_fields) - _SERVICE_FIELDS
    if not fields_set:
        return

    existing_change_id = getattr(instance, "change_id", None)

    if existing_change_id:
        change = session.get(Change, existing_change_id)
        if change:
            existing_fields = set(change.changed_fields or [])
            if DELETION_MARKER in existing_fields:
                existing_fields.discard(DELETION_MARKER)
            existing_fields.update(fields_set)
            change.changed_fields = sorted(existing_fields)
            change.changed_at = _utc_now()
            logger.debug("Обновлена запись Change для %s pk=%s", entity_name, entity_pk)
            return

    change = Change(
        entity_name=entity_name,
        entity_pk=entity_pk,
        changed_at=_utc_now(),
        changed_fields=sorted(fields_set),
    )
    session.add(change)
    # Не вызываем session.flush() внутри before_flush — объект Change
    # будет сохранён в рамках текущего flush, после чего SQLAlchemy
    # присвоит значение change.id автоматически.
    instance.change = change
    logger.debug("Создана запись Change для %s pk=%s", entity_name, entity_pk)


def _mark_deletion(session: Session, instance: Base) -> None:
    """Помечает удаление объекта специальным маркером в Change."""
    if instance.__tablename__ not in _TRACKED_TABLES:
        return

    entity_name = instance.__class__.__name__
    entity_pk = _entity_primary_key(instance)
    if not entity_pk:
        return

    existing_change_id = getattr(instance, "change_id", None)
    if existing_change_id:
        change = session.get(Change, existing_change_id)
        if change:
            change.changed_fields = [DELETION_MARKER]
            change.changed_at = _utc_now()
            logger.debug("Отмечено удаление Change для %s pk=%s", entity_name, entity_pk)
            return

    change = Change(
        entity_name=entity_name,
        entity_pk=entity_pk,
        changed_at=_utc_now(),
        changed_fields=[DELETION_MARKER],
    )
    session.add(change)
    # Удаляемый объект уже не может ссылаться на Change через ORM-атрибут,
    # но это не требуется — запись Change будет экспортирована и удалена
    # на приёмной стороне.
    logger.debug("Создана запись Change об удалении для %s pk=%s", entity_name, entity_pk)


def _on_before_flush(session: Session, _flush_context, _instances) -> None:
    """Обработчик события before_flush для создания/обновления Change."""
    for instance in session.new:
        if isinstance(instance, Base) and instance.__tablename__ in _TRACKED_TABLES:
            _ensure_primary_key(instance)
            columns = set(instance.__mapper__.columns.keys()) - _SERVICE_FIELDS
            _mark_change(session, instance, columns)

    for instance in session.dirty:
        if isinstance(instance, Base) and instance.__tablename__ in _TRACKED_TABLES:
            changed = _get_changed_fields(instance)
            if changed:
                _mark_change(session, instance, changed)

    for instance in session.deleted:
        if isinstance(instance, Base) and instance.__tablename__ in _TRACKED_TABLES:
            _mark_deletion(session, instance)


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
