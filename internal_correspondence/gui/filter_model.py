"""Модель фильтрации записей таблиц."""

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional, Set, Tuple

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric
from sqlalchemy import inspect as sa_inspect

from internal_correspondence.core.enum_registry import (
    pack_enum_choices,
    pack_enum_display,
    pack_key_for_enum_class,
)
from internal_correspondence.orm.base import IntEnumType
from internal_correspondence.utils.string_resources import STRINGS

TEXT_OPERATORS: List[Tuple[str, str]] = [
    ("contains", "содержит"),
    ("startswith", "начинается с"),
    ("endswith", "заканчивается на"),
]

COMPARISON_OPERATORS: List[Tuple[str, str]] = [
    ("eq", "="),
    ("ne", "≠"),
    ("gt", ">"),
    ("ge", "≥"),
    ("lt", "<"),
    ("le", "≤"),
]

BOOL_OPERATORS: List[Tuple[str, str]] = [
    ("eq", "="),
    ("ne", "≠"),
]

# Унарные проверки пустоты — только для nullable колонок
NULL_OPERATORS: List[Tuple[str, str]] = [
    ("empty", STRINGS.filter_op_empty),
    ("not_empty", STRINGS.filter_op_not_empty),
]

# Мультивыбор значений пакетного перечисления
ENUM_OPERATORS: List[Tuple[str, str]] = [("in", STRINGS.filter_op_in)]

OPERATOR_LABELS = dict(
    TEXT_OPERATORS + COMPARISON_OPERATORS + BOOL_OPERATORS + NULL_OPERATORS + ENUM_OPERATORS
)


def operators_for(value_type: str, nullable: bool = False) -> List[Tuple[str, str]]:
    """Возвращает список допустимых условий для типа значения.

    Для nullable колонок дополнительно доступны проверки на пустоту.
    """
    if value_type == "text":
        operators = list(TEXT_OPERATORS)
    elif value_type == "bool":
        operators = list(BOOL_OPERATORS)
    elif value_type == "enum":
        operators = list(ENUM_OPERATORS)
    else:
        operators = list(COMPARISON_OPERATORS)
    if nullable:
        operators += NULL_OPERATORS
    return operators


def _resolve_column(model_class: type, column_name: str):
    """Возвращает колонку ORM-модели по имени (включая вложенные связи)."""
    mapper = sa_inspect(model_class)
    parts = column_name.split(".")
    for part in parts[:-1]:
        attribute = mapper.attrs.get(part)
        target_mapper = getattr(attribute, "mapper", None)
        if target_mapper is None:
            return None
        mapper = target_mapper
    try:
        return mapper.columns[parts[-1]]
    except KeyError:
        return None


def resolve_value_type(model_class: type, column_name: str) -> str:
    """Определяет тип значения колонки ORM-модели, включая вложенные связи."""
    column = _resolve_column(model_class, column_name)
    if column is None:
        return "text"
    column_type = column.type
    if isinstance(column_type, IntEnumType):
        return "enum"
    if isinstance(column_type, Boolean):
        return "bool"
    if isinstance(column_type, DateTime):
        return "datetime"
    if isinstance(column_type, Date):
        return "date"
    if isinstance(column_type, Integer):
        return "integer"
    if isinstance(column_type, (Numeric, Float)):
        return "number"
    return "text"


def resolve_nullable(model_class: type, column_name: str) -> bool:
    """Проверяет, допускает ли колонка пустое значение (nullable)."""
    column = _resolve_column(model_class, column_name)
    return bool(column is not None and column.nullable)


def resolve_pack_enum(model_class: type, column_name: str) -> Optional[str]:
    """Возвращает ключ пакетного перечисления для колонки-IntEnum; иначе None."""
    column = _resolve_column(model_class, column_name)
    if column is None or not isinstance(column.type, IntEnumType):
        return None
    return pack_key_for_enum_class(column.type._enum_class.__name__)


def format_filter_value(
    value: str, value_type: str, pack_enum: Optional[str] = None
) -> str:
    """Форматирует значение фильтра для отображения пользователю."""
    if value_type == "enum" and pack_enum:
        choices = dict(pack_enum_choices(pack_enum))
        parts = []
        for raw in value.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                code = int(raw)
            except ValueError:
                parts.append(raw)
                continue
            parts.append(choices.get(code) or pack_enum_display(pack_enum, code))
        return ", ".join(parts)
    if value_type == "bool":
        return "Да" if value.lower() in ("true", "1", "да") else "Нет"
    if value_type == "date":
        try:
            return date.fromisoformat(value).strftime("%d.%m.%Y")
        except ValueError:
            return value
    if value_type == "datetime":
        try:
            return datetime.fromisoformat(value).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            return value
    return value


