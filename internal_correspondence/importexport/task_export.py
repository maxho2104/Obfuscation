"""Выгрузка задач региона в Excel для передачи в филиалы."""

from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple
from uuid import UUID

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from internal_correspondence.importexport.task_import import (
    TASK_HEADERS,
    TASK_SHEET_NAME,
)
from internal_correspondence.orm.models import (
    AddedTask,
    Department,
    Employee,
    ScientificTask,
    TerritorialUnit,
    WorkingGroup,
)
from internal_correspondence.services.task_distribution_service import FinancialPeriod

_COLUMN_WIDTHS = [18, 60, 12, 15, 15, 40, 18, 18]

DISTRIBUTION_SHEET_NAME = "Распределение задач"
DISTRIBUTION_HEADERS = [
    "№ п/п",
    "Код задачи",
    "Наименование",
    "Дата начала",
    "Дата завершения",
    "Отдел",
    "Сотрудники",
]
_DISTRIBUTION_WIDTHS = [8, 18, 60, 14, 14, 32, 55]


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


def branch_tasks(
    session: Session, branch_id: str, period: FinancialPeriod
) -> List[ScientificTask]:
    """Задачи, назначенные филиалу и попадающие в период."""
    stmt = (
        select(ScientificTask)
        .join(AddedTask, AddedTask.task_id == ScientificTask.id)
        .where(
            AddedTask.node_type == "branch",
            AddedTask.node_id == branch_id,
            ScientificTask.start_date <= period.end,
            (ScientificTask.end_date.is_(None))
            | (ScientificTask.end_date >= period.start),
        )
        .distinct()
        .order_by(ScientificTask.id)
    )
    return list(session.execute(stmt).scalars().all())


def _uuid_values(values: Iterable[str]):
    """Преобразует строковые идентификаторы узлов в UUID, пропуская мусор."""
    result = []
    for value in values:
        try:
            result.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return result


def _distribution_rows(
    session: Session, tasks: Sequence[ScientificTask], branch_id: str
) -> List[Tuple[ScientificTask, str, str]]:
    """Строки распределения: задача × отдел, сотрудники через «; »."""
    task_ids = [task.id for task in tasks]
    if not task_ids:
        return []

    assignments = list(
        session.execute(
            select(AddedTask).where(
                AddedTask.task_id.in_(task_ids),
                AddedTask.node_type.in_(("department", "employee", "workgroup")),
            )
        ).scalars()
    )

    department_ids = _uuid_values(
        item.node_id for item in assignments if item.node_type == "department"
    )
    employee_ids = _uuid_values(
        item.node_id for item in assignments if item.node_type == "employee"
    )
    group_ids = _uuid_values(
        item.node_id for item in assignments if item.node_type == "workgroup"
    )

    departments = {
        item.id: item
        for item in session.execute(
            select(Department).where(
                Department.id.in_(department_ids),
                Department.branch_id == branch_id,
            )
        ).scalars()
    }
    employees = {
        item.id: item
        for item in session.execute(
            select(Employee).where(Employee.id.in_(employee_ids))
        ).scalars()
    }
    groups = {
        item.id: item
        for item in session.execute(
            select(WorkingGroup).where(WorkingGroup.id.in_(group_ids))
        ).scalars()
    }

    task_departments: Dict[str, Set] = {task_id: set() for task_id in task_ids}
    task_employees: Dict[Tuple[str, object], Set] = {}

    for item in assignments:
        task_id = item.task_id
        if item.node_type == "department":
            try:
                department_id = UUID(item.node_id)
            except (TypeError, ValueError):
                continue
            if department_id in departments:
                task_departments[task_id].add(department_id)
        elif item.node_type == "employee":
            try:
                employee_id = UUID(item.node_id)
            except (TypeError, ValueError):
                continue
            employee = employees.get(employee_id)
            if (
                employee is None
                or employee.department_id is None
                or employee.department_id not in departments
            ):
                continue
            task_departments[task_id].add(employee.department_id)
            task_employees.setdefault(
                (task_id, employee.department_id), set()
            ).add(employee_id)
        elif item.node_type == "workgroup":
            try:
                group_id = UUID(item.node_id)
            except (TypeError, ValueError):
                continue
            group = groups.get(group_id)
            if (
                group is not None
                and group.department_id is not None
                and group.department_id in departments
            ):
                task_departments[task_id].add(group.department_id)

    rows: List[Tuple[ScientificTask, str, str]] = []
    for task in tasks:
        department_ids_for_task = task_departments.get(task.id) or set()
        if not department_ids_for_task:
            rows.append((task, "", ""))
            continue
        ordered = sorted(
            department_ids_for_task,
            key=lambda department_id: (
                departments[department_id].short_name
                or departments[department_id].name
            ),
        )
        for department_id in ordered:
            department = departments[department_id]
            label = department.short_name or department.name
            names = sorted(
                employees[employee_id].display_name()
                for employee_id in task_employees.get((task.id, department_id), set())
                if employee_id in employees
            )
            rows.append((task, label, "; ".join(names)))
    return rows


def write_branch_distribution(
    session: Session,
    branch_id: str,
    period: FinancialPeriod,
    path: Path,
) -> int:
    """Сохраняет распределение задач филиала; возвращает число строк."""
    tasks = branch_tasks(session, branch_id, period)
    if not tasks:
        raise TaskExportError(
            f"У филиала «{branch_id}» нет задач за период {period.label}."
        )

    rows = _distribution_rows(session, tasks, branch_id)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = DISTRIBUTION_SHEET_NAME
    sheet.append(DISTRIBUTION_HEADERS)

    header_font = Font(bold=True)
    for column, width in enumerate(_DISTRIBUTION_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width
        cell = sheet.cell(row=1, column=column)
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    for number, (task, department, employees_text) in enumerate(rows, start=1):
        sheet.append(
            [
                number,
                task.id,
                task.name,
                task.start_date,
                task.end_date,
                department,
                employees_text,
            ]
        )
        row = sheet.max_row
        for column in (4, 5):
            sheet.cell(row=row, column=column).number_format = "DD.MM.YYYY"

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:G{sheet.max_row}"
    workbook.save(path)
    return len(rows)


def default_distribution_filename(branch_id: str, period: FinancialPeriod) -> str:
    """Имя файла распределения: Распределение_задач_<код>_<период>.xlsx."""
    safe = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in branch_id
    )
    return f"Распределение_задач_{safe}_{period.year}-{period.year + 1}.xlsx"


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
