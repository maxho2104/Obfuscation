"""Импорт научных задач из Excel и подготовка данных для выгрузки."""

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from internal_correspondence.core.domain_pack import enum_codes, enum_labels
from internal_correspondence.importexport.reference_import import (
    _clean_value,
    _date_from_value,
    _read_sheet_rows,
    _to_float,
)
from internal_correspondence.orm.models import ScientificTask
from internal_correspondence.services.reference_service import (
    ScientificTaskError,
    ScientificTaskService,
)

TASK_SHEET_NAME = "Научные задачи"
TASK_HEADERS = [
    "Код",
    "Наименование",
    "Тип",
    "Начало действия",
    "Конец действия",
    "Комментарий",
    "Частичное решение",
    "Полное решение",
]


@dataclass
class TaskImportResult:
    """Результат импорта задач."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    task_ids: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped


def _as_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _date_from_value(value)


def _as_number(value: Any, label: str, row_number: int) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    number = _to_float(value)
    if number is None:
        raise ScientificTaskError(
            f"строка {row_number}: некорректное значение «{label}»."
        )
    return number


def _type_code(value: Any) -> str:
    """Принимает код типа или его русскую метку."""
    text = _clean_value(value)
    if not text:
        return ""
    if text in enum_codes("scientific_task_type"):
        return text
    for code, label in enum_labels("scientific_task_type").items():
        if text == label:
            return code
    return text


def import_scientific_tasks(
    session: Session, path: Path
) -> TaskImportResult:
    """Импортирует задачи из листа «Научные задачи» (upsert по коду)."""
    rows = _read_sheet_rows(path, TASK_SHEET_NAME)
    service = ScientificTaskService(session)
    result = TaskImportResult()

    for index, row in enumerate(rows, start=2):
        if not any(value not in (None, "") for value in row.values()):
            continue
        try:
            data: Dict[str, Any] = {
                "id": _clean_value(row.get("Код")),
                "name": _clean_value(row.get("Наименование")),
                "type": _type_code(row.get("Тип")),
                "start_date": _as_date(row.get("Начало действия")),
                "end_date": _as_date(row.get("Конец действия")),
                "comment": _clean_value(row.get("Комментарий")),
                "partial_threshold": _as_number(
                    row.get("Частичное решение"), "Частичное решение", index
                ),
                "full_threshold": _as_number(
                    row.get("Полное решение"), "Полное решение", index
                ),
            }
            existing = session.get(ScientificTask, data.get("id") or "")
            if existing is not None:
                service.update_task(existing, data)
                result.updated += 1
            else:
                service.create_task(data)
                result.created += 1
            result.task_ids.append(data["id"])
        except ScientificTaskError as error:
            result.skipped += 1
            result.errors.append(f"Строка {index}: {error}")

    return result


def task_rows(tasks: List[ScientificTask]) -> List[List[Any]]:
    """Готовит строки листа «Научные задачи» для выгрузки."""
    return [
        [
            task.id,
            task.name,
            task.type,
            task.start_date,
            task.end_date,
            task.comment,
            float(task.partial_threshold) if task.partial_threshold is not None else None,
            float(task.full_threshold) if task.full_threshold is not None else None,
        ]
        for task in tasks
    ]
