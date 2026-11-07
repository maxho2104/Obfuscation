"""Общие утилиты для работы с ORM-моделями."""

import uuid
from typing import Any, Optional

from internal_correspondence.orm.base import Base


def resolve_entity_class(entity_name: str) -> Optional[type]:
    """Возвращает класс ORM-модели по имени сущности."""
    from internal_correspondence.orm import models

    return getattr(models, entity_name, None)


def parse_primary_key(pk_str: str, entity_class: type) -> Any:
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
    # Составной ключ (в проекте не используется)
    return pk_str.split("_")
