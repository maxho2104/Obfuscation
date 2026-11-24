"""Модель таблицы режима «Управление задачами».

Таблица показывает задачи выбранного финансового периода с назначениями
по уровням иерархии и процентом выполнения. Назначения и процент — не
поля ORM-модели, а вычисляемые значения: они собираются из таблицы
``added_tasks`` и связей задачи с материалами и телеграммами.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from sqlalchemy import func, select

from internal_correspondence.core.enum_registry import pack_enum_display
from internal_correspondence.gui.table_model import ColumnDef, SqlAlchemyTableModel
from internal_correspondence.orm.models import (
    AddedTask,
    Branch,
    Department,
    Employee,
    ScientificTask,
    TerritorialUnit,
    material_task_association,
    telegram_task_association,
)
from internal_correspondence.services.task_distribution_service import (
    NODE_BRANCH,
    NODE_DEPARTMENT,
    NODE_EMPLOYEE,
    NODE_REGION,
    NodeKey,
)
from internal_correspondence.utils.string_resources import STRINGS

# Колонки назначений головного офиса и филиала
HEAD_OFFICE_ASSIGNMENT_COLUMNS = ("assigned_regions", "assigned_branches")
BRANCH_ASSIGNMENT_COLUMNS = ("assigned_departments", "assigned_employees")

# Вычисляемые колонки таблицы (нет в ORM-модели задачи)
COMPUTED_COLUMNS = frozenset(
    HEAD_OFFICE_ASSIGNMENT_COLUMNS
    + BRANCH_ASSIGNMENT_COLUMNS
    + ("progress",)
)


def _format_type(value: Any) -> str:
    """Краткий код типа задачи из пакета предметной области («ОЗ»/«ДЗ»)."""
    if value is None:
        return ""
    try:
        return pack_enum_display("scientific_task_type", int(value)) or str(value)
    except (TypeError, ValueError):
        return str(value)


def _format_number(value: Any) -> str:
    """Форматирует числовой порог в стиле таблиц задач (запятая)."""
    if value is None:
        return ""
    return f"{float(value):.2f}".replace(".", ",")


def _format_progress(value: Any) -> str:
    """Форматирует процент выполнения задачи."""
    if value is None:
        return ""
    return f"{value:.0f}%"


def management_columns(is_head_office: bool) -> List[ColumnDef]:
    """Возвращает колонки таблицы управления задачами для роли.

    Головному офису показываются назначения регионам и филиалам, филиалу —
    назначения его отделам и исполнителям.
    """
    columns = [
        ColumnDef("id", STRINGS.task_col_code, width=120),
        ColumnDef("name", STRINGS.task_col_name, width=280),
        ColumnDef("type", STRINGS.task_col_type, width=80, formatter=_format_type),
    ]
    if is_head_office:
        columns.append(
            ColumnDef("assigned_regions", STRINGS.task_col_regions, width=200)
        )
        columns.append(
            ColumnDef("assigned_branches", STRINGS.task_col_branches, width=200)
        )
    else:
        columns.append(
            ColumnDef("assigned_departments", STRINGS.task_col_departments, width=200)
        )
        columns.append(
            ColumnDef("assigned_employees", STRINGS.task_col_employees, width=220)
        )
    columns += [
        ColumnDef(
            "progress",
            STRINGS.task_col_progress,
            width=110,
            formatter=_format_progress,
        ),
        ColumnDef(
            "partial_threshold",
            STRINGS.task_col_partial,
            width=120,
            formatter=_format_number,
        ),
        ColumnDef(
            "full_threshold",
            STRINGS.task_col_full,
            width=120,
            formatter=_format_number,
        ),
        ColumnDef("start_date", STRINGS.task_col_start, width=100),
        ColumnDef("end_date", STRINGS.task_col_end, width=100),
        ColumnDef("comment", STRINGS.task_col_note, width=220),
    ]
    return columns


@dataclass
class _ReferenceCache:
    """Отображаемые названия узлов иерархии для колонок назначений."""

    regions: Dict[str, str]
    branches: Dict[str, str]
    departments: Dict[str, str]
    employees: Dict[str, str]
    department_branch: Dict[str, str]
    employee_department: Dict[str, str]


class TaskManagementModel(SqlAlchemyTableModel):
    """Таблица задач периода с назначениями и процентом выполнения.

    Задачи передаются снаружи (:meth:`set_tasks`), поэтому выборка
    ограничивается периодом и областью видимости роли, а фильтрация,
    сортировка и пагинация выполняются в памяти.
    """

    def __init__(
        self,
        session,
        columns: List[ColumnDef],
        is_head_office: bool = False,
        scope_branch_id: Optional[str] = None,
        parent=None,
    ) -> None:
        self._all_tasks: List[ScientificTask] = []
        self._is_head_office = is_head_office
        self._scope_branch_id = scope_branch_id
        self._assignments: Dict[str, Set[NodeKey]] = {}
        self._document_counts: Dict[str, int] = {}
        self._assignments_ready = False
        self._refs: Optional[_ReferenceCache] = None
        super().__init__(session, ScientificTask, columns, parent=parent)

    # ------------------------------------------------------------------
    # Наполнение
    # ------------------------------------------------------------------

    def set_tasks(self, tasks: Sequence[ScientificTask]) -> None:
        """Задаёт задачи периода и перечитывает таблицу с первой страницы."""
        self._all_tasks = list(tasks)
        self._page = 1
        self.refresh()

    def refresh(self) -> None:
        """Перечитывает таблицу; кэш назначений сбрасывается."""
        self._assignments_ready = False
        self._assignments = {}
        self._document_counts = {}
        super().refresh()

    # ------------------------------------------------------------------
    # Значения вычисляемых колонок
    # ------------------------------------------------------------------

    def _ensure_assignments(self) -> None:
        """Загружает назначения и число документов задач периода одним разом."""
        if self._assignments_ready:
            return
        task_ids = [task.id for task in self._all_tasks]
        if task_ids:
            rows = (
                self.session.execute(
                    select(AddedTask).where(AddedTask.task_id.in_(task_ids))
                )
                .scalars()
                .all()
            )
            for row in rows:
                self._assignments.setdefault(row.task_id, set()).add(
                    (row.node_type, row.node_id)
                )
            self._document_counts = self._count_documents(task_ids)
        self._assignments_ready = True

    def _count_documents(self, task_ids: Sequence[str]) -> Dict[str, int]:
        """Считает материалы и телеграммы, привязанные к задачам."""
        counts: Dict[str, int] = {}
        for association in (
            material_task_association,
            telegram_task_association,
        ):
            rows = self.session.execute(
                select(association.c.task_id, func.count())
                .where(association.c.task_id.in_(list(task_ids)))
                .group_by(association.c.task_id)
            ).all()
            for task_id, count in rows:
                counts[task_id] = counts.get(task_id, 0) + int(count)
        return counts

    def _ensure_refs(self) -> None:
        """Загружает названия узлов иерархии для колонок назначений."""
        if self._refs is not None:
            return
        regions = {
            unit.id: unit.name
            for unit in self.session.execute(select(TerritorialUnit)).scalars()
        }
        branches: Dict[str, str] = {}
        for branch in self.session.execute(select(Branch)).scalars():
            branches[branch.id] = branch.short_name or branch.name
        departments: Dict[str, str] = {}
        department_branch: Dict[str, str] = {}
        for department in self.session.execute(select(Department)).scalars():
            key = str(department.id)
            departments[key] = department.name
            department_branch[key] = department.branch_id
        employees: Dict[str, str] = {}
        employee_department: Dict[str, str] = {}
        for employee in self.session.execute(select(Employee)).scalars():
            key = str(employee.id)
            employees[key] = employee.display_name()
            employee_department[key] = str(employee.department_id)
        self._refs = _ReferenceCache(
            regions=regions,
            branches=branches,
            departments=departments,
            employees=employees,
            department_branch=department_branch,
            employee_department=employee_department,
        )

    def _in_scope(self, node_type: str, node_id: str) -> bool:
        """Проверяет, относится ли узел назначения к области филиала."""
        if self._is_head_office or not self._scope_branch_id:
            return True
        refs = self._refs
        if refs is None:
            return False
        if node_type == NODE_DEPARTMENT:
            return (
                refs.department_branch.get(str(node_id)) == self._scope_branch_id
            )
        if node_type == NODE_EMPLOYEE:
            department_id = refs.employee_department.get(str(node_id))
            return (
                department_id is not None
                and refs.department_branch.get(department_id)
                == self._scope_branch_id
            )
        return False

    def _join_labels(
        self,
        keys: Set[NodeKey],
        node_type: str,
        labels: Dict[str, str],
        scoped: bool,
    ) -> str:
        """Перечисляет названия узлов назначения через запятую."""
        values = []
        for kind, node_id in keys:
            if kind != node_type:
                continue
            if scoped and not self._in_scope(kind, node_id):
                continue
            label = labels.get(node_id) or labels.get(str(node_id))
            if label:
                values.append(label)
        values.sort(key=str.casefold)
        return ", ".join(values)

    def _progress(self, task: ScientificTask) -> Optional[float]:
        """Процент выполнения: документы по задаче / полное решение * 100."""
        full = task.full_threshold
        if full is None:
            return None
        try:
            full_value = float(full)
        except (TypeError, ValueError):
            return None
        if full_value <= 0:
            return None
        documents = self._document_counts.get(task.id, 0)
        return documents / full_value * 100.0

    def _computed_value(self, task: ScientificTask, name: str) -> Any:
        """Возвращает значение вычисляемой колонки для задачи."""
        self._ensure_assignments()
        self._ensure_refs()
        refs = self._refs
        if refs is None:  # pragma: no cover - защита от неверного состояния
            return None
        keys = self._assignments.get(task.id, set())
        if name == "assigned_regions":
            return self._join_labels(keys, NODE_REGION, refs.regions, scoped=False)
        if name == "assigned_branches":
            return self._join_labels(
                keys, NODE_BRANCH, refs.branches, scoped=False
            )
        if name == "assigned_departments":
            return self._join_labels(
                keys, NODE_DEPARTMENT, refs.departments, scoped=True
            )
        if name == "assigned_employees":
            return self._join_labels(
                keys, NODE_EMPLOYEE, refs.employees, scoped=True
            )
        if name == "progress":
            return self._progress(task)
        return None

    def _get_value(self, item: ScientificTask, name: str) -> Any:
        """Значение поля задачи; вычисляемые колонки считаются на месте."""
        if name in COMPUTED_COLUMNS:
            return self._computed_value(item, name)
        return super()._get_value(item, name)

    # ------------------------------------------------------------------
    # Сортировка и пагинация
    # ------------------------------------------------------------------

    def _can_use_db_pagination(self) -> bool:
        """Период и вычисляемые колонки не выражаются запросом к БД."""
        return False

    def _filtered_items(
        self, items: Optional[List[ScientificTask]] = None
    ) -> List[ScientificTask]:
        """Применяет фильтры к задачам периода."""
        return super()._filtered_items(
            list(self._all_tasks) if items is None else items
        )

    def _refresh_in_memory(self) -> None:
        """Загружает задачи периода в память для фильтров и сортировки."""
        all_items = self._filtered_items()
        if self._order_by:
            sort_column = next(
                (column for column in self.columns if column.name == self._order_by),
                None,
            )
            if sort_column is not None:
                all_items.sort(
                    key=lambda item: self._sort_text(item, sort_column),
                    reverse=self._order_desc,
                )
        self._total = len(all_items)
        start = (self._page - 1) * self._page_size
        self._items = all_items[start : start + self._page_size]

    def _sort_text(self, item: ScientificTask, column: ColumnDef) -> Any:
        """Ключ сортировки; процент сравнивается как число, а не как текст."""
        if column.name == "progress":
            value = self._computed_value(item, "progress")
            return (value is None, value or 0.0)
        return super()._sort_text(item, column)

    def pk_of(self, item: ScientificTask) -> Any:
        """Код задачи используется как первичный ключ строки."""
        return item.id

    def task_at(self, row: int) -> Optional[ScientificTask]:
        """Возвращает задачу строки текущей страницы."""
        return self.item_at(row)
