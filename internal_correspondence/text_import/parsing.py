"""Разбор строк по схеме, нормализация и проверка значений."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Sequence, Tuple

from internal_correspondence.text_import.errors import SchemeError
from internal_correspondence.text_import.models import (
    FieldSpec,
    LayoutScheme,
    ParsedRow,
    ProblemRow,
    ValidationReport,
)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SPACES_RE = re.compile(r"\s+")


class RowProblemError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def normalize_text(value: str) -> str:
    value = _CONTROL_RE.sub("", value)
    value = _SPACES_RE.sub(" ", value)
    return value.strip()


def parse_date(value: str, date_format: str | None) -> date:
    formats: Sequence[str]
    if date_format == "YYYYMM":
        formats = ("%Y%m",)
    elif date_format == "DD.MM.YYYY":
        formats = ("%d.%m.%Y",)
    else:
        formats = ("%d.%m.%Y", "%Y%m")
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return parsed.date()
    raise RowProblemError("field_date", f"invalid date: {value}")


def _effective_fields(scheme: LayoutScheme, lines: Sequence[str]) -> Tuple[List[FieldSpec], int]:
    """Возвращает поля и индекс первой строки данных."""
    if scheme.header_mode != "names":
        start = 1 if scheme.header_mode == "skip" else 0
        return list(scheme.fields), start
    if not lines:
        return list(scheme.fields), 0
    header = lines[0]
    if scheme.mode == "delimited":
        names = [normalize_text(item) for item in header.split(scheme.delimiter)]
    else:
        names = []
        for item in scheme.fields:
            if item.start is None:
                names.append("")
                continue
            end = None if item.length is None else item.start - 1 + item.length
            names.append(normalize_text(header[item.start - 1 : end]))
    fields: List[FieldSpec] = []
    for index, item in enumerate(scheme.fields):
        name = names[index] if index < len(names) and names[index] else item.name
        fields.append(
            FieldSpec(
                name=name,
                type=item.type,
                start=item.start,
                length=item.length,
                required=item.required,
                date_format=item.date_format,
                regex=item.regex,
                normalize_regex=item.normalize_regex,
                default=item.default,
            )
        )
    if len(names) != len(scheme.fields):
        raise SchemeError(
            "header_mismatch",
            f"header has {len(names)} fields, scheme has {len(scheme.fields)}",
        )
    return fields, 1


def _fixed_parts(raw: str, fields: Sequence[FieldSpec]) -> List[str]:
    fixed_ends: List[int] = []
    has_variable = False
    for item in fields:
        if item.length is None:
            has_variable = True
        elif item.start is not None:
            fixed_ends.append(item.start - 1 + item.length)
    minimum = max(fixed_ends) if fixed_ends else 0
    if has_variable:
        if len(raw) < minimum:
            raise RowProblemError(
                "line_length",
                f"line length {len(raw)} is less than {minimum}",
            )
    elif len(raw) != minimum:
        raise RowProblemError(
            "line_length",
            f"line length {len(raw)} does not match {minimum}",
        )
    parts: List[str] = []
    for item in fields:
        if item.start is None:
            raise RowProblemError("field_start", f"field {item.name} has no start")
        begin = item.start - 1
        end = len(raw) if item.length is None else begin + item.length
        if begin > len(raw):
            raise RowProblemError("line_length", f"field {item.name} starts beyond line")
        parts.append(raw[begin:end])
    return parts


def _delimited_parts(raw: str, delimiter: str, fields: Sequence[FieldSpec]) -> List[str]:
    parts = raw.split(delimiter)
    if len(parts) != len(fields):
        raise RowProblemError(
            "field_count",
            f"expected {len(fields)} fields, got {len(parts)}",
        )
    return parts


def _convert(item: FieldSpec, raw_value: str) -> Any:
    value = normalize_text(raw_value)
    if item.normalize_regex:
        value = normalize_text(re.sub(item.normalize_regex, "", value))
    if not value:
        if item.default is not None:
            value = normalize_text(item.default)
    if not value:
        if item.required:
            raise RowProblemError("field_required", f"field {item.name} is required")
        return None
    if item.regex and re.fullmatch(item.regex, value) is None:
        raise RowProblemError("field_regex", f"field {item.name} does not match regex")
    if item.type == "integer":
        if re.fullmatch(r"[+-]?\d+", value) is None:
            raise RowProblemError("field_type", f"field {item.name} is not an integer")
        if value.startswith("+"):
            value = value[1:]
        return int(value)
    if item.type == "date":
        return parse_date(value, item.date_format)
    return value


def parse_line(raw: str, scheme: LayoutScheme, fields: Sequence[FieldSpec]) -> Dict[str, Any]:
    if not raw.strip():
        raise RowProblemError("line_empty", "line is empty")
    if scheme.mode == "fixed":
        parts = _fixed_parts(raw, fields)
    else:
        parts = _delimited_parts(raw, scheme.delimiter, fields)
    data: Dict[str, Any] = {}
    for item, value in zip(fields, parts):
        data[item.name] = _convert(item, value)
    return data


def parse_rows(lines: Sequence[str], scheme: LayoutScheme) -> ValidationReport:
    errors = scheme.validate()
    if errors:
        raise SchemeError("scheme_invalid", "; ".join(errors), errors=errors)
    fields, start = _effective_fields(scheme, lines)
    rows: List[ParsedRow] = []
    for index in range(start, len(lines)):
        raw = lines[index]
        row_no = index + 1
        try:
            data = parse_line(raw, scheme, fields)
        except RowProblemError as exc:
            rows.append(
                ParsedRow(
                    row_no=row_no,
                    raw=raw,
                    problem=ProblemRow(row_no=row_no, raw=raw, code=exc.code, message=exc.message),
                )
            )
        else:
            rows.append(ParsedRow(row_no=row_no, raw=raw, data=data))
    return ValidationReport(rows=rows, total_lines=len(lines))
