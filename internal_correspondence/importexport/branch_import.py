"""Первоначальная загрузка филиала из экспортного архива головного офиса.

Мастер первого запуска предлагает выбрать экспортный ZIP головного офиса
и филиал из его состава. Перед применением архива к пустой базе филиала
записи, не относящиеся к выбранному филиалу и не являющиеся общими
справочниками, исключаются (механизм ``exclude`` импортного сервиса).

Правила атрибуции зеркалят ``importexport/branch_scope`` и опираются
только на содержимое export.json:

- справочные сущности (``REFERENCE_ENTITIES``) уходят в базу целиком;
- материал/телеграмма/отдел несут ``branch_id`` — сравнение напрямую;
- рабочая группа/сотрудник привязаны через ``department_id`` — по карте
  отделов выбранного филиала;
- участие в группе — через сотрудника или рабочую группу;
- оценка/файл/источник/адресация/список оценок — через связанные
  документы (списки первичных ключей в сериализованных связях).
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

from sqlalchemy.orm import Session

from internal_correspondence.core.constants import Role
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.importexport.branch_scope import REFERENCE_ENTITIES
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.services.task_distribution_service import NODE_BRANCH, NODE_REGION

logger = get_logger("branch_import")

ExportData = Dict[str, Dict[str, Dict]]


@dataclass
class InitialBranchImport:
    """План первоначальной загрузки: архив головного офиса и выбранный филиал."""

    archive_path: Path
    branch_id: str


def read_export_data(archive_path: Path) -> ExportData:
    """Читает export.json из экспортного архива."""
    with zipfile.ZipFile(archive_path, "r") as archive:
        with archive.open("export.json") as stream:
            data = json.loads(stream.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Некорректный формат export.json в архиве")
    return data


def read_archive_branches(archive_path: Path) -> List[Tuple[str, str]]:
    """Возвращает филиалы архива парами (идентификатор, наименование).

    Удалённые записи и записи без изменяемых полей пропускаются.
    """
    data = read_export_data(archive_path)
    branches: List[Tuple[str, str]] = []
    for branch_id, fields in sorted(data.get("Branch", {}).items()):
        if not isinstance(fields, dict) or fields.get("deleted"):
            continue
        name = str(fields.get("name") or branch_id)
        branches.append((branch_id, name))
    return branches


def _linked_ids(fields: Dict, key: str) -> Set[str]:
    """Возвращает множество первичных ключей сериализованной связи N-N."""
    value = fields.get(key)
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value}


def exclude_set_for_branch(
    export_data: ExportData, branch_id: str
) -> Set[Tuple[str, str]]:
    """Возвращает записи архива, не нужные выбранному филиалу.

    Атрибуция опирается только на содержимое export.json (см. модуль).
    """
    departments = export_data.get("Department", {})
    department_keep = {
        pk
        for pk, fields in departments.items()
        if isinstance(fields, dict) and fields.get("branch_id") == branch_id
    }
    workgroup_keep = {
        pk
        for pk, fields in export_data.get("WorkingGroup", {}).items()
        if isinstance(fields, dict)
        and str(fields.get("department_id")) in department_keep
    }
    employee_keep = {
        pk
        for pk, fields in export_data.get("Employee", {}).items()
        if isinstance(fields, dict)
        and str(fields.get("department_id")) in department_keep
    }
    membership_keep = {
        pk
        for pk, fields in export_data.get("WorkGroupMembership", {}).items()
        if isinstance(fields, dict)
        and (
            str(fields.get("employee_id")) in employee_keep
            or str(fields.get("working_group_id")) in workgroup_keep
        )
    }
    material_keep = {
        pk
        for pk, fields in export_data.get("ScientificMaterial", {}).items()
        if isinstance(fields, dict) and fields.get("branch_id") == branch_id
    }
    telegram_keep = {
        pk
        for pk, fields in export_data.get("Telegram", {}).items()
        if isinstance(fields, dict) and fields.get("branch_id") == branch_id
    }
    document_keep = material_keep | telegram_keep

    file_keep: Set[str] = set()
    source_keep: Set[str] = set()
    for entity in ("ScientificMaterial", "Telegram"):
        for pk in document_keep & set(export_data.get(entity, {})):
            fields = export_data[entity][pk]
            file_keep |= _linked_ids(fields, "files")
            source_keep |= _linked_ids(fields, "sources")

    evaluation_keep = {
        pk
        for pk, fields in export_data.get("Evaluation", {}).items()
        if isinstance(fields, dict)
        and (
            _linked_ids(fields, "materials") & material_keep
            or _linked_ids(fields, "telegrams") & telegram_keep
        )
    }
    report_address_keep = {
        pk
        for pk, fields in export_data.get("ReportAddress", {}).items()
        if isinstance(fields, dict)
        and str(fields.get("telegram_id")) in telegram_keep
    }
    evaluation_list_keep = {
        pk
        for pk, fields in export_data.get("EvaluationList", {}).items()
        if isinstance(fields, dict)
        and _linked_ids(fields, "evaluations") & evaluation_keep
    }
    # Назначения задач: нужны назначения выбранному филиалу, его региону
    # и его подразделениям; чужие назначения валидатор импорта всё равно
    # отклонил бы («узел вне доступного филиала»).
    branch_fields = export_data.get("Branch", {}).get(branch_id, {})
    region_id = str(branch_fields.get("territorial_unit_id") or "")
    added_task_keep = {
        pk
        for pk, fields in export_data.get("AddedTask", {}).items()
        if isinstance(fields, dict)
        and (
            fields.get("node_type") == NODE_BRANCH
            and fields.get("node_id") == branch_id
            or fields.get("node_type") == NODE_REGION
            and str(fields.get("node_id")) == region_id
            or str(fields.get("node_id"))
            in department_keep | workgroup_keep | employee_keep
        )
    }

    keep: Dict[str, Set[str]] = {
        entity: set(export_data.get(entity, {})) for entity in REFERENCE_ENTITIES
    }
    keep.update(
        {
            "Department": department_keep,
            "WorkingGroup": workgroup_keep,
            "Employee": employee_keep,
            "WorkGroupMembership": membership_keep,
            "ScientificMaterial": material_keep,
            "Telegram": telegram_keep,
            "FileRecord": file_keep,
            "Source": source_keep,
            "Evaluation": evaluation_keep,
            "ReportAddress": report_address_keep,
            "EvaluationList": evaluation_list_keep,
            "AddedTask": added_task_keep,
        }
    )

    exclude: Set[Tuple[str, str]] = set()
    for entity, entries in export_data.items():
        kept = keep.get(entity, set())
        for pk in entries:
            if pk not in kept:
                exclude.add((entity, pk))
    logger.info(
        "Первоначальная загрузка %s: исключено %d из %d записей архива",
        branch_id,
        len(exclude),
        sum(len(entries) for entries in export_data.values()),
    )
    return exclude


def run_initial_import(
    session: Session,
    storage_root: Path,
    plan: InitialBranchImport,
) -> Dict:
    """Применяет архив головного офиса к пустой базе выбранного филиала.

    Возвращает статистику импорта (см. ``ImportService.import_archive``).
    """
    export_data = read_export_data(plan.archive_path)
    exclude = exclude_set_for_branch(export_data, plan.branch_id)
    service = ImportService(
        session,
        Path(storage_root),
        Role.BRANCH.value,
        plan.branch_id,
    )
    return service.import_archive(plan.archive_path, exclude=exclude)
