"""Базовый класс ORM и общие типы."""

import uuid
from datetime import datetime, date, time
from decimal import Decimal
from enum import IntEnum
from typing import Any, Dict, Optional, Type

from sqlalchemy import SmallInteger
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


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


class IntEnumType(TypeDecorator):
    """Сохраняет IntEnum в БД как целое число.

    Python-сторона модели типизирована перечислением, в колонке
    хранится числовое значение (SmallInteger).
    """

    impl = SmallInteger
    cache_ok = True

    def __init__(self, enum_class: Type[IntEnum]) -> None:
        super().__init__()
        self._enum_class = enum_class

    def process_bind_param(
        self, value: Optional[IntEnum], dialect: Any
    ) -> Optional[int]:
        if value is None:
            return None
        return int(value)

    def process_result_value(
        self, value: Optional[int], dialect: Any
    ) -> Optional[IntEnum]:
        if value is None:
            return None
        try:
            return self._enum_class(value)
        except ValueError:
            # Неизвестное значение (чужой пакет): отдаём число как есть,
            # предупреждение оператору формирует validate_enum_codes
            return value  # type: ignore[return-value]
