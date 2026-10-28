"""Импорт справочных данных из файлов Excel."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.orm.models import (
    AcademicTitle,
    Branch,
    Consumer,
    Country,
    Leader,
    ScientificTask,
    TerritorialUnit,
)
from internal_correspondence.services.base_service import BaseService

logger = get_logger("reference_import")


class ReferenceImportError(Exception):
    """Ошибка импорта справочных данных."""

    pass


def _read_sheet_rows(path: Path, sheet_name: str) -> List[Dict[str, Any]]:
    """Читает строки листа Excel и возвращает список словарей."""
    workbook = load_workbook(path, data_only=True)
    if sheet_name not in workbook.sheetnames:
        raise ReferenceImportError(f"Лист '{sheet_name}' не найден в файле {path}")

    sheet = workbook[sheet_name]
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    result = []
    for row in rows[1:]:
        record = {}
        for idx, header in enumerate(headers):
            record[header] = row[idx] if idx < len(row) else None
        result.append(record)
    return result


def _clean_value(value: Any) -> Optional[str]:
    """Приводит значение ячейки к строке или None."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _to_int(value: Any) -> Optional[int]:
    """Приводит значение ячейки к int или None."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _to_float(value: Any) -> Optional[float]:
    """Приводит значение ячейки к float или None."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _date_from_value(value: Any):
    """Возвращает дату из значения ячейки (datetime/строка/число)."""
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str):
        from datetime import datetime
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return None


def import_territorial_units(session: Session, path: Path) -> int:
    """Импортирует территориальные единицы."""
    rows = _read_sheet_rows(path, "Территориальные единицы")
    service = BaseService(session, TerritorialUnit)
    count = 0
    for row in rows:
        unit_id = _clean_value(row.get("Сокращенное наименование"))
        name = _clean_value(row.get("Наименование"))
        if not unit_id or not name:
            continue
        if service.exists(unit_id):
            continue
        service.create({"id": unit_id, "name": name})
        count += 1
    logger.info("Импортировано территориальных единиц: %d", count)
    return count


def import_branches(session: Session, path: Path) -> int:
    """Импортирует филиалы."""
    rows = _read_sheet_rows(path, "Филиалы")
    service = BaseService(session, Branch)
    count = 0
    for row in rows:
        branch_id = _clean_value(row.get("Индекс"))
        name = _clean_value(row.get("Наименование"))
        short_name = _clean_value(row.get("Сокращенное наименование"))
        unit_id = _clean_value(row.get("Территориальная единица"))
        if not branch_id or not name:
            continue
        if service.exists(branch_id):
            continue
        service.create({
            "id": branch_id,
            "name": name,
            "short_name": short_name or branch_id,
            "territorial_unit_id": unit_id,
        })
        count += 1
    logger.info("Импортировано филиалов: %d", count)
    return count


def import_countries(session: Session, path: Path) -> int:
    """Импортирует страны."""
    rows = _read_sheet_rows(path, "Страны")
    service = BaseService(session, Country)
    count = 0
    for row in rows:
        country_id = _clean_value(row.get("Сокращенное наименование"))
        name = _clean_value(row.get("Наименование"))
        if not country_id or not name:
            continue
        if service.exists(country_id):
            continue
        service.create({"id": country_id, "name": name})
        count += 1
    logger.info("Импортировано стран: %d", count)
    return count


def import_academic_titles(session: Session, path: Path) -> int:
    """Импортирует научные звания."""
    rows = _read_sheet_rows(path, "Научные звания")
    service = BaseService(session, AcademicTitle)
    count = 0
    for row in rows:
        title_id = _clean_value(row.get("Сокращенное наименование"))
        name = _clean_value(row.get("Наименование"))
        genitive = _clean_value(row.get("Род. падеж"))
        dative = _clean_value(row.get("Дат. падеж"))
        order = _to_int(row.get("Порядок"))
        if not title_id or not name:
            continue
        if service.exists(title_id):
            continue
        service.create({
            "id": title_id,
            "name": name,
            "genitive": genitive,
            "dative": dative,
            "sort_order": order or 0,
        })
        count += 1
    logger.info("Импортировано научных званий: %d", count)
    return count


