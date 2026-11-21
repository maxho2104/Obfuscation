"""Расчёт показателей для вкладки «Дашборд».

Сервис только читает данные и не создаёт записи change tracking.
Все агрегаты считаются по выбранному периоду и области видимости роли.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, selectinload

from internal_correspondence.core.constants import Role
from internal_correspondence.core.domain_pack import enum_codes, enum_label, enum_weight
from internal_correspondence.core.enum_registry import pack_enum_display
from internal_correspondence.orm.labels import entity_label
from internal_correspondence.orm.models import (
    AddedTask,
    Branch,
    Change,
    Department,
    Evaluation,
    ScientificMaterial,
    ScientificTask,
    Telegram,
)
from internal_correspondence.reports.statistics_service import (
    PERIOD_HALF,
    PERIOD_MONTH,
    PERIOD_QUARTER,
    PERIOD_YEAR,
    Period,
    build_month_period,
    build_reporting_period,
)
from internal_correspondence.text_import.repository import import_log
from internal_correspondence.utils.string_resources import STRINGS

MONTH_SHORT = (
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)

NODE_BRANCH = "branch"


@dataclass(frozen=True)
class DashboardFilter:
    """Параметры отбора показателей."""

    period_type: str = PERIOD_YEAR
    year: int = field(default_factory=lambda: date.today().year)
    half: int = 1
    quarter: int = 1
    month: int = 1
    financial: bool = False
    branch_id: Optional[str] = None


@dataclass(frozen=True)
class KpiValue:
    """Одно значение карточки KPI."""

    key: str
    label: str
    value: str
    detail: str = ""
    delta: Optional[float] = None


@dataclass(frozen=True)
class RecentDocument:
    """Строка таблицы последних документов."""

    kind: str
    number: str
    document_date: Optional[date]
    name: str
    branch: str
    evaluation: str


@dataclass(frozen=True)
class DashboardData:
    """Полный набор данных для отрисовки вкладки."""

    period_label: str
    documents_total: int
    materials_total: int
    telegrams_total: int
    evaluated_count: int
    evaluation_average: Optional[float]
    tasks_total: int
    tasks_assigned: int
    tasks_unassigned: int
    tasks_overdue: int
    changes_total: int
    import_status: Optional[str]
    import_matched: int
    import_unmatched: int
    monthly_labels: List[str]
    monthly_materials: List[int]
    monthly_telegrams: List[int]
    material_types: List[Tuple[str, int]]
    telegram_types: List[Tuple[str, int]]
    evaluation_counts: List[Tuple[str, int]]
    ranking_title: str
    ranking: List[Tuple[str, int]]
    ranking_children: List[List[Tuple[str, int]]]
    recent: List[RecentDocument]
    attention: List[Tuple[str, int]]
    kpi: List[KpiValue]


class DashboardService:
    """Считает показатели дашборда по данным приложения."""

    def __init__(self, session: Session, role: str, branch_id: Optional[str] = None) -> None:
        self.session = session
        self.role = Role(role)
        self.branch_id = branch_id
        self._is_branch = self.role == Role.BRANCH
        if self._is_branch and not self.branch_id:
            raise ValueError("Для роли «филиал» не указан филиал.")

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------
    def available_years(self) -> List[int]:
        """Годы, за которые есть документы, плюс текущий год."""
        bounds: List[int] = [date.today().year]
        for model in (ScientificMaterial, Telegram):
            date_col = func.coalesce(model.outgoing_date, model.incoming_date)
            row = self.session.execute(
                select(func.min(date_col), func.max(date_col)).where(date_col.isnot(None))
            ).one()
            for value in row:
                if isinstance(value, date):
                    bounds.append(value.year)
        start, end = min(bounds), max(bounds)
        return list(range(start, end + 1))

    def available_branches(self) -> List[Branch]:
        """Активные (все существующие) филиалы для фильтра головного офиса."""
        return list(
            self.session.scalars(select(Branch).order_by(Branch.short_name, Branch.name))
        )

    def load(self, params: DashboardFilter) -> DashboardData:
        """Считает все показатели для указанного фильтра."""
        scope = self.branch_id if self._is_branch else params.branch_id
        period = self._select_period(params)
        previous = self._previous_period(params, period)

        documents = self._load_documents(period, scope)
        previous_documents = self._load_documents(previous, scope)
        tasks = self._load_tasks(period, scope)
        task_assignments = self._load_assignments(tasks)
        changes_total = self._changes_count() if self._is_branch else 0
        import_info = self._latest_import() if not self._is_branch else None

        materials = [doc for doc in documents if isinstance(doc, ScientificMaterial)]
        telegrams = [doc for doc in documents if isinstance(doc, Telegram)]
        previous_count = len(previous_documents)
        documents_delta = self._delta(len(documents), previous_count)

        evaluated = [doc for doc in documents if doc.latest_evaluation is not None]
        evaluated_count = len(evaluated)
        evaluation_average = self._evaluation_average(evaluated)

        assigned, unassigned, overdue = self._task_stats(
            tasks, task_assignments, scope
        )
        monthly_labels, monthly_materials, monthly_telegrams = self._monthly_series(
            period, materials, telegrams
        )
        material_types = self._type_counts(materials, "material_type")
        telegram_types = self._type_counts(telegrams, "telegram_type")
        evaluation_counts = self._evaluation_counts(evaluated)
        ranking_title, ranking, ranking_children = self._ranking(documents, scope)

        recent = self._recent_documents(documents)
        attention = self._attention(
            documents_total=len(documents),
            without_evaluation=len(documents) - evaluated_count,
            tasks_unassigned=unassigned,
            tasks_overdue=overdue,
            changes_total=changes_total,
            import_info=import_info,
        )
        kpi = self._kpi(
            documents_total=len(documents),
            materials_total=len(materials),
            telegrams_total=len(telegrams),
            documents_delta=documents_delta,
            evaluated_count=evaluated_count,
            evaluation_average=evaluation_average,
            tasks_assigned=assigned,
            tasks_unassigned=unassigned,
            changes_total=changes_total,
            import_info=import_info,
        )

        return DashboardData(
            period_label=self._period_label(period),
            documents_total=len(documents),
            materials_total=len(materials),
            telegrams_total=len(telegrams),
            evaluated_count=evaluated_count,
            evaluation_average=evaluation_average,
            tasks_total=len(tasks),
            tasks_assigned=assigned,
            tasks_unassigned=unassigned,
            tasks_overdue=overdue,
            changes_total=changes_total,
            import_status=import_info[0] if import_info else None,
            import_matched=import_info[1] if import_info else 0,
            import_unmatched=import_info[2] if import_info else 0,
            monthly_labels=monthly_labels,
            monthly_materials=monthly_materials,
            monthly_telegrams=monthly_telegrams,
            material_types=material_types,
            telegram_types=telegram_types,
            evaluation_counts=evaluation_counts,
            ranking_title=ranking_title,
            ranking=ranking,
            ranking_children=ranking_children,
            recent=recent,
            attention=attention,
            kpi=kpi,
        )

    # ------------------------------------------------------------------
    # Периоды
    # ------------------------------------------------------------------
    def _select_period(self, params: DashboardFilter) -> Period:
        reporting = build_reporting_period(params.year, params.financial)
        if params.period_type == PERIOD_YEAR:
            return Period(reporting.label, reporting.start, reporting.end)
        if params.period_type == PERIOD_HALF:
            return reporting.halves[min(max(params.half, 1), 2) - 1]
        if params.period_type == PERIOD_QUARTER:
            return reporting.quarters[min(max(params.quarter, 1), 4) - 1]
        if params.period_type == PERIOD_MONTH:
            return build_month_period(params.year, params.month, params.financial)
        raise ValueError(f"Неизвестный период: {params.period_type}")

    def _previous_period(self, params: DashboardFilter, period: Period) -> Period:
        """Предыдущий период той же длины для расчёта изменения."""
        if params.period_type == PERIOD_YEAR:
            prev = build_reporting_period(params.year - 1, params.financial)
            return Period(prev.label, prev.start, prev.end)
        if params.period_type == PERIOD_HALF:
            if params.half > 1:
                prev = build_reporting_period(params.year, params.financial)
                return prev.halves[0]
            prev = build_reporting_period(params.year - 1, params.financial)
            return prev.halves[1]
        if params.period_type == PERIOD_QUARTER:
            if params.quarter > 1:
                prev = build_reporting_period(params.year, params.financial)
                return prev.quarters[params.quarter - 2]
            prev = build_reporting_period(params.year - 1, params.financial)
            return prev.quarters[3]
        if params.period_type == PERIOD_MONTH:
            year, month = params.year, params.month
            if month == 1:
                year, month = year - 1, 12
            else:
                month -= 1
            return build_month_period(year, month, params.financial)
        return period

    @staticmethod
    def _period_label(period: Period) -> str:
        return (
            f"{period.label}: {period.start.strftime('%d.%m.%Y')}"
            f"–{period.end.strftime('%d.%m.%Y')}"
        )

    # ------------------------------------------------------------------
    # Документы
    # ------------------------------------------------------------------
    def _load_documents(self, period: Period, scope: Optional[str]) -> List[object]:
        result: List[object] = []
        for model in (ScientificMaterial, Telegram):
            date_col = func.coalesce(model.outgoing_date, model.incoming_date)
            query = (
                select(model)
                .where(date_col.isnot(None))
                .where(date_col >= period.start)
                .where(date_col <= period.end)
                .options(
                    selectinload(model.evaluations).selectinload(Evaluation.evaluation_list),
                    selectinload(model.departments),
                    selectinload(model.employees),
                    selectinload(model.branch),
                )
            )
            if scope:
                query = query.where(model.branch_id == scope)
            result.extend(self.session.scalars(query).unique().all())
        return result

    def _monthly_series(
        self,
        period: Period,
        materials: Sequence[ScientificMaterial],
        telegrams: Sequence[Telegram],
    ) -> Tuple[List[str], List[int], List[int]]:
        labels: List[str] = []
        keys: List[Tuple[int, int]] = []
        cursor = date(period.start.year, period.start.month, 1)
        while cursor <= period.end:
            labels.append(MONTH_SHORT[cursor.month - 1])
            keys.append((cursor.year, cursor.month))
            cursor = date(
                cursor.year + (1 if cursor.month == 12 else 0),
                1 if cursor.month == 12 else cursor.month + 1,
                1,
            )

        material_counts = {key: 0 for key in keys}
        telegram_counts = {key: 0 for key in keys}
        for document in materials:
            value = self._document_date(document)
            if value and (value.year, value.month) in material_counts:
                material_counts[(value.year, value.month)] += 1
        for document in telegrams:
            value = self._document_date(document)
            if value and (value.year, value.month) in telegram_counts:
                telegram_counts[(value.year, value.month)] += 1
        return (
            labels,
            [material_counts[key] for key in keys],
            [telegram_counts[key] for key in keys],
        )

    def _type_counts(self, documents: Sequence[object], enum_name: str) -> List[Tuple[str, int]]:
        counts: Dict[str, int] = {}
        for document in documents:
            code = pack_enum_display(enum_name, int(document.type))
            counts[code] = counts.get(code, 0) + 1
        return sorted(
            ((enum_label(enum_name, code), count) for code, count in counts.items()),
            key=lambda item: item[1],
            reverse=True,
        )

    def _evaluation_counts(self, documents: Sequence[object]) -> List[Tuple[str, int]]:
        counts: Dict[str, int] = {}
        for document in documents:
            evaluation = document.latest_evaluation
            if evaluation is None:
                continue
            code = pack_enum_display("evaluation_value", int(evaluation.value))
            counts[code] = counts.get(code, 0) + 1
        return [
            (code, counts[code])
            for code in enum_codes("evaluation_value")
            if counts.get(code)
        ]

    def _evaluation_average(self, documents: Sequence[object]) -> Optional[float]:
        weights: List[int] = []
        for document in documents:
            evaluation = document.latest_evaluation
            if evaluation is None:
                continue
            code = pack_enum_display("evaluation_value", int(evaluation.value))
            weight = enum_weight("evaluation_value", code)
            if weight is not None:
                weights.append(weight)
        if not weights:
            return None
        return sum(weights) / len(weights)

    def _recent_documents(self, documents: Sequence[object]) -> List[RecentDocument]:
        ordered = sorted(
            documents,
            key=lambda document: (
                self._document_date(document) or date.min,
                str(getattr(document, "outgoing_number", "") or ""),
            ),
            reverse=True,
        )
        result: List[RecentDocument] = []
        for document in ordered[:6]:
            evaluation = document.latest_evaluation
            result.append(
                RecentDocument(
                    kind=entity_label(
                        ScientificMaterial
                        if isinstance(document, ScientificMaterial)
                        else Telegram
                    ),
                    number=str(document.outgoing_number or ""),
                    document_date=self._document_date(document),
                    name=str(document.name or ""),
                    branch=document.branch.short_name if document.branch else "",
                    evaluation=(
                        pack_enum_display("evaluation_value", int(evaluation.value))
                        if evaluation
                        else ""
                    ),
                )
            )
        return result

    def _ranking(
        self, documents: Sequence[object], scope: Optional[str]
    ) -> Tuple[str, List[Tuple[str, int]], List[List[Tuple[str, int]]]]:
        counts: Dict[str, int] = {}
        children: Dict[str, Dict[str, int]] = {}
        if self._is_branch or scope:
            title = STRINGS.dashboard_chart_ranking_departments
            for document in documents:
                for department in document.departments:
                    label = department.short_name or department.name
                    counts[label] = counts.get(label, 0) + 1
                    bucket = children.setdefault(label, {})
                    for employee in document.employees:
                        if employee.department_id != department.id:
                            continue
                        child = employee.display_name()
                        bucket[child] = bucket.get(child, 0) + 1
        else:
            title = STRINGS.dashboard_chart_ranking
            for document in documents:
                label = (
                    document.branch.short_name
                    if document.branch
                    else STRINGS.dashboard_no_branch
                )
                counts[label] = counts.get(label, 0) + 1
                bucket = children.setdefault(label, {})
                for department in document.departments:
                    child = department.short_name or department.name
                    bucket[child] = bucket.get(child, 0) + 1
        ranking = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
        ranking_children = [
            sorted(children.get(label, {}).items(), key=lambda item: item[1], reverse=True)[:5]
            for label, _ in ranking
        ]
        return title, ranking, ranking_children

    # ------------------------------------------------------------------
    # Задачи
    # ------------------------------------------------------------------
    def _load_tasks(self, period: Period, scope: Optional[str]) -> List[ScientificTask]:
        query = select(ScientificTask).where(
            ScientificTask.start_date <= period.end,
            or_(ScientificTask.end_date.is_(None), ScientificTask.end_date >= period.start),
        )
        tasks = list(self.session.scalars(query))
        if not scope:
            return tasks
        assignments = self.session.scalars(
            select(AddedTask).where(AddedTask.task_id.in_([task.id for task in tasks]))
        ).all() if tasks else []
        allowed = {
            assignment.task_id
            for assignment in assignments
            if assignment.node_type == NODE_BRANCH and assignment.node_id == scope
        }
        return [task for task in tasks if task.id in allowed]

    def _load_assignments(
        self, tasks: Sequence[ScientificTask]
    ) -> Dict[str, Set[Tuple[str, str]]]:
        if not tasks:
            return {}
        ids = [task.id for task in tasks]
        assignments = self.session.scalars(
            select(AddedTask).where(AddedTask.task_id.in_(ids))
        ).all()
        result: Dict[str, Set[Tuple[str, str]]] = {}
        for assignment in assignments:
            result.setdefault(assignment.task_id, set()).add(
                (assignment.node_type, assignment.node_id)
            )
        return result

    def _task_stats(
        self,
        tasks: Sequence[ScientificTask],
        assignments: Dict[str, Set[Tuple[str, str]]],
        scope: Optional[str],
    ) -> Tuple[int, int, int]:
        today = date.today()
        assigned = 0
        unassigned = 0
        overdue = 0
        for task in tasks:
            nodes = assignments.get(task.id, set())
            if scope:
                assigned += 1
                has_child = any(
                    node_type != NODE_BRANCH or node_id != scope
                    for node_type, node_id in nodes
                )
                if not has_child:
                    unassigned += 1
            else:
                if nodes:
                    assigned += 1
                else:
                    unassigned += 1
            if task.end_date is not None and task.end_date < today:
                overdue += 1
        return assigned, unassigned, overdue

    # ------------------------------------------------------------------
    # Изменения и импорт
    # ------------------------------------------------------------------
    def _changes_count(self) -> int:
        return int(self.session.scalar(select(func.count(Change.id))) or 0)

    def _latest_import(self) -> Optional[Tuple[str, int, int]]:
        try:
            row = self.session.execute(
                select(import_log).order_by(import_log.c.started_at.desc()).limit(1)
            ).first()
        except OperationalError:
            self.session.rollback()
            return None
        if row is None:
            return None
        return (
            str(row.status or ""),
            int(row.matched_rows or 0),
            int(row.unmatched_rows or 0),
        )

    # ------------------------------------------------------------------
    # Внимание и KPI
    # ------------------------------------------------------------------
    def _attention(
        self,
        documents_total: int,
        without_evaluation: int,
        tasks_unassigned: int,
        tasks_overdue: int,
        changes_total: int,
        import_info: Optional[Tuple[str, int, int]],
    ) -> List[Tuple[str, int]]:
        items: List[Tuple[str, int]] = []
        if without_evaluation:
            items.append((STRINGS.dashboard_without_evaluation, without_evaluation))
        if tasks_unassigned:
            items.append((STRINGS.dashboard_tasks_unassigned, tasks_unassigned))
        if tasks_overdue:
            items.append((STRINGS.dashboard_tasks_overdue, tasks_overdue))
        if self._is_branch and changes_total:
            items.append((STRINGS.dashboard_changes_attention, changes_total))
        if import_info and import_info[2]:
            items.append((STRINGS.dashboard_import_mismatches, import_info[2]))
        return items

    def _kpi(
        self,
        documents_total: int,
        materials_total: int,
        telegrams_total: int,
        documents_delta: Optional[float],
        evaluated_count: int,
        evaluation_average: Optional[float],
        tasks_assigned: int,
        tasks_unassigned: int,
        changes_total: int,
        import_info: Optional[Tuple[str, int, int]],
    ) -> List[KpiValue]:
        share = (
            f"{evaluated_count * 100 / documents_total:.0f} %"
            if documents_total
            else "—"
        )
        average = f"{evaluation_average:.1f}".replace(".", ",") if evaluation_average else "—"
        result = [
            KpiValue(
                "documents",
                STRINGS.dashboard_documents,
                str(documents_total),
                f"{STRINGS.dashboard_materials.format(count=materials_total)}; "
                f"{STRINGS.dashboard_telegrams.format(count=telegrams_total)}",
                documents_delta,
            ),
            KpiValue(
                "evaluated",
                STRINGS.dashboard_evaluated,
                share,
                STRINGS.dashboard_average.format(value=average),
            ),
            KpiValue(
                "tasks",
                STRINGS.dashboard_tasks,
                f"{tasks_assigned} / {tasks_unassigned}",
                STRINGS.dashboard_tasks_detail,
            ),
        ]
        if self._is_branch:
            result.append(
                KpiValue(
                    "changes",
                    STRINGS.dashboard_changes,
                    str(changes_total),
                    STRINGS.dashboard_changes_detail,
                )
            )
        else:
            status = {
                "committed": STRINGS.dashboard_import_success,
                "rolled_back": STRINGS.dashboard_import_rollback,
                "running": STRINGS.dashboard_import_running,
            }.get(import_info[0], STRINGS.dashboard_import_absent) if import_info else STRINGS.dashboard_import_absent
            result.append(
                KpiValue(
                    "import",
                    STRINGS.dashboard_import,
                    status,
                    (
                        STRINGS.dashboard_import_status.format(
                            matched=import_info[1],
                            total=import_info[1] + import_info[2],
                        )
                        if import_info
                        else STRINGS.dashboard_import_none
                    ),
                )
            )
        return result

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------
    @staticmethod
    def _document_date(document: object) -> Optional[date]:
        return document.outgoing_date or document.incoming_date

    @staticmethod
    def _delta(current: int, previous: int) -> Optional[float]:
        if not previous:
            return None
        return (current - previous) * 100.0 / previous