def _parse_value(value: str, value_type: str) -> Any:
    """Преобразует строковое значение фильтра в сравнимое значение."""
    if value_type == "date":
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    if value_type == "datetime":
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    if value_type in ("number", "integer"):
        try:
            return Decimal(value.replace(",", "."))
        except (InvalidOperation, AttributeError):
            return None
    if value_type == "bool":
        return value.lower() in ("true", "1", "да")
    return value


def _compare(actual: Any, expected: Any, operator: str) -> bool:
    """Сравнивает значения согласно условию."""
    if operator == "eq":
        return actual == expected
    if operator == "ne":
        return actual != expected
    if operator == "gt":
        return actual > expected
    if operator == "ge":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "le":
        return actual <= expected
    return False


def _parse_code_set(value: str) -> Set[int]:
    """Разбирает список целочисленных кодов перечисления из строки условия."""
    codes: Set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            codes.add(int(part))
        except ValueError:
            continue
    return codes


@dataclass(frozen=True)
class FilterCondition:
    """Условие фильтрации по одной колонке."""

    column_name: str
    operator: str
    value: str

    def describe(
        self, header: str, value_type: str, pack_enum: Optional[str] = None
    ) -> str:
        """Возвращает читаемое описание условия."""
        label = OPERATOR_LABELS.get(self.operator, self.operator)
        if self.operator in ("empty", "not_empty"):
            return f"{header} {label}"
        formatted = format_filter_value(self.value, value_type, pack_enum)
        if value_type in ("text", "enum"):
            return f"{header} {label} «{formatted}»"
        return f"{header} {label} {formatted}"

    def matches(self, actual: Any, value_type: str) -> bool:
        """Проверяет, удовлетворяет ли значение условию."""
        if self.operator in ("empty", "not_empty"):
            is_empty = actual is None or actual == ""
            return is_empty if self.operator == "empty" else not is_empty

        if value_type == "enum":
            if self.operator != "in":
                return True
            if actual is None:
                return False
            try:
                return int(actual) in _parse_code_set(self.value)
            except (TypeError, ValueError):
                return False

        if value_type == "text":
            text = "" if actual is None else str(actual).lower()
            needle = self.value.lower()
            if self.operator == "contains":
                return needle in text
            if self.operator == "startswith":
                return text.startswith(needle)
            if self.operator == "endswith":
                return text.endswith(needle)
            return False

        if value_type in ("date", "datetime"):
            expected = _parse_value(self.value, value_type)
            if expected is None or actual is None:
                return False
            if value_type == "date":
                if isinstance(actual, datetime):
                    actual = actual.date()
                if not isinstance(actual, date):
                    return False
            elif not isinstance(actual, datetime):
                return False
            return _compare(actual, expected, self.operator)

        if value_type in ("number", "integer"):
            expected = _parse_value(self.value, value_type)
            if expected is None or actual is None:
                return False
            try:
                actual_number = Decimal(actual)
            except (InvalidOperation, TypeError, ValueError):
                return False
            return _compare(actual_number, expected, self.operator)

        if value_type == "bool":
            expected = _parse_value(self.value, value_type)
            return _compare(bool(actual), expected, self.operator)

        return True

    def to_dict(self) -> dict:
        """Сериализует условие для сохранения в настройках."""
        return {
            "column": self.column_name,
            "operator": self.operator,
            "value": self.value,
        }

    @staticmethod
    def from_dict(raw: dict, model_class: type) -> Optional["FilterCondition"]:
        """Восстанавливает условие из словаря; None — условие недопустимо.

        Проверяет существование колонки и оператора для её типа —
        сохранённое в INI значение может отставать от схемы.
        """
        if not isinstance(raw, dict):
            return None
        column_name = raw.get("column")
        operator = raw.get("operator")
        value = raw.get("value")
        if not isinstance(column_name, str) or not isinstance(operator, str):
            return None
        if not isinstance(value, (str, int, float)):
            return None
        value_type = resolve_value_type(model_class, column_name)
        valid_operators = {
            item
            for item, _label in operators_for(
                value_type, resolve_nullable(model_class, column_name)
            )
        }
        if operator not in valid_operators:
            return None
        return FilterCondition(column_name, operator, str(value))


def serialize_filters(filters: List[FilterCondition]) -> str:
    """Сериализует список условий в JSON-строку для settings.ini."""
    return json.dumps([condition.to_dict() for condition in filters], ensure_ascii=False)


def deserialize_filters(
    raw: str, model_class: type
) -> List[FilterCondition]:
    """Восстанавливает список условий из JSON-строки; мусор отбрасывается."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        condition = FilterCondition.from_dict(item, model_class)
        if condition is not None:
            result.append(condition)
    return result