def import_scientific_tasks(session: Session, path: Path) -> int:
    """Импортирует научные задачи."""
    rows = _read_sheet_rows(path, "Научные задачи")
    service = BaseService(session, ScientificTask)
    count = 0
    for row in rows:
        task_id = _clean_value(row.get("Код"))
        name = _clean_value(row.get("Наименование"))
        task_type = _clean_value(row.get("Тип"))
        start_date = _date_from_value(row.get("Начало действия"))
        end_date = _date_from_value(row.get("Конец действия"))
        comment = _clean_value(row.get("Комментарий"))
        partial = _to_float(row.get("Частичное решение"))
        full = _to_float(row.get("Полное решение"))
        if not task_id or not name:
            continue
        if service.exists(task_id):
            continue
        service.create({
            "id": task_id,
            "name": name,
            "type": task_type,
            "start_date": start_date,
            "end_date": end_date,
            "comment": comment,
            "partial_threshold": partial,
            "full_threshold": full,
        })
        count += 1
    logger.info("Импортировано научных задач: %d", count)
    return count


def import_consumers(session: Session, path: Path) -> int:
    """Импортирует потребителей."""
    rows = _read_sheet_rows(path, "Потребители")
    service = BaseService(session, Consumer)
    count = 0
    for row in rows:
        consumer_id = _clean_value(row.get("Индекс"))
        short_name = _clean_value(row.get("Сокращенное наименование"))
        name = _clean_value(row.get("Наименование"))
        if not consumer_id or not name:
            continue
        if service.exists(consumer_id):
            continue
        service.create({
            "id": consumer_id,
            "short_name": short_name or consumer_id,
            "name": name,
        })
        count += 1
    logger.info("Импортировано потребителей: %d", count)
    return count


def import_leaders(session: Session, path: Path) -> int:
    """Импортирует руководителей."""
    rows = _read_sheet_rows(path, "Руководители")
    service = BaseService(session, Leader)
    count = 0
    for row in rows:
        leader_id = _clean_value(row.get("Сокращенное наименование"))
        active_value = row.get("Действительный")
        active = True
        if active_value is not None:
            text = str(active_value).strip().lower()
            active = text in ("true", "1", "да", "yes", "истина")
        if not leader_id:
            continue
        if service.exists(leader_id):
            continue
        service.create({"id": leader_id, "active": active})
        count += 1
    logger.info("Импортировано руководителей: %d", count)
    return count


# Карта имён листов на функции импорта для "Первичные данные.xlsx"
PRIMARY_IMPORTERS = {
    "Территориальные единицы": import_territorial_units,
    "Филиалы": import_branches,
    "Страны": import_countries,
    "Научные звания": import_academic_titles,
}

# Карта имён листов на функции импорта для "Актуальные данные.xlsx"
ACTUAL_IMPORTERS = {
    "Научные задачи": import_scientific_tasks,
    "Потребители": import_consumers,
    "Руководители": import_leaders,
}


def import_primary_data(session: Session, path: Path) -> Dict[str, int]:
    """Импортирует первичные справочные данные из XLSX."""
    results = {}
    for sheet_name, importer in PRIMARY_IMPORTERS.items():
        try:
            results[sheet_name] = importer(session, path)
        except ReferenceImportError as exc:
            logger.warning("Пропущен лист %s: %s", sheet_name, exc)
            results[sheet_name] = 0
    return results


def import_actual_data(session: Session, path: Path) -> Dict[str, int]:
    """Импортирует актуальные справочные данные из XLSX."""
    results = {}
    for sheet_name, importer in ACTUAL_IMPORTERS.items():
        try:
            results[sheet_name] = importer(session, path)
        except ReferenceImportError as exc:
            logger.warning("Пропущен лист %s: %s", sheet_name, exc)
            results[sheet_name] = 0
    return results
