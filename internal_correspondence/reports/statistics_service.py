"""Статистические подсчёты по научным материалам и телеграммам."""

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import EvaluationValue
from internal_correspondence.core.domain_pack import enum_label
from internal_correspondence.core.enum_registry import pack_enum_display
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.labels import entity_label

# Типы периодов
PERIOD_YEAR = "year"
PERIOD_HALF = "half"
PERIOD_QUARTER = "quarter"
PERIOD_MONTH = "month"

PERIOD_LABELS = {
    PERIOD_YEAR: "Год",
    PERIOD_HALF: "Полугодие",
    PERIOD_QUARTER: "Квартал",
    PERIOD_MONTH: "Месяц",
}

# Критерии подсчёта
CRITERION_EMPLOYEE = "employee"
CRITERION_DEPARTMENT = "department"
CRITERION_WORKGROUP = "workgroup"
CRITERION_CONSUMER = "consumer"
CRITERION_TASK = "task"
CRITERION_SOURCE = "source"
CRITERION_EVALUATION = "evaluation"

CRITERION_LABELS = {
    CRITERION_EMPLOYEE: "Сотрудники",
    CRITERION_DEPARTMENT: "Отделы",
    CRITERION_WORKGROUP: "Рабочие группы",
    CRITERION_CONSUMER: "Потребители",
    CRITERION_TASK: "Научные задачи",
    CRITERION_SOURCE: "Источники",
    CRITERION_EVALUATION: "Полученные оценки",
}

_MONTH_NAMES = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)

_ROMAN = ("I", "II", "III", "IV")


@dataclass(frozen=True)
class Period:
    """Календарный период расчёта."""

    label: str
    start: date
    end: date

    def contains(self, value: date) -> bool:
        """Проверяет, попадает ли дата в период."""
        return self.start <= value <= self.end


@dataclass(frozen=True)
class ReportingPeriod:
    """Отчётный год целиком."""

    label: str
    start: date
    end: date
    halves: List[Period]
    quarters: List[Period]


@dataclass
class StatisticsQuery:
    """Параметры статистического подсчёта."""

    model_class: Type[Base]
    criterion: str
    period_type: str
    year: int
    half: int = 1
    quarter: int = 1
    month: int = 1
    financial: bool = False


@dataclass
class StatisticsRow:
    """Строка статистической таблицы."""

    label: str
    values: List[int] = field(default_factory=list)
    total: int = 0


@dataclass
class StatisticsResult:
    """Результат статистического подсчёта."""

    title: str
    period_label: str
    columns: List[str]
    rows: List[StatisticsRow]
    totals: List[int]
    grand_total: int
    month_columns: List[str] = field(default_factory=list)
    month_indices: List[int] = field(default_factory=list)


def _month_period(year: int, month: int) -> Period:
    """Возвращает период, соответствующий календарному месяцу."""
    last_day = calendar.monthrange(year, month)[1]
    return Period(
        _MONTH_NAMES[month - 1],
        date(year, month, 1),
        date(year, month, last_day),
    )


