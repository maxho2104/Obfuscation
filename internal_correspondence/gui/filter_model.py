"""Модель фильтрации записей таблиц."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, List, Tuple

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric
from sqlalchemy import inspect as sa_inspect

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

OPERATOR_LABELS = dict(TEXT_OPERATORS + COMPARISON_OPERATORS + BOOL_OPERATORS)


def operators_for(value_type: str) -> List[Tuple[str, str]]:
    """Возвращает список допустимых условий для типа значения."""
    if value_type == "text":
        return list(TEXT_OPERATORS)
    if value_type == "bool":
        return list(BOOL_OPERATORS)
    return list(COMPARISON_OPERATORS)


def resolve_value_type(model_class: type, column_name: str) -> str:
    """Определяет тип значения колонки ORM-модели, включая вложенные связи."""
    mapper = sa_inspect(model_class)
    parts = column_name.split(".")
    for part in parts[:-1]:
        attribute = mapper.attrs.get(part)
        target_mapper = getattr(attribute, "mapper", None)
        if target_mapper is None:
            return "text"
        mapper = target_mapper

    try:
        column = mapper.columns[parts[-1]]
    except KeyError:
        return "text"

    column_type = column.type
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


def format_filter_value(value: str, value_type: str) -> str:
    """Форматирует значение фильтра для отображения пользователю."""
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


@dataclass(frozen=True)
class FilterCondition:
    """Условие фильтрации по одной колонке."""

    column_name: str
    operator: str
    value: str

    def describe(self, header: str, value_type: str) -> str:
        """Возвращает читаемое описание условия."""
        label = OPERATOR_LABELS.get(self.operator, self.operator)
        formatted = format_filter_value(self.value, value_type)
        if value_type == "text":
            return f"{header} {label} «{formatted}»"
        return f"{header} {label} {formatted}"

    def matches(self, actual: Any, value_type: str) -> bool:
        """Проверяет, удовлетворяет ли значение условию."""
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
