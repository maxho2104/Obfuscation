"""Запись импортированных оценок в предметные таблицы приложения."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional, Tuple

from sqlalchemy import select

from internal_correspondence.core.constants import EvaluationValue
from internal_correspondence.core.domain_pack import enum_codes
from internal_correspondence.orm.models import (
    Evaluation,
    EvaluationList,
    ScientificMaterial,
    Telegram,
    evaluation_material_association,
    evaluation_telegram_association,
)
from internal_correspondence.text_import.models import MatchResult


class EvaluationWriteError(ValueError):
    """Ошибка записи оценки (несовместимые данные или отсутствующий документ)."""


_ENTITY_MODELS = {
    "material": ScientificMaterial,
    "telegram": Telegram,
}


def value_from_code(code: str) -> EvaluationValue:
    codes = list(enum_codes("evaluation_value"))
    try:
        index = codes.index(str(code).strip())
    except ValueError as exc:
        raise EvaluationWriteError(f"unknown evaluation code: {code}") from exc
    try:
        return EvaluationValue(index)
    except ValueError as exc:
        raise EvaluationWriteError(f"evaluation code has no value: {code}") from exc


class EvaluationImportWriter:
    """Создаёт или обновляет оценки в списке, найденном по номеру и дате."""

    def __init__(self, session, doc_no: str, doc_date: date) -> None:
        self.session = session
        self.doc_no = doc_no
        self.doc_date = doc_date
        self._list: Optional[EvaluationList] = None
        self.warnings: list[str] = []

    def _find_list(self) -> Optional[EvaluationList]:
        if self._list is not None:
            return self._list
        statement = (
            select(EvaluationList)
            .where(
                EvaluationList.number == self.doc_no,
                EvaluationList.date == self.doc_date,
            )
            .order_by(EvaluationList.id)
        )
        found = list(self.session.scalars(statement))
        if not found:
            return None
        if len(found) > 1:
            self.warnings.append(
                f"multiple evaluation lists for {self.doc_no} {self.doc_date}: used {found[0].id}"
            )
        self._list = found[0]
        return self._list

    def ensure_list(self) -> EvaluationList:
        found = self._find_list()
        if found is not None:
            return found
        created = EvaluationList(number=self.doc_no, date=self.doc_date)
        self.session.add(created)
        self.session.flush()
        self._list = created
        return created

    def find_existing(self, entity_type: str, entity_id: str) -> Optional[Evaluation]:
        if entity_type not in _ENTITY_MODELS:
            return None
        evaluation_list = self._find_list()
        if evaluation_list is None:
            return None
        entity_uuid = uuid.UUID(str(entity_id))
        if entity_type == "material":
            statement = (
                select(Evaluation)
                .join(
                    evaluation_material_association,
                    Evaluation.id == evaluation_material_association.c.evaluation_id,
                )
                .where(
                    Evaluation.evaluation_list_id == evaluation_list.id,
                    evaluation_material_association.c.material_id == entity_uuid,
                )
            )
        else:
            statement = (
                select(Evaluation)
                .join(
                    evaluation_telegram_association,
                    Evaluation.id == evaluation_telegram_association.c.evaluation_id,
                )
                .where(
                    Evaluation.evaluation_list_id == evaluation_list.id,
                    evaluation_telegram_association.c.telegram_id == entity_uuid,
                )
            )
        return self.session.scalars(statement).first()

    def write(self, match: MatchResult, action: str = "skip") -> Tuple[Optional[Evaluation], bool]:
        """Записывает оценку. Возвращает (оценка, была_ли_обновлена)."""
        if not match.matched or not match.entity_type or not match.entity_id:
            raise EvaluationWriteError("match is not resolved")
        if not match.value_code:
            return None, False
        if match.evaluation_date is None:
            raise EvaluationWriteError("evaluation date is empty")
        model = _ENTITY_MODELS.get(match.entity_type)
        if model is None:
            raise EvaluationWriteError(f"unsupported entity: {match.entity_type}")
        document = self.session.get(model, uuid.UUID(str(match.entity_id)))
        if document is None:
            raise EvaluationWriteError(f"document not found: {match.entity_id}")
        value = value_from_code(match.value_code)
        existing = self.find_existing(match.entity_type, match.entity_id)
        if existing is not None:
            if action != "update":
                return existing, False
            existing.value = value
            existing.date = match.evaluation_date
            self.session.flush()
            return existing, True
        evaluation = Evaluation(
            value=value,
            date=match.evaluation_date,
            evaluation_list_id=self.ensure_list().id,
        )
        document.evaluations.append(evaluation)
        self.session.add(evaluation)
        self.session.flush()
        return evaluation, True
