"""Выгрузка задач региона в Excel для передачи в филиалы."""

from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from internal_correspondence.importexport.task_import import (
    TASK_HEADERS,
    TASK_SHEET_NAME,
)
from internal_correspondence.orm.models import AddedTask, ScientificTask, TerritorialUnit
from internal_correspondence.services.task_distribution_service import FinancialPeriod

_COLUMN_WIDTHS = [18, 60, 12, 15, 15, 40, 18, 18]


class TaskExportError(Exception):
    """Ошибка выгрузки задач."""


def region_tasks(
    session: Session, region_id: str, period: FinancialPeriod
) -> List[ScientificTask]:
    """Задачи, назначенные региону и попадающие в период."""
    stmt = (
        select(ScientificTask)
        .join(AddedTask, AddedTask.task_id == ScientificTask.id)
        .where(
            AddedTask.node_type == "region",
            AddedTask.node_id == region_id,
            ScientificTask.start_date <= period.end,
            (ScientificTask.end_date.is_(None))
            | (ScientificTask.end_date >= period.start),
        )
        .distinct()
        .order_by(ScientificTask.id)
    )
    return list(session.execute(stmt).scalars().all())


def write_region_file(
    session: Session,
    region: TerritorialUnit,
    period: FinancialPeriod,
    path: Path,
) -> int:
    """Записывает файл одного региона; возвращает число задач."""
    tasks = region_tasks(session, region.id, period)
    if not tasks:
        raise TaskExportError(
            f"У региона «{region.name}» нет задач за период {period.label}."
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = TASK_SHEET_NAME
    sheet.append(TASK_HEADERS)

    header_font = Font(bold=True)
    for column, width in enumerate(_COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width
        cell = sheet.cell(row=1, column=column)
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    for task in tasks:
        sheet.append(
            [
                task.id,
                task.name,
                task.type,
                task.start_date,
                task.end_date,
                task.comment,
                float(task.partial_threshold)
                if task.partial_threshold is not None
                else None,
                float(task.full_threshold)
                if task.full_threshold is not None
                else None,
            ]
        )
        row = sheet.max_row
        for column in (4, 5):
            sheet.cell(row=row, column=column).number_format = "DD.MM.YYYY"
        for column in (7, 8):
            sheet.cell(row=row, column=column).number_format = "0.00"

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:H{sheet.max_row}"
    workbook.save(path)
    return len(tasks)


def default_region_filename(region: TerritorialUnit, period: FinancialPeriod) -> str:
    """Имя файла по умолчанию: Задачи_<код>_<период>.xlsx."""
    safe = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in region.id
    )
    return f"Задачи_{safe}_{period.year}-{period.year + 1}.xlsx"


def export_regions(
    session: Session,
    period: FinancialPeriod,
    regions: Sequence[TerritorialUnit],
    directory: Path,
) -> List[Path]:
    """Выгружает по файлу на регион; регионы без задач пропускает."""
    directory.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for region in regions:
        if not region_tasks(session, region.id, period):
            continue
        path = directory / default_region_filename(region, period)
        write_region_file(session, region, period, path)
        written.append(path)
    return written
