"""Определение филиала-получателя изменения (атрибуция Change → Branch).

Головной офис формирует отдельный экспортный архив для каждого филиала.
Запись ``Change`` не хранит филиал, поэтому он вычисляется по связанной
сущности:

- материал/телеграмма → свой ``branch_id``;
- отдел/рабочая группа/сотрудник/участие в группе → через отдел → филиал;
- оценка, адресация доклада, файл, список оценок → через связанные
  документы (материалы/телеграммы); сущность может быть связана с
  документами разных филиалов — тогда изменение попадает в архив каждого;
- источник → через документы, в которых он используется; если таких
  нет (сирота) — не попадает ни в один архив и остаётся
  неэкспортированным;
- справочные сущности (территориальные единицы, филиалы, страны, звания,
  потребители, руководители, научные задачи и назначения) → ``None``
  (пометка «справочник»: полный набор изменений кладётся в каждый архив).
"""

from typing import Optional, Set

from sqlalchemy.orm import Session

from internal_correspondence.orm.models import (
    Change,
    Department,
    Employee,
    Evaluation,
    EvaluationList,
    FileRecord,
    ReportAddress,
    ScientificMaterial,
    Source,
    Telegram,
    WorkGroupMembership,
    WorkingGroup,
)
from internal_correspondence.orm.utils import parse_primary_key, resolve_entity_class

# Сущности-справочники: их изменения рассылаются всем филиалам.
REFERENCE_ENTITIES = {
    "TerritorialUnit",
    "Branch",
    "Country",
    "AcademicTitle",
    "Consumer",
    "Leader",
    "ScientificTask",
    "AddedTask",
}

# Документы: напрямую несут branch_id.
_DOCUMENT_ENTITIES = {"ScientificMaterial", "Telegram"}


def _load(session: Session, entity_name: str, entity_pk: str):
    """Возвращает экземпляр сущности по имени и строковому PK (None — не найден)."""
    entity_class = resolve_entity_class(entity_name)
    if entity_class is None:
        return None
    try:
        pk = parse_primary_key(entity_pk, entity_class)
    except (TypeError, ValueError):
        return None
    return session.get(entity_class, pk)


def _document_branches(documents) -> Set[str]:
    """Возвращает множество филиалов документов (по их branch_id)."""
    return {document.branch_id for document in documents if document is not None}


def branches_for_instance(session: Session, instance) -> Set[str]:
    """Возвращает филиалы, связанные с экземпляром сущности.

    Пустое множество — филиал определить нельзя (сирота).
    """
    if instance is None:
        return set()
    if isinstance(instance, (ScientificMaterial, Telegram)):
        return {instance.branch_id}
    if isinstance(instance, Department):
        return {instance.branch_id}
    if isinstance(instance, (WorkingGroup, Employee)):
        return {instance.department.branch_id}
    if isinstance(instance, WorkGroupMembership):
        employee = instance.employee
        return {employee.department.branch_id} if employee is not None else set()
    if isinstance(instance, (Evaluation, FileRecord)):
        return _document_branches(
            list(instance.materials) + list(instance.telegrams)
        )
    if isinstance(instance, ReportAddress):
        telegram = instance.telegram
        return {telegram.branch_id} if telegram is not None else set()
    if isinstance(instance, EvaluationList):
        branches: Set[str] = set()
        for evaluation in instance.evaluations:
            branches.update(
                _document_branches(
                    list(evaluation.materials) + list(evaluation.telegrams)
                )
            )
        return branches
    if isinstance(instance, Source):
        return _document_branches(
            list(instance.materials) + list(instance.telegrams)
        )
    return set()


def branches_for_change(session: Session, change: Change) -> Optional[Set[str]]:
    """Возвращает филиалы-получатели изменения.

    Returns:
        ``None`` — справочная сущность (изменение кладётся в каждый архив);
        пустое множество — филиал не определяется (в архивы не попадает);
        непустое множество — конкретные филиалы.
    """
    if change.entity_name in REFERENCE_ENTITIES:
        return None
    instance = _load(session, change.entity_name, change.entity_pk)
    if instance is not None:
        return branches_for_instance(session, instance)
    # Экземпляр удалён или отсутствует: атрибуция по типу сущности.
    if change.entity_name in _DOCUMENT_ENTITIES:
        # Материал/телеграмма удалены — без экземпляра филиал не узнать:
        # изменение остаётся неэкспортированным (уйдёт в запрос missing).
        return set()
    if change.entity_name in {
        "Department",
        "WorkingGroup",
        "Employee",
        "WorkGroupMembership",
    }:
        return set()
    return set()


def pending_branch_ids(session: Session) -> Set[str]:
    """Возвращает филиалы, имеющие неэкспортированные изменения."""
    branches: Set[str] = set()
    changes = (
        session.query(Change).filter(Change.exported_at.is_(None)).all()
    )
    for change in changes:
        resolved = branches_for_change(session, change)
        if resolved:
            branches.update(resolved)
    return branches
