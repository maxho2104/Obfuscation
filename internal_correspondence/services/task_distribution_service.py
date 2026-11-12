"""Сервис распределения научных задач по иерархии организации.

Модуль не хранит состояние между запросами: дерево, назначения и периоды
строятся из БД. Назначение задачи узлу описывается строкой ``added_tasks``;
допустимость операции проверяется по родителю узла и роли пользователя.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import Role
from internal_correspondence.orm.models import (
    AddedTask,
    Branch,
    Department,
    Employee,
    ScientificTask,
    TerritorialUnit,
    WorkingGroup,
)
from internal_correspondence.utils.string_resources import STRINGS

# Типы узлов дерева распределения
NODE_ORGANIZATION = "organization"
NODE_REGION = "region"
NODE_BRANCH = "branch"
NODE_DEPARTMENT = "department"
NODE_WORKGROUP = "workgroup"
NODE_EMPLOYEE = "employee"

ORGANIZATION_ID = "__organization__"

# Типы, которые могут быть владельцем назначения
ASSIGNABLE_NODE_TYPES = {
    NODE_REGION,
    NODE_BRANCH,
    NODE_DEPARTMENT,
    NODE_WORKGROUP,
    NODE_EMPLOYEE,
}

NodeKey = Tuple[str, str]


class TaskDistributionError(ValueError):
    """Ошибка операции распределения задачи."""


@dataclass(frozen=True, order=True)
class FinancialPeriod:
    """Финансовый год: 1 октября — 30 сентября."""

    year: int

    @property
    def start(self) -> date:
        return date(self.year, 10, 1)

    @property
    def end(self) -> date:
        return date(self.year + 1, 9, 30)

    @property
    def label(self) -> str:
        return f"{self.year}–{self.year + 1}"

    @property
    def title(self) -> str:
        return f"{self.label} (01.10.{self.year}–30.09.{self.year + 1})"

    @classmethod
    def current(cls, today: Optional[date] = None) -> "FinancialPeriod":
        today = today or date.today()
        return cls(today.year if today.month >= 10 else today.year - 1)

    def contains(self, start: date, end: Optional[date]) -> bool:
        """Проверяет пересечение срока задачи с финансовым годом."""
        return start <= self.end and (end is None or end >= self.start)


@dataclass
class DistributionNode:
    """Узел дерева распределения."""

    node_type: str
    node_id: str
    label: str
    active: bool = True
    assignable: bool = True
    children: List["DistributionNode"] = field(default_factory=list)

    @property
    def key(self) -> NodeKey:
        return (self.node_type, self.node_id)

    @property
    def is_leaf(self) -> bool:
        return not self.children


class TaskDistributionService:
    """Распределение задач между регионами, филиалами и подразделениями."""

    def __init__(
        self,
        session: Session,
        role: Role | str,
        branch_id: Optional[str] = None,
    ) -> None:
        self.session = session
        self.role = role
        self.branch_id = branch_id

        self._tree: Optional[List[DistributionNode]] = None
        self._nodes: Dict[NodeKey, DistributionNode] = {}
        self._descendants: Dict[NodeKey, Set[NodeKey]] = {}
        self._branch_region: Dict[str, str] = {}
        self._department_branch: Dict[str, str] = {}
        self._group_department: Dict[str, str] = {}
        self._employee_department: Dict[str, str] = {}

        self._tasks: Dict[str, ScientificTask] = {}
        self._assignments: Dict[str, Set[NodeKey]] = {}
        self._assignment_rows: Dict[Tuple[str, NodeKey], AddedTask] = {}
        self._period: Optional[FinancialPeriod] = None
        self._region_id: Optional[str] = None

    # ------------------------------------------------------------------
    # Роль и область видимости
    # ------------------------------------------------------------------

    @property
    def is_head_office(self) -> bool:
        return self.role == Role.HEAD_OFFICE or self.role == Role.HEAD_OFFICE.value

    @property
    def region_id(self) -> Optional[str]:
        """Регион, доступный филиалу."""
        self._ensure_tree()
        return self._region_id

    def _scope_key(self) -> Optional[NodeKey]:
        """Корень доступной филиалу области (регион)."""
        if self.is_head_office:
            return None
        region = self.region_id
        return (NODE_REGION, region) if region else None

    def in_scope(self, key: NodeKey) -> bool:
        """Проверяет, входит ли узел в доступную пользователю область."""
        if self.is_head_office:
            return True
        scope = self._scope_key()
        if scope is None:
            return False
        return key == scope or key in self.descendants(scope)

    # ------------------------------------------------------------------
    # Дерево
    # ------------------------------------------------------------------

    def build_tree(self) -> List[DistributionNode]:
        """Строит корневые узлы дерева (для ГО — организация, для филиала — регион)."""
        self._ensure_tree()
        return self._tree or []

    def _ensure_tree(self) -> None:
        if self._tree is not None:
            return

        branches = (
            self.session.execute(select(Branch).order_by(Branch.short_name))
            .scalars()
            .all()
        )
        if not self.is_head_office:
            branches = [b for b in branches if b.id == self.branch_id]
            if not branches:
                self._tree = []
                return

        units = {
            unit.id: unit
            for unit in self.session.execute(select(TerritorialUnit)).scalars()
        }
        departments = (
            self.session.execute(select(Department).order_by(Department.name))
            .scalars()
            .all()
        )
        groups = (
            self.session.execute(select(WorkingGroup).order_by(WorkingGroup.name))
            .scalars()
            .all()
        )
        employees = (
            self.session.execute(
                select(Employee).order_by(
                    Employee.last_name, Employee.first_name, Employee.middle_name
                )
            )
            .scalars()
            .all()
        )

        self._branch_region = {
            branch.id: branch.territorial_unit_id for branch in branches
        }
        self._department_branch = {
            str(department.id): department.branch_id for department in departments
        }
        self._group_department = {
            str(group.id): str(group.department_id) for group in groups
        }
        self._employee_department = {
            str(employee.id): str(employee.department_id) for employee in employees
        }

        departments_by_branch: Dict[str, List[Department]] = {}
        for department in departments:
            departments_by_branch.setdefault(department.branch_id, []).append(department)
        groups_by_department: Dict[str, List[WorkingGroup]] = {}
        for group in groups:
            groups_by_department.setdefault(group.department_id, []).append(group)
        employees_by_department: Dict[str, List[Employee]] = {}
        employees_by_group: Dict[str, List[Employee]] = {}
        for employee in employees:
            employees_by_department.setdefault(employee.department_id, []).append(
                employee
            )
            if employee.working_group_id and employee.worked_in_workgroup_on(
                date.today()
            ):
                employees_by_group.setdefault(
                    employee.working_group_id, []
                ).append(employee)

        def make_node(
            parent: Optional[DistributionNode],
            node_type: str,
            node_id: str,
            label: str,
            active: bool = True,
            assignable: bool = True,
        ) -> DistributionNode:
            node = DistributionNode(
                node_type=node_type,
                node_id=node_id,
                label=label,
                active=active,
                assignable=assignable,
            )
            if parent is not None:
                parent.children.append(node)
            # Первый экземпляр узла считается каноническим: сотрудник,
            # показанный в отделе, важнее справочного сотрудника в группе.
            self._nodes.setdefault(node.key, node)
            return node

        def fill_department(department: Department) -> DistributionNode:
            node = make_node(
                None,
                NODE_DEPARTMENT,
                str(department.id),
                department.name,
                active=bool(department.active),
            )
            for employee in employees_by_department.get(department.id, []):
                make_node(
                    node,
                    NODE_EMPLOYEE,
                    str(employee.id),
                    employee.display_name(),
                    active=bool(employee.active),
                    assignable=True,
                )
            for group in groups_by_department.get(department.id, []):
                group_node = make_node(
                    node,
                    NODE_WORKGROUP,
                    str(group.id),
                    group.name,
                    active=bool(group.active),
                )
                for employee in employees_by_group.get(group.id, []):
                    make_node(
                        group_node,
                        NODE_EMPLOYEE,
                        str(employee.id),
                        employee.display_name(),
                        active=bool(employee.active),
                        assignable=False,
                    )
            return node

        def fill_branch(branch: Branch) -> DistributionNode:
            node = make_node(
                None,
                NODE_BRANCH,
                branch.id,
                branch.short_name or branch.name,
            )
            for department in departments_by_branch.get(branch.id, []):
                dept_node = fill_department(department)
                node.children.append(dept_node)
            return node

        def fill_region(region_id: str, region_branches: Sequence[Branch]):
            unit = units.get(region_id)
            label = unit.name if unit else region_id
            node = make_node(
                None,
                NODE_REGION,
                region_id,
                label,
            )
            for branch in region_branches:
                branch_node = fill_branch(branch)
                node.children.append(branch_node)
            return node

        if self.is_head_office:
            organization = make_node(
                None,
                NODE_ORGANIZATION,
                ORGANIZATION_ID,
                STRINGS.task_organization,
                assignable=False,
            )
            branches_by_region: Dict[str, List[Branch]] = {}
            for branch in branches:
                branches_by_region.setdefault(branch.territorial_unit_id, []).append(
                    branch
                )
            for region_id in sorted(
                branches_by_region,
                key=lambda rid: (units[rid].name if rid in units else rid),
            ):
                region_node = fill_region(region_id, branches_by_region[region_id])
                organization.children.append(region_node)
            self._tree = [organization]
        else:
            branch = branches[0]
            self._region_id = branch.territorial_unit_id
            region_node = fill_region(branch.territorial_unit_id, [branch])
            self._tree = [region_node]

        self._build_descendants(self._tree)

    def _build_descendants(self, roots: Iterable[DistributionNode]) -> None:
        def visit(node: DistributionNode) -> Set[NodeKey]:
            result: Set[NodeKey] = set()
            for child in node.children:
                result.add(child.key)
                result |= visit(child)
            self._descendants[node.key] = result
            return result

        for root in roots:
            visit(root)

    def node(self, key: NodeKey) -> Optional[DistributionNode]:
        """Возвращает канонический узел по ключу."""
        self._ensure_tree()
        return self._nodes.get(key)

    def descendants(self, key: NodeKey) -> Set[NodeKey]:
        """Возвращает всех потомков узла (без самого узла)."""
        self._ensure_tree()
        return set(self._descendants.get(key, set()))

    def parent_key(self, key: NodeKey) -> Optional[NodeKey]:
        """Возвращает канонического родителя узла."""
        self._ensure_tree()
        node_type, node_id = key
        if node_type == NODE_ORGANIZATION:
            return None
        if node_type == NODE_REGION:
            return (NODE_ORGANIZATION, ORGANIZATION_ID) if self.is_head_office else None
        if node_type == NODE_BRANCH:
            region = self._branch_region.get(node_id)
            return (NODE_REGION, region) if region else None
        if node_type == NODE_DEPARTMENT:
            branch = self._department_branch.get(node_id)
            return (NODE_BRANCH, branch) if branch else None
        if node_type == NODE_WORKGROUP:
            department = self._group_department.get(node_id)
            return (NODE_DEPARTMENT, department) if department else None
        if node_type == NODE_EMPLOYEE:
            department = self._employee_department.get(node_id)
            return (NODE_DEPARTMENT, department) if department else None
        return None

    def ancestors(self, key: NodeKey) -> List[NodeKey]:
        """Возвращает предков узла от родителя к корню."""
        result: List[NodeKey] = []
        current = self.parent_key(key)
        while current is not None:
            result.append(current)
            current = self.parent_key(current)
        return result

    def node_label(self, key: NodeKey) -> str:
        node = self.node(key)
        if node is not None:
            return node.label
        return f"{key[0]}:{key[1]}"

    # ------------------------------------------------------------------
    # Периоды
    # ------------------------------------------------------------------

    def available_periods(self) -> List[FinancialPeriod]:
        """Возвращает годы с задачами плюс текущий и следующий."""
        tasks = (
            self.session.execute(select(ScientificTask)).scalars().all()
        )
        visible = self._visible_tasks_without_state(tasks)
        current = FinancialPeriod.current()
        years: Set[int] = {current.year, current.year + 1}
        for task in visible:
            start_year = self._fiscal_year(task.start_date)
            end_year = (
                self._fiscal_year(task.end_date)
                if task.end_date is not None
                else max(current.year + 1, start_year)
            )
            for year in range(min(start_year, end_year), max(start_year, end_year) + 1):
                years.add(year)
        return [FinancialPeriod(year) for year in sorted(years, reverse=True)]

    @staticmethod
    def _fiscal_year(value: date) -> int:
        return value.year if value.month >= 10 else value.year - 1

    def tasks(self, period: FinancialPeriod) -> List[ScientificTask]:
        """Загружает задачи периода и доступные назначения."""
        self._ensure_tree()
        stmt = (
            select(ScientificTask)
            .where(ScientificTask.start_date <= period.end)
            .where(
                (ScientificTask.end_date.is_(None))
                | (ScientificTask.end_date >= period.start)
            )
            .order_by(ScientificTask.id)
        )
        tasks = list(self.session.execute(stmt).scalars().all())
        self._tasks = {task.id: task for task in tasks}
        self._load_assignments(tasks)
        self._period = period
        return self._visible_tasks(tasks)

    def _visible_tasks_without_state(
        self, tasks: Sequence[ScientificTask]
    ) -> List[ScientificTask]:
        if self.is_head_office:
            return list(tasks)
        assignments = self._load_assignment_map([task.id for task in tasks])
        scope = self._scope_key()
        if scope is None:
            return []
        scope_keys = {scope} | self.descendants(scope)
        return [
            task
            for task in tasks
            if assignments.get(task.id, set()) & scope_keys
        ]

    def _visible_tasks(self, tasks: Sequence[ScientificTask]) -> List[ScientificTask]:
        if self.is_head_office:
            return list(tasks)
        scope = self._scope_key()
        if scope is None:
            return []
        scope_keys = {scope} | self.descendants(scope)
        return [
            task
            for task in tasks
            if self._assignments.get(task.id, set()) & scope_keys
        ]

    # ------------------------------------------------------------------
    # Назначения
    # ------------------------------------------------------------------

    def _load_assignment_map(
        self, task_ids: Sequence[str]
    ) -> Dict[str, Set[NodeKey]]:
        result: Dict[str, Set[NodeKey]] = {}
        if not task_ids:
            return result
        rows = (
            self.session.execute(
                select(AddedTask).where(AddedTask.task_id.in_(list(task_ids)))
            )
            .scalars()
            .all()
        )
        for row in rows:
            result.setdefault(row.task_id, set()).add(
                (row.node_type, row.node_id)
            )
        return result

    def _load_assignments(self, tasks: Sequence[ScientificTask]) -> None:
        task_ids = [task.id for task in tasks]
        self._assignments = self._load_assignment_map(task_ids)
        self._assignment_rows = {}
        if not task_ids:
            return
        rows = (
            self.session.execute(
                select(AddedTask).where(AddedTask.task_id.in_(task_ids))
            )
            .scalars()
            .all()
        )
        for row in rows:
            self._assignment_rows[(row.task_id, (row.node_type, row.node_id))] = row

    def reload(self, period: FinancialPeriod) -> List[ScientificTask]:
        """Перечитывает задачи и назначения после изменения."""
        return self.tasks(period)

    def assigned_task_ids(self, key: NodeKey) -> Set[str]:
        return {
            task_id
            for task_id, keys in self._assignments.items()
            if key in keys
        }

    def is_assigned(self, task: ScientificTask, key: NodeKey) -> bool:
        return key in self._assignments.get(task.id, set())

    def tasks_for_node(
        self, node: DistributionNode, period: FinancialPeriod
    ) -> List[ScientificTask]:
        """Задачи, назначенные узлу, в порядке кода."""
        if node.node_type == NODE_ORGANIZATION:
            return list(self._tasks.values())
        keys = self._assignments
        result = [
            task
            for task in self._tasks.values()
            if node.key in keys.get(task.id, set())
            and period.contains(task.start_date, task.end_date)
        ]
        return sorted(result, key=lambda task: task.id)

    def tasks_for_parent(
        self, node: DistributionNode, period: FinancialPeriod
    ) -> List[ScientificTask]:
        """Задачи вышестоящего узла (для средней таблицы)."""
        parent = self.parent_key(node.key)
        if parent is None:
            return self.tasks_for_node(node, period)
        parent_node = self.node(parent)
        if parent_node is None:
            return []
        return self.tasks_for_node(parent_node, period)

    def is_undistributed(self, task: ScientificTask, owner: DistributionNode) -> bool:
        """Задача не назначена ни одному потомку владельца списка."""
        if owner.node_type in (NODE_WORKGROUP, NODE_EMPLOYEE):
            return False
        descendants = self.descendants(owner.key)
        if not descendants:
            return False
        return not (self._assignments.get(task.id, set()) & descendants)

    # ------------------------------------------------------------------
    # Проверки и операции
    # ------------------------------------------------------------------

    def can_assign(self, node: DistributionNode) -> Tuple[bool, str]:
        """Проверяет право назначения задачи узлу."""
        if node.node_type == NODE_ORGANIZATION:
            return False, "Задачи назначаются регионам, а не организации."
        if not node.assignable:
            return False, "Сотрудник в рабочей группе — справочный узел."
        if not node.active:
            return False, "Узел неактивен."
        if not self.is_head_office:
            if not self.in_scope(node.key):
                return False, "Узел вне доступного филиала."
            if node.node_type == NODE_REGION:
                return False, "Филиал не назначает задачи региону."
        return True, ""

    def can_unassign(self, node: DistributionNode) -> Tuple[bool, str]:
        """Проверяет право снятия задачи с узла."""
        if not node.assignable:
            return False, "Сотрудник в рабочей группе — справочный узел."
        if not self.is_head_office:
            if not self.in_scope(node.key):
                return False, "Узел вне доступного филиала."
            if node.node_type in (NODE_REGION, NODE_BRANCH):
                return False, "Филиал не снимает задачи с региона и филиала."
        return True, ""

    def assign(
        self, tasks: Sequence[ScientificTask], node: DistributionNode
    ) -> int:
        """Назначает задачи узлу. Возвращает число новых назначений."""
        if not tasks:
            return 0
        allowed, reason = self.can_assign(node)
        if not allowed:
            raise TaskDistributionError(reason)

        self._ensure_tasks_loaded(tasks)

        # Филиал, берущий задачу себе, автоматически фиксирует её за регионом.
        if not self.is_head_office and node.node_type == NODE_BRANCH:
            region_key = (NODE_REGION, self.region_id or "")
            for task in tasks:
                if region_key not in self._assignments.get(task.id, set()):
                    self._create_assignment(task, region_key)

        parent = self.parent_key(node.key)
        if parent is not None and parent[0] != NODE_ORGANIZATION:
            missing = [
                task
                for task in tasks
                if parent not in self._assignments.get(task.id, set())
            ]
            if missing:
                raise TaskDistributionError(
                    "Сначала назначьте задачи вышестоящему узлу: "
                    + ", ".join(task.id for task in missing[:5])
                )

        created = 0
        for task in tasks:
            if node.key in self._assignments.get(task.id, set()):
                continue
            self._create_assignment(task, node.key)
            created += 1
        self.session.flush()
        return created

    def unassign(
        self, tasks: Sequence[ScientificTask], node: DistributionNode
    ) -> int:
        """Снимает задачи с узла. Возвращает число удалённых назначений."""
        if not tasks:
            return 0
        allowed, reason = self.can_unassign(node)
        if not allowed:
            raise TaskDistributionError(reason)

        self._ensure_tasks_loaded(tasks)
        descendants = self.descendants(node.key)
        blocked: List[str] = []
        for task in tasks:
            keys = self._assignments.get(task.id, set())
            if node.key not in keys:
                continue
            below = keys & descendants
            if below:
                blocked.append(task.id)
        if blocked:
            raise TaskDistributionError(
                "Задача уже назначена ниже: " + ", ".join(blocked[:5])
            )

        removed = 0
        for task in tasks:
            row = self._assignment_rows.pop((task.id, node.key), None)
            if row is None:
                continue
            self.session.delete(row)
            self._assignments.get(task.id, set()).discard(node.key)
            removed += 1
        self.session.flush()
        return removed

    def add_region_assignments(
        self, tasks: Sequence[ScientificTask], region_id: Optional[str] = None
    ) -> int:
        """Помещает задачи в пул региона (для импорта филиалом).

        Филиалу запрещено назначать задачи региону обычной операцией, но при
        импорте файла региона задачи должны появиться в среднем списке, чтобы
        филиал мог забрать их кнопкой «>>>».
        """
        target_region = region_id or self.region_id
        if target_region is None:
            raise TaskDistributionError("Не определен регион филиала.")
        if self.is_head_office and region_id is None:
            raise TaskDistributionError("Не указан регион для пула задач.")

        self._ensure_tasks_loaded(tasks)
        key = (NODE_REGION, target_region)
        created = 0
        for task in tasks:
            if key in self._assignments.get(task.id, set()):
                continue
            self._create_assignment(task, key)
            created += 1
        self.session.flush()
        return created

    def _create_assignment(self, task: ScientificTask, key: NodeKey) -> AddedTask:
        row = AddedTask(task_id=task.id, node_type=key[0], node_id=key[1])
        self.session.add(row)
        self._assignments.setdefault(task.id, set()).add(key)
        self._assignment_rows[(task.id, key)] = row
        return row

    def _ensure_tasks_loaded(self, tasks: Sequence[ScientificTask]) -> None:
        missing = [task for task in tasks if task.id not in self._tasks]
        if missing:
            for task in missing:
                self._tasks[task.id] = task
            self._load_assignments(list(self._tasks.values()))
