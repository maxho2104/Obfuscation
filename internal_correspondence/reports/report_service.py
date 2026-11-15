"""Подготовка данных для месячных и полугодовых аналитических отчётов."""

from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Type

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import (
    EvaluationValue,
    MaterialType,
    ReportType,
    ScientificTaskType,
    SourceType,
    TelegramReportType,
    TelegramType,
)
from internal_correspondence.core.domain_pack import enum_label
from internal_correspondence.core.enum_registry import pack_enum_display
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.models import (
    Branch,
    Department,
    ReportDraft,
    ScientificMaterial,
    ScientificTask,
    Telegram,
    WorkingGroup,
)
from internal_correspondence.utils.string_resources import STRINGS


@dataclass(frozen=True)
class ReportRequest:
    """Параметры формирования одного отчёта."""

    report_type: ReportType
    branch_id: str
    year: int
    period_number: int


@dataclass(frozen=True)
class PeriodRange:
    """Замкнутый диапазон дат отчётного периода."""

    start: date
    end: date


@dataclass(frozen=True)
class MetricPair:
    """Значение показателя за текущий и сопоставимый прошлый период."""

    current: int
    previous: int

    @property
    def display(self) -> str:
        """Возвращает компактное представление ``текущее (прошлое)``."""
        return f"{self.current} ({self.previous})"


