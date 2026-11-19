"""Статистика документов элемента ОШС для панели сведений.

Считает по документам, в создании которых участвовал элемент (как критерии
статистики: сотрудник — по участию, отдел/группа — по участию отдела/группы,
действовавших на дату документа, филиал — по принадлежности документа).
Документ относится к периоду по дате исходящего (иначе входящего) номера;
оценка документа — последняя выставленная (как в статистике).
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple, Type

from sqlalchemy.orm import Session

from internal_correspondence.core.domain_pack import enum_weight
from internal_correspondence.core.enum_registry import pack_enum_display
from internal_correspondence.orm.models import ScientificMaterial, Telegram
from internal_correspondence.reports.statistics_service import Period


@dataclass(frozen=True)
class ElementPeriodStats:
    """Показатели элемента за период."""

    materials: int = 0
    telegrams: int = 0
    evaluations: int = 0  # количество оцененных документов
    # распределение оценок: код значения перечисления -> количество
    evaluation_counts: Dict[int, int] = field(default_factory=dict)
    # распределение документов по типам: код перечисления -> количество
    material_type_counts: Dict[int, int] = field(default_factory=dict)
    telegram_type_counts: Dict[int, int] = field(default_factory=dict)
    # коэффициент эффективности: средний вес оценок (None — оценок нет)
    avg_weight: Optional[float] = None


# Типы узлов дерева ОШС, для которых считается статистика
NODE_TYPES = ("branch", "department", "workgroup", "employee")


def shift_period_year(period: Period, years: int) -> Period:
    """Возвращает тот же период, смещённый на указанное число лет."""
    try:
        shifted_start = period.start.replace(year=period.start.year + years)
    except ValueError:  # 29 февраля
        shifted_start = period.start.replace(year=period.start.year + years, day=28)
    try:
        shifted_end = period.end.replace(year=period.end.year + years)
    except ValueError:
        shifted_end = period.end.replace(year=period.end.year + years, day=28)
    label = period.label
    if years != 0:
        label = f"{label} {period.start.year + years}"
    return Period(label=label, start=shifted_start, end=shifted_end)


class ElementStatsService:
    """Статистика документов, принадлежащих элементу ОШС."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _document_matches(self, document, node_type: str, node_id: str) -> bool:
        """Проверяет принадлежность документа элементу (как критерии статистики)."""
        if node_type == "branch":
            return getattr(document, "branch_id", None) == node_id
        if node_type == "employee":
            return any(str(emp.id) == node_id for emp in document.employees)
        if node_type == "department":
            return any(
                str(dept.id) == node_id
                for dept in document.participating_departments
            )
        if node_type == "workgroup":
            return any(
                str(group.id) == node_id
                for group in document.participating_workgroups
            )
        return False

    def element_documents(
        self, node_type: str, node_id: str
    ) -> Tuple[List[ScientificMaterial], List[Telegram]]:
        """Возвращает (материалы, телеграммы) элемента без фильтра периода."""
        materials = [
            doc
            for doc in self.session.query(ScientificMaterial).all()
            if self._document_matches(doc, node_type, node_id)
        ]
        telegrams = [
            doc
            for doc in self.session.query(Telegram).all()
            if self._document_matches(doc, node_type, node_id)
        ]
        return materials, telegrams

    @staticmethod
    def _document_date(document) -> Optional[date]:
        """Дата документа для отнесения к периоду."""
        return getattr(document, "outgoing_date", None) or getattr(
            document, "incoming_date", None
        )

    def _collect(
        self, documents, period: Period
    ) -> Tuple[int, Dict[int, int], List[float], Dict[int, int]]:
        """Собирает (количество, оценки по значениям, веса, типы документов)."""
        count = 0
        evaluation_counts: Dict[int, int] = {}
        weights: List[float] = []
        type_counts: Dict[int, int] = {}
        for document in documents:
            document_date = self._document_date(document)
            if document_date is None or not period.contains(document_date):
                continue
            count += 1
            type_value = int(document.type)
            type_counts[type_value] = type_counts.get(type_value, 0) + 1
            evaluation = document.latest_evaluation
            if evaluation is None:
                continue
            value = int(evaluation.value)
            evaluation_counts[value] = evaluation_counts.get(value, 0) + 1
            code = pack_enum_display("evaluation_value", value)
            weight = enum_weight("evaluation_value", code)
            if weight is not None:
                weights.append(float(weight))
        return count, evaluation_counts, weights, type_counts

    def period_stats(
        self, node_type: str, node_id: str, period: Period
    ) -> ElementPeriodStats:
        """Показатели элемента за период: материалы, телеграммы, оценки."""
        materials, telegrams = self.element_documents(node_type, node_id)
        materials_count, mat_counts, mat_weights, mat_types = self._collect(
            materials, period
        )
        telegrams_count, tel_counts, tel_weights, tel_types = self._collect(
            telegrams, period
        )
        evaluation_counts: Dict[int, int] = {}
        for source in (mat_counts, tel_counts):
            for value, count in source.items():
                evaluation_counts[value] = evaluation_counts.get(value, 0) + count
        evaluated = sum(evaluation_counts.values())
        weights = mat_weights + tel_weights
        avg = round(sum(weights) / len(weights), 2) if weights else None
        return ElementPeriodStats(
            materials=materials_count,
            telegrams=telegrams_count,
            evaluations=evaluated,
            evaluation_counts=evaluation_counts,
            material_type_counts=mat_types,
            telegram_type_counts=tel_types,
            avg_weight=avg,
        )
