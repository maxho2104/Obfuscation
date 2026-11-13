"""Загрузка, сохранение и автоопределение схем разметки."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, List, Sequence

from internal_correspondence.text_import.errors import SchemeError
from internal_correspondence.text_import.models import LayoutScheme, SchemeMatch


def load_scheme_file(path: Path) -> LayoutScheme:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SchemeError("scheme_not_found", f"scheme not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemeError("scheme_invalid", f"cannot read scheme {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SchemeError("scheme_invalid", f"scheme root must be an object: {path}")
    scheme = LayoutScheme.from_dict(data)
    errors = scheme.validate()
    if errors:
        raise SchemeError("scheme_invalid", "; ".join(errors), errors=errors)
    return scheme


def load_schemes(directory: Path) -> List[LayoutScheme]:
    directory = Path(directory)
    if not directory.exists():
        return []
    schemes: List[LayoutScheme] = []
    for path in sorted(directory.glob("*.json")):
        try:
            schemes.append(load_scheme_file(path))
        except SchemeError:
            continue
    return schemes


def save_scheme(scheme: LayoutScheme, directory: Path) -> Path:
    errors = scheme.validate()
    if errors:
        raise SchemeError("scheme_invalid", "; ".join(errors), errors=errors)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r"[^\w.\-]+", "_", scheme.name, flags=re.UNICODE).strip("_")
    if not filename:
        filename = "scheme"
    path = directory / f"{filename}.json"
    path.write_text(
        json.dumps(scheme.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def detect_schemes(lines: Sequence[str], schemes: Iterable[LayoutScheme]) -> List[SchemeMatch]:
    """Проверяет схемы на первых строках файла.

    Схема считается подходящей, если первые одна-две строки данных разобраны
    без ошибок. Строка заголовка при ``header_mode=skip`` пропускается.
    """
    if not lines:
        return [SchemeMatch(scheme=item, matched=False, reason="no_lines") for item in schemes]
    result: List[SchemeMatch] = []
    for scheme in schemes:
        errors = scheme.validate()
        if errors:
            result.append(SchemeMatch(scheme=scheme, matched=False, reason="scheme_invalid"))
            continue
        probe = list(lines[:3])
        try:
            from internal_correspondence.text_import.parsing import parse_rows

            report = parse_rows(probe, scheme)
        except SchemeError:
            result.append(SchemeMatch(scheme=scheme, matched=False, reason="parse_error"))
            continue
        if report.rows and report.problem_count == 0:
            result.append(SchemeMatch(scheme=scheme, matched=True))
        else:
            reason = report.problems[0].code if report.problems else "no_rows"
            result.append(SchemeMatch(scheme=scheme, matched=False, reason=reason))
    return result