class ReportDataService:
    """Собирает показатели отчёта и сохраняет его ручные разделы."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def periods(request: ReportRequest) -> tuple[PeriodRange, PeriodRange]:
        """Возвращает выбранный период и такой же период прошлого года."""
        if request.report_type == ReportType.MONTH:
            month = min(max(request.period_number, 1), 12)
            current = PeriodRange(
                date(request.year, month, 1),
                date(request.year, month, calendar.monthrange(request.year, month)[1]),
            )
            previous_year = request.year - 1
            previous = PeriodRange(
                date(previous_year, month, 1),
                date(
                    previous_year,
                    month,
                    calendar.monthrange(previous_year, month)[1],
                ),
            )
            return current, previous

        half = min(max(request.period_number, 1), 2)
        start_month = 1 if half == 1 else 7
        end_month = 6 if half == 1 else 12
        current = PeriodRange(
            date(request.year, start_month, 1),
            date(request.year, end_month, calendar.monthrange(request.year, end_month)[1]),
        )
        previous = PeriodRange(
            date(request.year - 1, start_month, 1),
            date(
                request.year - 1,
                end_month,
                calendar.monthrange(request.year - 1, end_month)[1],
            ),
        )
        return current, previous

    def load_draft(self, request: ReportRequest) -> Optional[ReportDraft]:
        """Загружает сохранённый черновик выбранного отчётного периода."""
        return (
            self.session.query(ReportDraft)
            .filter(
                ReportDraft.branch_id == request.branch_id,
                ReportDraft.report_type == request.report_type,
                ReportDraft.year == request.year,
                ReportDraft.period_number == request.period_number,
            )
            .one_or_none()
        )

    def save_draft(self, request: ReportRequest, values: Dict[str, str]) -> ReportDraft:
        """Создаёт или обновляет ручные текстовые разделы отчёта."""
        draft = self.load_draft(request)
        if draft is None:
            draft = ReportDraft(
                report_type=request.report_type,
                branch_id=request.branch_id,
                year=request.year,
                period_number=request.period_number,
            )
            self.session.add(draft)
        for field_name in (
            "recipient",
            "shortcomings",
            "significant_results",
            "proposals",
            "conclusion",
            "plan_execution",
            "signatory_position",
            "signatory_name",
        ):
            value = (values.get(field_name) or "").strip()
            setattr(draft, field_name, value or None)
        self.session.flush()
        return draft

    def build_context(
        self,
        request: ReportRequest,
        month_names: Sequence[str],
    ) -> Dict[str, Any]:
        """Формирует полный словарь значений для DOCX-шаблона."""
        current_period, previous_period = self.periods(request)
        branch = self.session.get(Branch, request.branch_id)
        if branch is None:
            raise ValueError(
                STRINGS.report_error_branch_not_found.format(
                    branch_id=request.branch_id
                )
            )

        current_materials = self._load_documents(
            ScientificMaterial, request.branch_id, current_period
        )
        previous_materials = self._load_documents(
            ScientificMaterial, request.branch_id, previous_period
        )
        current_telegrams = self._load_documents(
            Telegram, request.branch_id, current_period
        )
        previous_telegrams = self._load_documents(
            Telegram, request.branch_id, previous_period
        )
        draft = self.load_draft(request)

        context: Dict[str, Any] = {
            "report_type": int(request.report_type),
            "year": request.year,
            "previous_year": request.year - 1,
            "period_number": request.period_number,
            "period_start": current_period.start.strftime("%d.%m.%Y"),
            "period_end": current_period.end.strftime("%d.%m.%Y"),
            "branch": {
                "id": branch.id,
                "name": branch.name,
                "short_name": branch.short_name,
                "territorial_unit": branch.territorial_unit.name,
            },
            "materials_total": asdict(
                MetricPair(len(current_materials), len(previous_materials))
            ),
            "telegrams_total": asdict(
                MetricPair(len(current_telegrams), len(previous_telegrams))
            ),
            "materials_change_percent": self._change_percent(
                len(current_materials), len(previous_materials)
            ),
            "telegrams_change_percent": self._change_percent(
                len(current_telegrams), len(previous_telegrams)
            ),
            "material_types": self._enum_rows(
                current_materials,
                previous_materials,
                "type",
                MaterialType,
                "material_type",
            ),
            "telegram_types": self._enum_rows(
                current_telegrams,
                previous_telegrams,
                "type",
                TelegramType,
                "telegram_type",
            ),
            "telegram_report_types": self._enum_rows(
                current_telegrams,
                previous_telegrams,
                "report_type",
                TelegramReportType,
                "telegram_report_type",
            ),
            "task_rows": self._task_rows(
                current_materials, previous_materials, current_period
            ),
            "evaluation_rows": self._evaluation_rows(
                current_materials, previous_materials
            ),
            "evaluated_materials": asdict(
                MetricPair(
                    self._evaluated_count(current_materials),
                    self._evaluated_count(previous_materials),
                )
            ),
            "evaluated_main_materials": asdict(
                MetricPair(
                    self._evaluated_main_count(current_materials),
                    self._evaluated_main_count(previous_materials),
                )
            ),
            "reported_telegrams": asdict(
                MetricPair(
                    self._reported_count(current_telegrams),
                    self._reported_count(previous_telegrams),
                )
            ),
            "reported_percent": self._percent(
                self._reported_count(current_telegrams), len(current_telegrams)
            ),
            "telegram_details": self._telegram_details(current_telegrams),
            "material_cost": {
                "current": self._total_cost(current_materials),
                "previous": self._total_cost(previous_materials),
            },
            "draft": self._draft_values(draft),
        }

        if request.report_type == ReportType.MONTH:
            names = list(month_names)
            if len(names) != 12:
                raise ValueError(STRINGS.report_error_month_names)
            context["period_label"] = f"{names[request.period_number - 1]} {request.year}"
            context["month_name"] = names[request.period_number - 1].lower()
            context["previous_period_label"] = (
                f"{names[request.period_number - 1]} {request.year - 1}"
            )
            context["monthly"] = self._monthly_template_context(
                current_materials,
                previous_materials,
                current_telegrams,
                previous_telegrams,
            )
            return context

        half_label = ("I", "II")[request.period_number - 1]
        context["period_label"] = f"{half_label} полугодие {request.year}"
        context["previous_period_label"] = (
            f"{half_label} полугодие {request.year - 1}"
        )
        context.update(
            self._half_year_context(
                branch,
                current_materials,
                previous_materials,
                current_telegrams,
                previous_telegrams,
            )
        )
        context["halfyear"] = self._halfyear_template_context(
            branch,
            current_materials,
            previous_materials,
            current_telegrams,
            previous_telegrams,
        )
        return context

    def _monthly_template_context(
        self,
        current_materials: Sequence[ScientificMaterial],
        previous_materials: Sequence[ScientificMaterial],
        current_telegrams: Sequence[Telegram],
        previous_telegrams: Sequence[Telegram],
    ) -> Dict[str, Any]:
        """Готовит показатели в порядке и формулировках месячного образца."""
        current_main = self._main_task_documents(current_materials)
        previous_main = self._main_task_documents(previous_materials)
        current_technical = [
            item
            for item in current_materials
            if item.type == MaterialType.TECHNICAL_DOCUMENT
        ]
        previous_technical = [
            item
            for item in previous_materials
            if item.type == MaterialType.TECHNICAL_DOCUMENT
        ]
        current_product_and_technical = [
            item
            for item in current_materials
            if item.type
            in (MaterialType.PRODUCT_SAMPLE, MaterialType.TECHNICAL_DOCUMENT)
        ]
        previous_product_and_technical = [
            item
            for item in previous_materials
            if item.type
            in (MaterialType.PRODUCT_SAMPLE, MaterialType.TECHNICAL_DOCUMENT)
        ]
        current_experimental = [
            item
            for item in current_materials
            if any(source.type == SourceType.EXPERIMENTAL_EQUIPMENT for source in item.sources)
        ]
        previous_experimental = [
            item
            for item in previous_materials
            if any(source.type == SourceType.EXPERIMENTAL_EQUIPMENT for source in item.sources)
        ]
        current_evaluated = self._evaluated_count(current_materials)
        previous_evaluated = self._evaluated_count(previous_materials)
        current_reported = self._reported_count(current_telegrams)
        previous_reported = self._reported_count(previous_telegrams)
        return {
            "main_materials": asdict(
                MetricPair(len(current_main), len(previous_main))
            ),
            "other_materials": asdict(
                MetricPair(
                    len(current_materials) - len(current_main),
                    len(previous_materials) - len(previous_main),
                )
            ),
            "technical_documents": asdict(
                MetricPair(len(current_technical), len(previous_technical))
            ),
            "evaluation_rows": self._evaluation_detail_rows(
                current_materials, previous_materials
            ),
            "telegram_report_rows": self._telegram_report_detail_rows(
                current_telegrams, previous_telegrams
            ),
            "materials_trend": self._change_description(
                len(current_materials), len(previous_materials)
            ),
            "technical_products_trend": self._change_description(
                len(current_product_and_technical),
                len(previous_product_and_technical),
            ),
            "main_materials_trend": self._change_description(
                len(current_main), len(previous_main)
            ),
            "experimental_difference": (
                len(current_experimental) - len(previous_experimental)
            ),
            "evaluations_trend": self._change_description(
                current_evaluated, previous_evaluated
            ),
            "telegrams_trend": self._change_description(
                len(current_telegrams), len(previous_telegrams)
            ),
            "reported_trend": self._change_description(
                current_reported, previous_reported
            ),
            "reported_percent_previous": self._percent(
                previous_reported, len(previous_telegrams)
            ),
        }

    def _halfyear_template_context(
        self,
        branch: Branch,
        current_materials: Sequence[ScientificMaterial],
        previous_materials: Sequence[ScientificMaterial],
        current_telegrams: Sequence[Telegram],
        previous_telegrams: Sequence[Telegram],
    ) -> Dict[str, Any]:
        """Готовит строки и итоги трёх таблиц полугодового образца."""
        departments = sorted(
            branch.departments,
            key=lambda item: (item.short_name or item.name).lower(),
        )
        telegram_rows = self._halfyear_telegram_table_rows(
            departments, current_telegrams, previous_telegrams
        )
        material_rows = self._department_material_rows(
            departments, current_materials, previous_materials
        )
        evaluation_rows = self._department_evaluation_rows(
            departments, current_materials, previous_materials
        )
        thematic_current = [
            item for item in current_telegrams if item.type == TelegramType.THEMATIC
        ]
        thematic_previous = [
            item for item in previous_telegrams if item.type == TelegramType.THEMATIC
        ]
        results_current = [
            item
            for item in current_telegrams
            if item.type == TelegramType.RESULTS_REPORT
        ]
        results_previous = [
            item
            for item in previous_telegrams
            if item.type == TelegramType.RESULTS_REPORT
        ]
        current_reported = self._reported_count(current_telegrams)
        previous_reported = self._reported_count(previous_telegrams)
        current_thematic_reported = self._reported_count(thematic_current)
        previous_thematic_reported = self._reported_count(thematic_previous)
        department_thematic_rows = self._percentage_unit_rows(
            departments, thematic_current, thematic_previous
        )
        workgroups = [
            group for department in departments for group in department.workgroups
        ]
        workgroup_thematic_rows = self._percentage_unit_rows(
            workgroups, thematic_current, thematic_previous
        )
        material_rank = self._rank_rows(
            departments, current_materials, "participating_departments"
        )
        workgroup_rank = self._rank_rows(
            workgroups, current_telegrams, "participating_workgroups"
        )[:5]
        material_rank = material_rank[:3]
        return {
            "telegrams_trend": self._change_description(
                len(current_telegrams), len(previous_telegrams)
            ),
            "reported_percent_previous": self._percent(
                previous_reported, len(previous_telegrams)
            ),
            "telegram_table_rows": telegram_rows,
            "telegram_table_total": self._telegram_table_total(
                current_telegrams, previous_telegrams
            ),
            "department_report_rows": self._percentage_unit_rows(
                departments, current_telegrams, previous_telegrams
            ),
            "thematic": asdict(
                MetricPair(len(thematic_current), len(thematic_previous))
            ),
            "thematic_urgent": asdict(
                MetricPair(
                    self._report_type_count(
                        thematic_current, TelegramReportType.URGENTLY_REPORTED
                    ),
                    self._report_type_count(
                        thematic_previous, TelegramReportType.URGENTLY_REPORTED
                    ),
                )
            ),
            "thematic_reported": asdict(
                MetricPair(
                    self._report_type_count(
                        thematic_current, TelegramReportType.REPORTED
                    ),
                    self._report_type_count(
                        thematic_previous, TelegramReportType.REPORTED
                    ),
                )
            ),
            "thematic_percent": self._percent(
                current_thematic_reported, len(thematic_current)
            ),
            "thematic_percent_previous": self._percent(
                previous_thematic_reported, len(thematic_previous)
            ),
            "department_thematic_rows": department_thematic_rows,
            "workgroup_thematic_text": self._percentage_rows_text(
                workgroup_thematic_rows
            ),
            "results_telegrams": asdict(
                MetricPair(len(results_current), len(results_previous))
            ),
            "workgroup_ranking_rows": workgroup_rank,
            "department_ranking_rows": material_rank,
            "telegram_details": self._telegram_details(current_telegrams)[:12],
            "material_table_rows": material_rows,
            "material_table_total": self._material_table_total(
                current_materials, previous_materials
            ),
            "evaluation_table_rows": evaluation_rows,
            "evaluation_table_total": self._evaluation_table_total(
                current_materials, previous_materials
            ),
            "materials_trend": self._change_description(
                len(current_materials), len(previous_materials)
            ),
            "message_materials": asdict(
                MetricPair(
                    sum(
                        1
                        for item in current_materials
                        if item.type == MaterialType.MESSAGE
                    ),
                    sum(
                        1
                        for item in previous_materials
                        if item.type == MaterialType.MESSAGE
                    ),
                )
            ),
            "top_material_departments": ", ".join(
                row["label"] for row in material_rank[:2]
            )
            or "—",
            "evaluations_trend": self._change_description(
                self._evaluated_count(current_materials),
                self._evaluated_count(previous_materials),
            ),
        }

    @staticmethod
    def _main_task_documents(
        documents: Sequence[ScientificMaterial],
    ) -> List[ScientificMaterial]:
        return [
            item
            for item in documents
            if any(task.type == ScientificTaskType.MAIN for task in item.tasks)
        ]

    @staticmethod
    def _change_description(current: int, previous: int) -> str:
        """Возвращает словесное изменение в стиле исходных отчётов."""
        if current == previous:
            return "сохранении на прежнем уровне"
        if previous == 0:
            return f"увеличении с 0 до {current}"
        if current == 0:
            return "снижении до 0"
        if current > previous:
            ratio = current / previous
            percent = (current - previous) / previous * 100
            direction = "увеличении"
        else:
            ratio = previous / current
            percent = (previous - current) / previous * 100
            direction = "снижении"
        ratio_text = f"{ratio:.1f}".replace(".", ",")
        percent_text = f"{percent:.1f}".replace(".", ",")
        return f"{direction} в {ratio_text} раза (или на {percent_text}%)"

    def _evaluation_detail_rows(
        self,
        current: Sequence[ScientificMaterial],
        previous: Sequence[ScientificMaterial],
    ) -> List[Dict[str, Any]]:
        rows = []
        for value in (
            EvaluationValue.IMPORTANT,
            EvaluationValue.USEFUL,
            EvaluationValue.INTERESTING,
        ):
            current_docs = [
                item
                for item in current
                if item.latest_evaluation is not None
                and item.latest_evaluation.value == value
            ]
            previous_docs = [
                item
                for item in previous
                if item.latest_evaluation is not None
                and item.latest_evaluation.value == value
            ]
            current_main = self._main_task_documents(current_docs)
            previous_main = self._main_task_documents(previous_docs)
            code = pack_enum_display("evaluation_value", value)
            details = []
            for item in current_docs:
                task_codes = ", ".join(
                    task.id
                    for task in item.tasks
                    if task.type == ScientificTaskType.MAIN
                )
                number = item.outgoing_number or item.incoming_number or "—"
                details.append(
                    f"{number} ({task_codes})" if task_codes else number
                )
            rows.append(
                {
                    "label": enum_label("evaluation_value", code).lower(),
                    "current": len(current_docs),
                    "previous": len(previous_docs),
                    "main_current": len(current_main),
                    "main_previous": len(previous_main),
                    "details": "; ".join(details) or "нет",
                }
            )
        return rows

    def _telegram_report_detail_rows(
        self,
        current: Sequence[Telegram],
        previous: Sequence[Telegram],
    ) -> List[Dict[str, Any]]:
        rows = []
        for value in (
            TelegramReportType.URGENTLY_REPORTED,
            TelegramReportType.REPORTED,
        ):
            current_docs = [item for item in current if item.report_type == value]
            previous_docs = [item for item in previous if item.report_type == value]
            code = pack_enum_display("telegram_report_type", value)
            details = []
            for item in sorted(
                current_docs,
                key=lambda obj: (
                    obj.outgoing_date or obj.incoming_date or date.min,
                    obj.outgoing_number or obj.incoming_number or "",
                ),
            ):
                number = item.outgoing_number or item.incoming_number or "—"
                document_date = item.outgoing_date or item.incoming_date
                date_text = document_date.strftime("%d.%m.%y") if document_date else "—"
                leaders = ", ".join(
                    sorted({address.leader_id for address in item.report_addresses})
                )
                detail = f"{number} от {date_text} г."
                if leaders:
                    detail += f" (доложено: {leaders})"
                details.append(detail)
            rows.append(
                {
                    "label": enum_label("telegram_report_type", code).lower(),
                    "current": len(current_docs),
                    "previous": len(previous_docs),
                    "details": "; ".join(details) or "нет",
                }
            )
        return rows

    def _halfyear_telegram_table_rows(
        self,
        departments: Sequence[Department],
        current: Sequence[Telegram],
        previous: Sequence[Telegram],
    ) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for department in departments:
            department_current = self._unit_documents(current, department)
            department_previous = self._unit_documents(previous, department)
            department_values = self._telegram_report_metrics(
                department_current, department_previous
            )
            groups = sorted(department.workgroups, key=lambda item: item.name.lower())
            if not groups:
                groups = [None]
            for group in groups:
                if group is None:
                    group_values = {
                        "urgent": "—",
                        "reported": "—",
                        "total": "—",
                    }
                    group_label = "—"
                else:
                    group_values = self._telegram_report_metrics(
                        self._unit_documents(current, group),
                        self._unit_documents(previous, group),
                    )
                    group_label = group.name
                rows.append(
                    {
                        "department": department.short_name or department.name,
                        "workgroup": group_label,
                        "group_urgent": group_values["urgent"],
                        "department_urgent": department_values["urgent"],
                        "group_reported": group_values["reported"],
                        "department_reported": department_values["reported"],
                        "group_total": group_values["total"],
                        "department_total": department_values["total"],
                    }
                )
        return rows

    def _telegram_table_total(
        self,
        current: Sequence[Telegram],
        previous: Sequence[Telegram],
    ) -> Dict[str, str]:
        values = self._telegram_report_metrics(current, previous)
        return {
            "urgent": values["urgent"],
            "reported": values["reported"],
            "total": values["total"],
        }

    @staticmethod
    def _telegram_report_metrics(
        current: Sequence[Telegram],
        previous: Sequence[Telegram],
    ) -> Dict[str, str]:
        current_urgent = ReportDataService._report_type_count(
            current, TelegramReportType.URGENTLY_REPORTED
        )
        previous_urgent = ReportDataService._report_type_count(
            previous, TelegramReportType.URGENTLY_REPORTED
        )
        current_reported = ReportDataService._report_type_count(
            current, TelegramReportType.REPORTED
        )
        previous_reported = ReportDataService._report_type_count(
            previous, TelegramReportType.REPORTED
        )
        return {
            "urgent": MetricPair(current_urgent, previous_urgent).display,
            "reported": MetricPair(current_reported, previous_reported).display,
            "total": MetricPair(
                current_urgent + current_reported,
                previous_urgent + previous_reported,
            ).display,
        }

    @staticmethod
    def _report_type_count(
        documents: Sequence[Telegram], value: TelegramReportType
    ) -> int:
        return sum(1 for item in documents if item.report_type == value)

    def _percentage_unit_rows(
        self,
        units: Sequence[Any],
        current: Sequence[Telegram],
        previous: Sequence[Telegram],
    ) -> List[Dict[str, str]]:
        rows = []
        for unit in units:
            current_docs = self._unit_documents(current, unit)
            previous_docs = self._unit_documents(previous, unit)
            current_reported = self._reported_count(current_docs)
            previous_reported = self._reported_count(previous_docs)
            rows.append(
                {
                    "label": getattr(unit, "short_name", None) or unit.name,
                    "current": current_reported,
                    "previous": previous_reported,
                    "percent": self._percent(current_reported, len(current_docs)),
                    "percent_previous": self._percent(
                        previous_reported, len(previous_docs)
                    ),
                }
            )
        return rows

    @staticmethod
    def _percentage_rows_text(rows: Sequence[Dict[str, str]]) -> str:
        return ", ".join(
            f"«{row['label']}» — {row['percent']}% ({row['percent_previous']}%)"
            for row in rows
        ) or "—"

    @staticmethod
    def _rank_rows(
        units: Sequence[Any], documents: Sequence[Any], relationship: str
    ) -> List[Dict[str, Any]]:
        roman = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII")
        ranked = sorted(
            (
                {
                    "label": getattr(unit, "short_name", None) or unit.name,
                    "count": sum(
                        1
                        for document in documents
                        if unit in getattr(document, relationship)
                    ),
                }
                for unit in units
            ),
            key=lambda row: (-row["count"], row["label"].lower()),
        )
        for index, row in enumerate(ranked):
            row["place"] = roman[index] if index < len(roman) else str(index + 1)
        return ranked

    @staticmethod
    def _material_table_total(
        current: Sequence[ScientificMaterial],
        previous: Sequence[ScientificMaterial],
    ) -> Dict[str, Any]:
        values = [
            MetricPair(
                sum(1 for item in current if item.type == material_type),
                sum(1 for item in previous if item.type == material_type),
            ).display
            for material_type in MaterialType
        ]
        return {
            "type_values": values,
            "total": MetricPair(len(current), len(previous)).display,
        }

    def _evaluation_table_total(
        self,
        current: Sequence[ScientificMaterial],
        previous: Sequence[ScientificMaterial],
    ) -> Dict[str, Any]:
        return {
            "categories": self._evaluation_table_categories(current, previous)
        }

    def _evaluation_table_categories(
        self,
        current: Sequence[ScientificMaterial],
        previous: Sequence[ScientificMaterial],
    ) -> List[Dict[str, str]]:
        categories = []
        for value in (
            EvaluationValue.IMPORTANT,
            EvaluationValue.USEFUL,
            EvaluationValue.INTERESTING,
        ):
            current_docs = [
                item
                for item in current
                if item.latest_evaluation is not None
                and item.latest_evaluation.value == value
            ]
            previous_docs = [
                item
                for item in previous
                if item.latest_evaluation is not None
                and item.latest_evaluation.value == value
            ]
            categories.append(
                {
                    "current": (
                        f"{len(current_docs)} "
                        f"({len(self._main_task_documents(current_docs))})"
                    ),
                    "previous": (
                        f"{len(previous_docs)} "
                        f"({len(self._main_task_documents(previous_docs))})"
                    ),
                }
            )
        return categories

    def _half_year_context(
        self,
        branch: Branch,
        current_materials: Sequence[ScientificMaterial],
        previous_materials: Sequence[ScientificMaterial],
        current_telegrams: Sequence[Telegram],
        previous_telegrams: Sequence[Telegram],
    ) -> Dict[str, Any]:
        """Готовит таблицы, специфичные для полугодового отчёта."""
        departments = sorted(
            branch.departments,
            key=lambda item: (item.short_name or item.name).lower(),
        )
        workgroups = sorted(
            [group for department in departments for group in department.workgroups],
            key=lambda item: item.name.lower(),
        )
        material_headers = [
            {
                "code": pack_enum_display("material_type", value),
                "label": enum_label(
                    "material_type", pack_enum_display("material_type", value)
                ),
            }
            for value in MaterialType
        ]
        return {
            "department_telegram_rows": self._reporting_unit_rows(
                departments, current_telegrams, previous_telegrams
            ),
            "workgroup_telegram_rows": self._reporting_unit_rows(
                workgroups, current_telegrams, previous_telegrams
            ),
            "material_type_headers": material_headers,
            "department_material_rows": self._department_material_rows(
                departments, current_materials, previous_materials
            ),
            "department_evaluation_rows": self._department_evaluation_rows(
                departments, current_materials, previous_materials
            ),
            "department_ranking": self._ranking(
                departments, current_materials, "participating_departments"
            ),
            "workgroup_ranking": self._ranking(
                workgroups, current_telegrams, "participating_workgroups"
            ),
        }

    def _load_documents(
        self,
        model_class: Type[Base],
        branch_id: str,
        period: PeriodRange,
    ) -> List[Any]:
        """Загружает документы филиала, относящиеся к указанному периоду."""
        return (
            self.session.query(model_class)
            .filter(model_class.branch_id == branch_id)
            .filter(
                or_(
                    and_(
                        model_class.outgoing_date.is_not(None),
                        model_class.outgoing_date >= period.start,
                        model_class.outgoing_date <= period.end,
                    ),
                    and_(
                        model_class.outgoing_date.is_(None),
                        model_class.incoming_date >= period.start,
                        model_class.incoming_date <= period.end,
                    ),
                )
            )
            .all()
        )

    @staticmethod
    def _enum_rows(
        current_documents: Sequence[Any],
        previous_documents: Sequence[Any],
        attribute: str,
        enum_class: Iterable[Any],
        enum_name: str,
    ) -> List[Dict[str, Any]]:
        """Считает документы по значениям пакетного перечисления."""
        rows = []
        for value in enum_class:
            code = pack_enum_display(enum_name, value)
            current = sum(
                1 for document in current_documents if getattr(document, attribute) == value
            )
            previous = sum(
                1 for document in previous_documents if getattr(document, attribute) == value
            )
            rows.append(
                {
                    "key": value.name.lower(),
                    "code": code,
                    "label": enum_label(enum_name, code),
                    "current": current,
                    "previous": previous,
                    "display": MetricPair(current, previous).display,
                }
            )
        return rows

    def _task_rows(
        self,
        current_materials: Sequence[ScientificMaterial],
        previous_materials: Sequence[ScientificMaterial],
        period: PeriodRange,
    ) -> List[Dict[str, Any]]:
        """Считает материалы по действовавшим основным научным задачам."""
        active_tasks = (
            self.session.query(ScientificTask)
            .filter(ScientificTask.type == ScientificTaskType.MAIN)
            .filter(ScientificTask.start_date <= period.end)
            .filter(
                or_(ScientificTask.end_date.is_(None), ScientificTask.end_date >= period.start)
            )
            .order_by(ScientificTask.id)
            .all()
        )
        tasks_by_id = {task.id: task for task in active_tasks}
        for document in (*current_materials, *previous_materials):
            for task in document.tasks:
                if task.type == ScientificTaskType.MAIN:
                    tasks_by_id[task.id] = task

        rows = []
        for task in sorted(tasks_by_id.values(), key=lambda item: item.id):
            current = sum(1 for document in current_materials if task in document.tasks)
            previous = sum(1 for document in previous_materials if task in document.tasks)
            rows.append(
                {
                    "code": task.id,
                    "label": task.name,
                    "current": current,
                    "previous": previous,
                    "display": MetricPair(current, previous).display,
                }
            )
        return rows

    @staticmethod
    def _evaluation_rows(
        current_materials: Sequence[ScientificMaterial],
        previous_materials: Sequence[ScientificMaterial],
    ) -> List[Dict[str, Any]]:
        """Считает последние оценки материалов по категориям."""
        rows = []
        for value in EvaluationValue:
            code = pack_enum_display("evaluation_value", value)
            current = sum(
                1
                for document in current_materials
                if document.latest_evaluation is not None
                and document.latest_evaluation.value == value
            )
            previous = sum(
                1
                for document in previous_materials
                if document.latest_evaluation is not None
                and document.latest_evaluation.value == value
            )
            rows.append(
                {
                    "key": value.name.lower(),
                    "code": code,
                    "label": enum_label("evaluation_value", code),
                    "current": current,
                    "previous": previous,
                    "display": MetricPair(current, previous).display,
                }
            )
        return rows

    @staticmethod
    def _evaluated_count(documents: Sequence[ScientificMaterial]) -> int:
        return sum(1 for document in documents if document.latest_evaluation is not None)

    @staticmethod
    def _evaluated_main_count(documents: Sequence[ScientificMaterial]) -> int:
        return sum(
            1
            for document in documents
            if document.latest_evaluation is not None
            and any(task.type == ScientificTaskType.MAIN for task in document.tasks)
        )

    @staticmethod
    def _reported_count(documents: Sequence[Telegram]) -> int:
        return sum(1 for document in documents if document.report_type is not None)

    @staticmethod
    def _telegram_details(documents: Sequence[Telegram]) -> List[Dict[str, str]]:
        """Формирует перечень доложенных телеграмм и адресатов."""
        details = []
        for telegram in sorted(
            (item for item in documents if item.report_type is not None),
            key=lambda item: (item.outgoing_date or item.incoming_date or date.min, item.outgoing_number or ""),
        ):
            code = pack_enum_display("telegram_report_type", telegram.report_type)
            addresses = ", ".join(
                sorted(
                    {
                        address.leader_id
                        + (
                            f" ({address.report_date:%d.%m.%Y})"
                            if address.report_date
                            else ""
                        )
                        for address in telegram.report_addresses
                    }
                )
            )
            details.append(
                {
                    "number": telegram.outgoing_number or telegram.incoming_number or "—",
                    "date": (
                        telegram.outgoing_date or telegram.incoming_date
                    ).strftime("%d.%m.%Y")
                    if (telegram.outgoing_date or telegram.incoming_date)
                    else "—",
                    "report_type": enum_label("telegram_report_type", code),
                    "leaders": addresses or "—",
                }
            )
        return details

    @staticmethod
    def _total_cost(documents: Sequence[ScientificMaterial]) -> str:
        total = sum((Decimal(document.cost or 0) for document in documents), Decimal(0))
        return f"{total:,.2f}".replace(",", " ").replace(".", ",")

    @staticmethod
    def _unit_documents(documents: Sequence[Any], unit: Any) -> List[Any]:
        relationship = (
            "participating_departments"
            if isinstance(unit, Department)
            else "participating_workgroups"
        )
        return [document for document in documents if unit in getattr(document, relationship)]

    def _reporting_unit_rows(
        self,
        units: Sequence[Any],
        current: Sequence[Telegram],
        previous: Sequence[Telegram],
    ) -> List[Dict[str, Any]]:
        rows = []
        for unit in units:
            current_docs = self._unit_documents(current, unit)
            previous_docs = self._unit_documents(previous, unit)
            current_urgent = sum(
                1
                for document in current_docs
                if document.report_type == TelegramReportType.URGENTLY_REPORTED
            )
            previous_urgent = sum(
                1
                for document in previous_docs
                if document.report_type == TelegramReportType.URGENTLY_REPORTED
            )
            current_reported = sum(
                1
                for document in current_docs
                if document.report_type == TelegramReportType.REPORTED
            )
            previous_reported = sum(
                1
                for document in previous_docs
                if document.report_type == TelegramReportType.REPORTED
            )
            rows.append(
                {
                    "label": getattr(unit, "short_name", None) or unit.name,
                    "urgent": MetricPair(current_urgent, previous_urgent).display,
                    "reported": MetricPair(current_reported, previous_reported).display,
                    "total": MetricPair(len(current_docs), len(previous_docs)).display,
                    "percent": self._percent(
                        current_urgent + current_reported, len(current_docs)
                    ),
                }
            )
        return rows

    def _department_material_rows(
        self,
        departments: Sequence[Department],
        current: Sequence[ScientificMaterial],
        previous: Sequence[ScientificMaterial],
    ) -> List[Dict[str, Any]]:
        rows = []
        for department in departments:
            current_docs = self._unit_documents(current, department)
            previous_docs = self._unit_documents(previous, department)
            values = []
            for material_type in MaterialType:
                values.append(
                    MetricPair(
                        sum(1 for document in current_docs if document.type == material_type),
                        sum(1 for document in previous_docs if document.type == material_type),
                    ).display
                )
            rows.append(
                {
                    "label": department.short_name or department.name,
                    "type_values": values,
                    "total": MetricPair(len(current_docs), len(previous_docs)).display,
                }
            )
        return rows

    def _department_evaluation_rows(
        self,
        departments: Sequence[Department],
        current: Sequence[ScientificMaterial],
        previous: Sequence[ScientificMaterial],
    ) -> List[Dict[str, Any]]:
        rows = []
        values = (
            EvaluationValue.IMPORTANT,
            EvaluationValue.USEFUL,
            EvaluationValue.INTERESTING,
        )
        for department in departments:
            current_docs = self._unit_documents(current, department)
            previous_docs = self._unit_documents(previous, department)
            categories = []
            for value in values:
                current_value = [
                    document
                    for document in current_docs
                    if document.latest_evaluation is not None
                    and document.latest_evaluation.value == value
                ]
                previous_value = [
                    document
                    for document in previous_docs
                    if document.latest_evaluation is not None
                    and document.latest_evaluation.value == value
                ]
                current_main = sum(
                    1
                    for document in current_value
                    if any(
                        task.type == ScientificTaskType.MAIN
                        for task in document.tasks
                    )
                )
                previous_main = sum(
                    1
                    for document in previous_value
                    if any(
                        task.type == ScientificTaskType.MAIN
                        for task in document.tasks
                    )
                )
                categories.append(
                    {
                        "current": f"{len(current_value)} ({current_main})",
                        "previous": f"{len(previous_value)} ({previous_main})",
                        "total": MetricPair(
                            len(current_value), len(previous_value)
                        ).display,
                        "main": MetricPair(
                            current_main,
                            previous_main,
                        ).display,
                    }
                )
            rows.append(
                {
                    "label": department.short_name or department.name,
                    "categories": categories,
                }
            )
        return rows

    @staticmethod
    def _ranking(
        units: Sequence[Any],
        documents: Sequence[Any],
        relationship: str,
    ) -> str:
        ranked = sorted(
            (
                (
                    sum(1 for document in documents if unit in getattr(document, relationship)),
                    getattr(unit, "short_name", None) or unit.name,
                )
                for unit in units
            ),
            key=lambda item: (-item[0], item[1].lower()),
        )
        return "; ".join(f"{label} — {count}" for count, label in ranked) or "—"

    @staticmethod
    def _draft_values(draft: Optional[ReportDraft]) -> Dict[str, str]:
        fields = (
            "recipient",
            "shortcomings",
            "significant_results",
            "proposals",
            "conclusion",
            "plan_execution",
            "signatory_position",
            "signatory_name",
        )
        return {
            field_name: (getattr(draft, field_name, None) or "")
            for field_name in fields
        }

    @staticmethod
    def _percent(value: int, total: int) -> str:
        if total <= 0:
            return "0,0"
        return f"{value * 100 / total:.1f}".replace(".", ",")

    @staticmethod
    def _change_percent(current: int, previous: int) -> str:
        if previous <= 0:
            return "—" if current else "0,0"
        return f"{(current - previous) * 100 / previous:.1f}".replace(".", ",")