def _months_between(start: date, end: date) -> List[Period]:
    """Возвращает список месяцев, входящих в диапазон."""
    months: List[Period] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(_month_period(year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _calendar_quarter(year: int, quarter: int) -> Period:
    """Возвращает календарный квартал года."""
    start_month = 3 * (quarter - 1) + 1
    last_month = start_month + 2
    last_day = calendar.monthrange(year, last_month)[1]
    start = date(year, start_month, 1)
    end = date(year, last_month, last_day)
    return Period(f"{_ROMAN[quarter - 1]} квартал", start, end)


def build_reporting_period(year: int, financial: bool = False) -> ReportingPeriod:
    """Формирует отчётный год, его полугодия и кварталы."""
    if financial:
        quarters = [
            Period("I квартал", date(year, 10, 1), date(year, 12, 31)),
            Period("II квартал", date(year + 1, 1, 1), date(year + 1, 3, 31)),
            Period("III квартал", date(year + 1, 4, 1), date(year + 1, 6, 30)),
            Period("IV квартал", date(year + 1, 7, 1), date(year + 1, 9, 30)),
        ]
        halves = [
            Period("I полугодие", quarters[0].start, quarters[1].end),
            Period("II полугодие", quarters[2].start, quarters[3].end),
        ]
        return ReportingPeriod(
            f"Финансовый год {year}/{year + 1}",
            date(year, 10, 1),
            date(year + 1, 9, 30),
            halves,
            quarters,
        )

    quarters = [_calendar_quarter(year, quarter) for quarter in range(1, 5)]
    halves = [
        Period("I полугодие", quarters[0].start, quarters[1].end),
        Period("II полугодие", quarters[2].start, quarters[3].end),
    ]
    return ReportingPeriod(
        str(year),
        date(year, 1, 1),
        date(year, 12, 31),
        halves,
        quarters,
    )


def build_columns(
    period_type: str,
    reporting: ReportingPeriod,
    half: int = 1,
    quarter: int = 1,
    month: int = 1,
) -> List[Period]:
    """Возвращает колонки таблицы.

    Базовые значения считаются по месяцам; итоги кварталов выводятся сразу
    после месяцев квартала, итог полугодия — после его кварталов.
    """
    if period_type == PERIOD_YEAR:
        columns: List[Period] = []
        for half_index in range(2):
            for quarter_index in range(half_index * 2, half_index * 2 + 2):
                quarter_period = reporting.quarters[quarter_index]
                columns.extend(
                    _months_between(quarter_period.start, quarter_period.end)
                )
                columns.append(quarter_period)
            columns.append(reporting.halves[half_index])
        return columns

    if period_type == PERIOD_HALF:
        half = min(max(half, 1), 2)
        columns = []
        for quarter_index in range((half - 1) * 2, (half - 1) * 2 + 2):
            quarter_period = reporting.quarters[quarter_index]
            columns.extend(_months_between(quarter_period.start, quarter_period.end))
            columns.append(quarter_period)
        return columns

    if period_type == PERIOD_QUARTER:
        quarter = min(max(quarter, 1), 4)
        selected = reporting.quarters[quarter - 1]
        return _months_between(selected.start, selected.end)

    if period_type == PERIOD_MONTH:
        return []

    raise ValueError(f"Неизвестный период: {period_type}")


def build_month_period(year: int, month: int, financial: bool = False) -> Period:
    """Возвращает выбранный месяц с учётом финансового года."""
    month = min(max(month, 1), 12)
    actual_year = year if (not financial or month >= 10) else year + 1
    return _month_period(actual_year, month)


class StatisticsService:
    """Выполняет статистические подсчёты по документам."""

    def __init__(self, session: Session, branch_id: Optional[str] = None) -> None:
        self.session = session
        self.branch_id = branch_id

    def calculate(self, query: StatisticsQuery) -> StatisticsResult:
        """Выполняет подсчёт по заданным параметрам."""
        reporting = build_reporting_period(query.year, query.financial)
        columns = build_columns(
            query.period_type,
            reporting,
            half=query.half,
            quarter=query.quarter,
            month=query.month,
        )

        if query.period_type == PERIOD_MONTH:
            selected = build_month_period(query.year, query.month, query.financial)
            columns = [selected]
            search_period = selected
        elif query.period_type == PERIOD_HALF:
            search_period = reporting.halves[min(max(query.half, 1), 2) - 1]
        elif query.period_type == PERIOD_QUARTER:
            search_period = reporting.quarters[min(max(query.quarter, 1), 4) - 1]
        else:
            search_period = Period(reporting.label, reporting.start, reporting.end)

        documents = self._load_documents(query.model_class, search_period)

        counts: Dict[Any, List[int]] = {}
        totals: Dict[Any, int] = {}
        labels: Dict[Any, str] = {}
        order: List[Any] = []

        def register(key: Any, label: str) -> None:
            if key in counts:
                return
            counts[key] = [0] * len(columns)
            totals[key] = 0
            labels[key] = label
            order.append(key)

        if query.criterion == CRITERION_EVALUATION:
            # Регистрируем все значения перечисления, чтобы строки с нулевым
            # количеством тоже попали в отчёт
            for member in EvaluationValue:
                code = pack_enum_display("evaluation_value", int(member))
                register(int(member), enum_label("evaluation_value", code))

        for document in documents:
            document_date = self._document_date(document)
            if document_date is None or not search_period.contains(document_date):
                continue
            for key, label in self._criterion_targets(document, query.criterion):
                register(key, label)
                for index, column in enumerate(columns):
                    if column.contains(document_date):
                        counts[key][index] += 1
                totals[key] += 1

        rows = [
            StatisticsRow(labels[key], list(counts[key]), totals[key])
            for key in order
            if totals[key] > 0 or query.criterion == CRITERION_EVALUATION
        ]
        if query.criterion != CRITERION_EVALUATION:
            rows.sort(key=lambda row: row.label)

        totals_row = [
            sum(row.values[index] for row in rows) for index in range(len(columns))
        ]
        grand_total = sum(row.total for row in rows)
        month_indices = [
            index for index, column in enumerate(columns) if column.label in _MONTH_NAMES
        ]
        month_columns = [columns[index].label for index in month_indices]

        return StatisticsResult(
            title=f"{entity_label(query.model_class, plural=True)}"
            f" — {CRITERION_LABELS.get(query.criterion, query.criterion)}",
            period_label=self._period_label(reporting, search_period),
            columns=[column.label for column in columns],
            rows=rows,
            totals=totals_row,
            grand_total=grand_total,
            month_columns=month_columns,
            month_indices=month_indices,
        )

    def available_period_years(
        self,
        model_class: Type[Base],
        financial: bool = False,
    ) -> List[int]:
        """Возвращает доступные годы на основе записей БД (с учётом филиала)."""
        self.session.expire_all()
        query = self.session.query(model_class)
        if self.branch_id:
            query = query.filter(model_class.branch_id == self.branch_id)

        years = set()
        for document in query.all():
            document_date = self._document_date(document)
            if document_date is None:
                continue
            if financial and document_date.month < 10:
                years.add(document_date.year - 1)
            else:
                years.add(document_date.year)

        if not years:
            return [date.today().year]
        return list(range(min(years), max(years) + 1))

    def _load_documents(self, model_class: Type[Base], period: Period) -> List[Base]:
        """Загружает документы, попадающие в отчётный период."""
        documents = self.session.query(model_class).all()
        result = []
        for document in documents:
            if self.branch_id and getattr(document, "branch_id", None) != self.branch_id:
                continue
            document_date = self._document_date(document)
            if document_date is not None and period.contains(document_date):
                result.append(document)
        return result

    @staticmethod
    def _document_date(document: Base) -> Optional[date]:
        """Возвращает дату документа для отнесения к периоду."""
        return getattr(document, "outgoing_date", None) or getattr(
            document, "incoming_date", None
        )

    def _criterion_targets(self, document: Base, criterion: str) -> List[Tuple[Any, str]]:
        """Возвращает пары (ключ, подпись) для критерия подсчёта."""
        if criterion == CRITERION_EMPLOYEE:
            return [
                (employee.id, employee.display_name())
                for employee in document.employees
            ]

        if criterion == CRITERION_DEPARTMENT:
            return [
                (department.id, department.short_name or department.name)
                for department in document.participating_departments
            ]

        if criterion == CRITERION_WORKGROUP:
            return [
                (workgroup.id, workgroup.name)
                for workgroup in document.participating_workgroups
            ]

        if criterion == CRITERION_CONSUMER:
            consumer = getattr(document, "consumer", None)
            if consumer is None:
                return []
            return [(consumer.id, consumer.short_name or consumer.name)]

        if criterion == CRITERION_TASK:
            return [(task.id, task.name) for task in document.tasks]

        if criterion == CRITERION_SOURCE:
            return [
                (source.id, self._source_label(source))
                for source in document.sources
            ]

        if criterion == CRITERION_EVALUATION:
            evaluation = document.latest_evaluation
            if evaluation is None:
                return []
            code = pack_enum_display("evaluation_value", evaluation.value)
            return [(int(evaluation.value), enum_label("evaluation_value", code))]

        return []

    @staticmethod
    def _source_label(source: Any) -> str:
        """Формирует подпись источника данных."""
        code = pack_enum_display("source_type", source.type)
        label = enum_label("source_type", code)
        if source.comment:
            label = f"{label} ({source.comment})"
        return label

    @staticmethod
    def _period_label(reporting: ReportingPeriod, selected: Period) -> str:
        """Формирует подпись выбранного периода расчёта."""
        if selected.start == reporting.start and selected.end == reporting.end:
            return f"{reporting.label}: {reporting.start:%d.%m.%Y}–{reporting.end:%d.%m.%Y}"
        return (
            f"{reporting.label}, {selected.label}: "
            f"{selected.start:%d.%m.%Y}–{selected.end:%d.%m.%Y}"
        )
