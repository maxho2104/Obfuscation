"""Сервис ручного выставления и изменения оценок документов.

Правила изменения оценки (план доработки, раздел 3):

- «последняя» оценка документа — по максимальной дате выставления;
  при равенстве дат — оценка с большим значением;
- при смене оценки новая оценка присваивается документу; прежняя
  последняя оценка удаляется, только если она является последней
  исключительно для этого документа (если она привязана к другим
  документам, для которых тоже последняя — остаётся у них);
- документ помечается изменённым штатным механизмом delta-tracking
  (состав связи N-N «оценки» попадает в ``Change.changed_fields``),
  удалённая оценка фиксируется отдельной записью Change об удалении.
"""

import re
from datetime import date
from typing import Optional, Sequence, Union

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import EvaluationValue
from internal_correspondence.orm.models import (
    Evaluation,
    EvaluationList,
    ScientificMaterial,
    Telegram,
)
from internal_correspondence.services.change_tracking import mark_fields_changed

# Формат номера списка оценок: «ОЦ-00001» (годовая последовательность)
_LIST_NUMBER_PATTERN = re.compile(r"^ОЦ-(\d+)$")

Document = Union[ScientificMaterial, Telegram]


class EvaluationError(Exception):
    """Ошибка выставления или изменения оценки."""

    pass


class EvaluationService:
    """Выставление и изменение оценок материалов/телеграмм."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_list(self, number: str, list_date: date) -> EvaluationList:
        """Создаёт новый список оценок с заданными номером и датой."""
        evaluation_list = EvaluationList(number=number, date=list_date)
        self.session.add(evaluation_list)
        self.session.flush()
        return evaluation_list

    def suggest_list_number(self, today: Optional[date] = None) -> str:
        """Предлагает следующий номер списка оценок для года даты.

        Годовая последовательность: среди списков с датой в том же году
        ищется максимальный номер вида «ОЦ-NNNNN», предлагается следующий;
        списков года нет — «ОЦ-00001».
        """
        year = (today or date.today()).year
        maximum = 0
        for evaluation_list in self.session.query(EvaluationList).all():
            if evaluation_list.date is None or evaluation_list.date.year != year:
                continue
            match = _LIST_NUMBER_PATTERN.match(evaluation_list.number or "")
            if match:
                maximum = max(maximum, int(match.group(1)))
        return f"ОЦ-{maximum + 1:05d}"

    def set_evaluation(
        self,
        document: Document,
        value: EvaluationValue,
        assigned_date: date,
        evaluation_list: Optional[EvaluationList] = None,
    ) -> Evaluation:
        """Присваивает одному документу новую оценку (см. ``assign_evaluation``)."""
        return self.assign_evaluation(
            [document], value, assigned_date, evaluation_list
        )

    def assign_evaluation(
        self,
        documents: Sequence[Document],
        value: EvaluationValue,
        assigned_date: date,
        evaluation_list: Optional[EvaluationList] = None,
    ) -> Evaluation:
        """Присваивает совокупности документов одну новую оценку.

        Оценка создаётся одна и связывается со всеми переданными
        документами: в списках каждый документ показывает долю оценки
        (согласно ТЗ, для совокупности перед значением выводится дробное
        число). Для каждого документа прежняя последняя оценка снимается;
        она удаляется, если после снятия остаётся последней только для
        документов вне совокупности (либо не остаётся ни для кого).
        Каждый документ помечается изменённым для экспортной дельты.
        """
        documents = list(documents)
        if not documents:
            raise EvaluationError("Не выбраны документы для оценки.")
        previous_by_id = {
            document.id: document.latest_evaluation for document in documents
        }

        evaluation = Evaluation(
            value=value,
            date=assigned_date,
            evaluation_list=evaluation_list,
        )
        for document in documents:
            if isinstance(document, ScientificMaterial):
                evaluation.materials.append(document)
            else:
                evaluation.telegrams.append(document)
        self.session.add(evaluation)
        self.session.flush()

        # Первый проход: снятие прежних оценок (до проверки
        # «последности» — связанные документы совокупности уже отвязаны).
        for document in documents:
            previous = previous_by_id[document.id]
            if previous is not None and previous is not evaluation:
                if previous in document.evaluations:
                    document.evaluations.remove(previous)

        # Второй проход: удаление оценок, ставших ненужными.
        for document in documents:
            previous = previous_by_id[document.id]
            if previous is not None and previous is not evaluation:
                if self._is_exclusive_last(previous, document):
                    self.session.delete(previous)

        # Документы помечаются изменёнными: владельцем ассоциативной
        # таблицы «оценки-документы» является оценка, поэтому штатный
        # before_flush не фиксирует изменение со стороны документа.
        for document in documents:
            mark_fields_changed(self.session, document, ["evaluations"])
        self.session.flush()
        return evaluation

    def _is_exclusive_last(
        self, evaluation: Evaluation, document: Document
    ) -> bool:
        """Проверяет, что оценка последняя только для данного документа.

        Перебираются остальные документы, связанные с оценкой; если хотя
        бы для одного из них эта оценка — последняя, оценка сохраняется.
        Связь с ``document`` к моменту вызова уже снята.
        """
        others = [
            item
            for item in list(evaluation.materials) + list(evaluation.telegrams)
            if item is not document
        ]
        for other in others:
            if other.latest_evaluation is evaluation:
                return False
        return True
