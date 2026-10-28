"""Базовый класс ORM и общие миксины."""

import uuid
from datetime import datetime, timezone, date, time
from typing import Any, Dict

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase
from decimal import Decimal


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""

    def to_dict(self, fields: list[str] | None = None) -> Dict[str, Any]:
        """Сериализует объект в словарь.

        Args:
            fields: Список имён полей для сериализации. Если None — сериализуются
                все обычные атрибуты.
        """
        result: Dict[str, Any] = {}
        target_fields = fields if fields is not None else self.__mapper__.columns.keys()
        for field_name in target_fields:
            value = getattr(self, field_name, None)
            if isinstance(value, (datetime, date, time)):
                value = value.isoformat()
            elif isinstance(value, uuid.UUID):
                value = str(value)
            elif isinstance(value, Decimal):
                value = float(value)
            result[field_name] = value
        return result


class VersionedMixin:
    """Миксин оптимистичного контроля версий."""

    row_version = Column(Integer, nullable=False, default=1)


class TimestampMixin:
    """Миксин временных меток создания и обновления."""

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )
