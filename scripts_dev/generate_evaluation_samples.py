"""Генератор тестовых файлов для модуля загрузки оценок.

Скрипт создаёт два текстовых файла фиксированной ширины:

* ``evaluation_data_139.txt`` — схема «Оценочные данные» (139 символов);
* ``effect_101.txt`` — схема «Эффект» (101 символ).

Содержимое берётся из базы данных головного офиса: генератор выбирает
неоценённые научные материалы и телеграммы (по умолчанию 40% от их числа),
раскладывает их по коду филиала, исходящему номеру и отчётному месяцу так,
чтобы после загрузки сопоставилось примерно 85% строк, и портит около 3%
строк лишним или недостающим пробелом (ошибка ``line_length``).

Данные для полей, которых нет в базе (код подборки, номер группы, количество,
случайные страны и суммы), генерируются так, чтобы покрыть как можно больше
вариантов разбора. Рядом с файлами пишется ``manifest.json`` с ожидаемым
решением по каждой строке и результатом самопроверки настоящим сопоставителем.

Запуск::

    .venv/Scripts/python.exe scripts_dev/generate_evaluation_samples.py \
        --db D:/projects/Obfuscation/123.db \
        --project . \
        --out var/testdata/evaluations

Скрипт ничего не пишет в базу данных — только читает её.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Длины записей, по которым импортёр определяет схему автоматически
# (см. internal_correspondence/text_import/scheme.py: detect_scheme_by_length).
EVALUATION_LINE_LENGTH = 139
EFFECT_LINE_LENGTH = 101

# Код филиала в строках вида «11-1-12»: две цифры, одна цифра, две цифры.
BRANCH_CODE_RE = re.compile(r"^\d{2}-\d-\d{2}$")

SYNTHETIC_BRANCH_PREFIX = "11-1-"
SYNTHETIC_BRANCH_START = 12

COLLECTION_CODES = ("ОБЩ", "ЭКС", "НТИ", "ЗАК")

TYPE_CHAR_ALPHABET = "СДОТП"

_PROJECT_ROOT: Optional[Path] = None


# ---------------------------------------------------------------------------
# Подключение к проекту
# ---------------------------------------------------------------------------

def bootstrap(project: Path) -> Path:
    """Добавляет каталог проекта в ``sys.path`` и запоминает его."""
    global _PROJECT_ROOT
    resolved = Path(project).expanduser().resolve()
    if not (resolved / "internal_correspondence").is_dir():
        raise SystemExit(
            f"В каталоге проекта нет пакета internal_correspondence: {resolved}"
        )
    if str(resolved) not in sys.path:
        sys.path.insert(0, str(resolved))
    _PROJECT_ROOT = resolved
    return resolved


def project_root() -> Path:
    """Возвращает каталог проекта, полученный в :func:`bootstrap`."""
    if _PROJECT_ROOT is None:
        raise RuntimeError("bootstrap() не выполнен")
    return _PROJECT_ROOT


# ---------------------------------------------------------------------------
# Описание данных
# ---------------------------------------------------------------------------

@dataclass
class Document:
    """Документ базы данных, для которого генерируется строка."""

    entity: str                 # "material" | "telegram"
    entity_id: str
    branch_id: str
    outgoing_no: str
    outgoing_date: date
    type_value: int
    country: Optional[str] = None
    cost: Optional[float] = None
    incoming_no: Optional[str] = None
    tasks: List[str] = field(default_factory=list)


@dataclass
class PlanRow:
    """Запись плана: что именно попадёт в строку файла."""

    document: Document
    expectation: str            # match | not_found | month_shift | unknown_branch
                                # | empty_number | defect
    defect: Optional[str] = None  # None | "extra" | "missing"
    branch_code: str = ""
    outgoing_no: str = ""
    year_month: str = ""
    value_code: str = ""
    evaluation_date: Optional[date] = None
    source_type: str = ""
    material_type: str = ""
    task_code: str = ""
    country: str = ""
    quantity: int = 1
    group: str = "1"
    collection: str = ""
    costs: Optional[float] = None
    effect: Optional[float] = None
    their_no: str = ""

    # Результаты самопроверки заполняются после разбора файла.
    actual_matched: bool = False
    actual_reason: str = ""
    actual_problem: str = ""


# ---------------------------------------------------------------------------
# Чтение базы данных
# ---------------------------------------------------------------------------

def make_engine(db: str):
    """Создаёт движок SQLAlchemy по пути к файлу или по URL базы."""
    from sqlalchemy import create_engine

    if "://" in db:
        return create_engine(db, future=True)
    path = Path(db).expanduser()
    if not path.exists():
        raise SystemExit(f"Файл базы данных не найден: {path}")
    return create_engine(f"sqlite:///{path.resolve().as_posix()}", future=True)


def _material_to_document(material: Any) -> Document:
    return Document(
        entity="material",
        entity_id=str(material.id),
        branch_id=str(material.branch_id),
        outgoing_no=str(material.outgoing_number or "").strip(),
        outgoing_date=material.outgoing_date,
        type_value=int(material.type),
        country=(str(material.countries[0].id) if material.countries else None),
        cost=(float(material.cost) if material.cost is not None else None),
        incoming_no=(
            str(material.incoming_number).strip() if material.incoming_number else None
        ),
        tasks=[str(task.id) for task in material.tasks],
    )


def _telegram_to_document(telegram: Any) -> Document:
    return Document(
        entity="telegram",
        entity_id=str(telegram.id),
        branch_id=str(telegram.branch_id),
        outgoing_no=str(telegram.outgoing_number or "").strip(),
        outgoing_date=telegram.outgoing_date,
        type_value=int(telegram.type),
        country=(str(telegram.countries[0].id) if telegram.countries else None),
        cost=None,
        incoming_no=(
            str(telegram.incoming_number).strip() if telegram.incoming_number else None
        ),
        tasks=[str(task.id) for task in telegram.tasks],
    )


def load_documents(
    session,
) -> Tuple[List[Document], List[Document], List[str], Dict[Tuple[str, str], List[date]]]:
    """Возвращает неоценённые материалы, неоценённые телеграммы, предупреждения и ключи.

    Ключи — словарь ``(branch_id, outgoing_number) → [даты]`` по всем документам
    базы. Он нужен, чтобы «неродные» номера в строках гарантированно не
    совпали с реальными документами.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from internal_correspondence.orm.models import ScientificMaterial, Telegram

    warnings: List[str] = []

    material_rows = session.scalars(
        select(ScientificMaterial)
        .options(
            selectinload(ScientificMaterial.tasks),
            selectinload(ScientificMaterial.countries),
            selectinload(ScientificMaterial.evaluations),
        )
        .order_by(ScientificMaterial.outgoing_date, ScientificMaterial.outgoing_number)
    ).all()
    telegram_rows = session.scalars(
        select(Telegram)
        .options(
            selectinload(Telegram.tasks),
            selectinload(Telegram.countries),
            selectinload(Telegram.evaluations),
        )
        .order_by(Telegram.outgoing_date, Telegram.outgoing_number)
    ).all()

    materials_all = [
        item
        for item in (_material_to_document(row) for row in material_rows)
        if item.outgoing_no and item.outgoing_date is not None
    ]
    telegrams_all = [
        item
        for item in (_telegram_to_document(row) for row in telegram_rows)
        if item.outgoing_no and item.outgoing_date is not None
    ]

    evaluated_materials = {str(row.id) for row in material_rows if row.evaluations}
    evaluated_telegrams = {str(row.id) for row in telegram_rows if row.evaluations}

    materials = [item for item in materials_all if item.entity_id not in evaluated_materials]
    telegrams = [item for item in telegrams_all if item.entity_id not in evaluated_telegrams]

    warnings.extend(_ambiguous_warnings(materials_all, telegrams_all))
    return materials, telegrams, warnings, document_keys(materials_all + telegrams_all)


def document_keys(documents: Sequence[Document]) -> Dict[Tuple[str, str], List[date]]:
    """Строит индекс ``(branch_id, outgoing_number) → даты`` по документам."""
    index: Dict[Tuple[str, str], List[date]] = {}
    for item in documents:
        index.setdefault((item.branch_id, item.outgoing_no), []).append(
            item.outgoing_date
        )
    return index


def _ambiguous_warnings(
    materials: Sequence[Document], telegrams: Sequence[Document]
) -> List[str]:
    """Ищет ключи, которые сопоставитель сочтёт неоднозначными."""
    index: Dict[Tuple[str, str], List[Tuple[str, date]]] = {}
    for item in list(materials) + list(telegrams):
        index.setdefault((item.branch_id, item.outgoing_no), []).append(
            (item.entity, item.outgoing_date)
        )
    warnings: List[str] = []
    for (branch_id, outgoing_no), entries in index.items():
        months = {(item[1].year, item[1].month) for item in entries}
        entities = {item[0] for item in entries}
        if len(entries) > 1 and len(entities) > 1:
            warnings.append(
                f"ключ {branch_id} / {outgoing_no} встречается в материалах и "
                f"телеграммах ({len(months)} мес.) — строки с ним станут неоднозначными"
            )
    return warnings


def resolve_branch_codes(
    session,
    explicit_map: Dict[str, str],
    use_db_ids: bool,
) -> Tuple[Dict[str, str], List[str]]:
    """Строит отображение ``Branch.id`` → код филиала в строке файла."""
    from sqlalchemy import select

    from internal_correspondence.orm.models import Branch

    warnings: List[str] = []
    codes: Dict[str, str] = {}
    next_suffix = SYNTHETIC_BRANCH_START
    used = set()

    for branch in session.scalars(select(Branch).order_by(Branch.id)).all():
        branch_id = str(branch.id)
        if branch_id in explicit_map:
            codes[branch_id] = explicit_map[branch_id]
            used.add(explicit_map[branch_id])
            continue
        if use_db_ids or BRANCH_CODE_RE.fullmatch(branch_id):
            codes[branch_id] = branch_id
            used.add(branch_id)
            continue
        while f"{SYNTHETIC_BRANCH_PREFIX}{next_suffix}" in used:
            next_suffix += 1
        synthetic = f"{SYNTHETIC_BRANCH_PREFIX}{next_suffix}"
        used.add(synthetic)
        next_suffix += 1
        codes[branch_id] = synthetic
        warnings.append(
            f"код филиала {branch_id} не соответствует виду 11-1-12: "
            f"в строках будет {synthetic} (для совпадения переименуйте филиал в БД)"
        )

    for branch_id, code in explicit_map.items():
        if branch_id not in codes:
            warnings.append(f"--branch-map: филиала {branch_id} нет в базе")
    return codes, warnings


# ---------------------------------------------------------------------------
# Выбор документов
# ---------------------------------------------------------------------------

def select_documents(
    materials: Sequence[Document],
    telegrams: Sequence[Document],
    total: int,
    rng: random.Random,
) -> List[Document]:
    """Отбирает документы, равномерно покрывая филиалы и типы документов.

    Сначала раскладываем документы по ячейкам «тип × филиал», затем идём
    внешним циклом по типам, а внутренним — по филиалам: так в выборку
    попадают все встречающиеся типы и все филиалы, если документов хватает.
    """
    buckets: Dict[Tuple[str, int, str], List[Document]] = {}
    for item in list(materials) + list(telegrams):
        key = (item.entity, item.type_value, item.branch_id)
        buckets.setdefault(key, []).append(item)

    for key in buckets:
        rng.shuffle(buckets[key])

    type_keys = sorted({(key[0], key[1]) for key in buckets})
    picked: List[Document] = []
    depth = 0
    while len(picked) < total:
        progressed = False
        for entity, type_value in type_keys:
            branch_keys = sorted(
                key for key in buckets if key[0] == entity and key[1] == type_value
            )
            rng.shuffle(branch_keys)
            for key in branch_keys:
                bucket = buckets[key]
                if depth < len(bucket):
                    picked.append(bucket[depth])
                    progressed = True
                    if len(picked) >= total:
                        break
            if len(picked) >= total:
                break
        if not progressed:
            break
        depth += 1
    return picked


def year_month_text(value: date, mode: str) -> str:
    """Форматирует отчётный месяц: ГГГГММ или ММГГГГ."""
    if mode == "month-first":
        return f"{value.month:02d}{value.year:04d}"
    return f"{value.year:04d}{value.month:02d}"


def _month_mode(policy: str, index: int) -> str:
    """Выбирает формат месяца для строки с учётом политики ``--year-month-formats``."""
    if policy == "month-first":
        return "month-first"
    if policy == "gregorian":
        return "gregorian"
    # both: каждый четвёртый месяц пишем в формате ММГГГГ, чтобы проверить оба разбора
    return "month-first" if index % 4 == 3 else "gregorian"


# ---------------------------------------------------------------------------
# Заполнение полей
# ---------------------------------------------------------------------------

def format_amount(value: Optional[float]) -> str:
    """Форматирует сумму для поля шириной 9 символов."""
    if value is None:
        return ""
    if value > 999_999.99:
        value = 999_999.99
    return f"{value:.2f}"


def _pick_value_codes(count: int, rng: random.Random) -> List[str]:
    """Возвращает коды оценок: первые четыре гарантированно разные."""
    from internal_correspondence.core.domain_pack import enum_codes

    codes = list(enum_codes("evaluation_value"))
    if not codes:
        raise SystemExit("В пакете предметной области нет перечисления evaluation_value")
    result: List[str] = []
    for index in range(min(count, len(codes))):
        result.append(codes[index])
    rng.shuffle(result)
    while len(result) < count:
        result.append(rng.choice(codes))
    return result


def _type_char(entity: str, type_value: int, rng: random.Random) -> str:
    """Первый символ кода типа документа из пакета предметной области."""
    from internal_correspondence.core.domain_pack import enum_codes

    name = "material_type" if entity == "material" else "telegram_type"
    codes = list(enum_codes(name))
    code = codes[type_value] if 0 <= type_value < len(codes) else "?"
    char = code[:1] or "?"
    if rng.random() < 0.10:
        # Иногда подставляем посторонний символ: проверка устойчивости
        # к неизвестным кодам в информационных полях.
        alternatives = [item for item in TYPE_CHAR_ALPHABET if item != char]
        if alternatives:
            char = rng.choice(alternatives)
    return char


def _source_type_char(rng: random.Random) -> str:
    from internal_correspondence.core.domain_pack import enum_codes

    codes = [code for code in enum_codes("source_type") if code]
    if not codes:
        return "Н"
    return rng.choice(codes)[:1]


def _evaluation_date(outgoing: date, rng: random.Random) -> date:
    """Дата оценки: в том же месяце или в первые дни следующего."""
    shift = rng.randint(0, 25)
    return outgoing + timedelta(days=shift)


def _shift_month(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def build_plan(
    documents: Sequence[Document],
    branch_codes: Dict[str, str],
    rng: random.Random,
    matched_share: float,
    defect_share: float,
    month_format: str,
    country_pool: Sequence[str],
    taken_keys: Optional[Dict[Tuple[str, str], List[date]]] = None,
) -> List[PlanRow]:
    """Строит план строк: что совпадёт, что нет и что будет испорчено.

    Ожидание строки — либо ``"match"``, либо код причины, которую должен
    вернуть сопоставитель (``document_not_found``, ``year_month_invalid``),
    либо ``"defect"`` для строки с неверной длиной.
    """
    total = len(documents)
    if total == 0:
        return []

    defect_count = int(round(defect_share * total))
    matched_count = int(round(matched_share * total))
    matched_count = max(1, min(matched_count, total - defect_count))
    other_count = total - matched_count - defect_count

    # Виды несопоставленных строк: разные причины в журнале импорта.
    misses = ["not_found", "month_shift", "unknown_branch", "year_month_invalid"]
    roles: List[Tuple[str, Optional[str]]] = [("match", None)] * matched_count
    roles.extend([("defect", "extra")] * defect_count)
    for index in range(other_count):
        roles.append((misses[index % len(misses)], None))

    rows: List[PlanRow] = []
    value_codes = _pick_value_codes(total, rng)
    for index, document in enumerate(documents):
        role, defect = roles[index]
        row = PlanRow(document=document, expectation=role, defect=defect)
        row.branch_code = branch_codes.get(document.branch_id, document.branch_id)
        row.outgoing_no = document.outgoing_no
        month_source = document.outgoing_date
        if role == "defect":
            row.defect = defect if defect else "extra"
            if index % 2:
                row.defect = "missing"
            row.expectation = "defect"
        elif role == "not_found":
            row.outgoing_no = _free_number(document.branch_id, taken_keys, rng)
            row.expectation = "document_not_found"
        elif role == "month_shift":
            month_source = _shift_month(document.outgoing_date, rng.choice((1, -1, 2)))
            row.expectation = "document_not_found"
        elif role == "unknown_branch":
            row.branch_code = f"{SYNTHETIC_BRANCH_PREFIX}{rng.randint(90, 99)}"
            row.expectation = "document_not_found"
        elif role == "year_month_invalid":
            row.expectation = "year_month_invalid"

        if row.expectation == "year_month_invalid":
            # Месяц «13»: строка разбирается, но месяц не распознаётся.
            row.year_month = f"13{month_source.year:04d}"
        else:
            row.year_month = year_month_text(
                month_source, _month_mode(month_format, index)
            )
        row.value_code = value_codes[index]
        row.evaluation_date = _evaluation_date(document.outgoing_date, rng)
        row.source_type = _source_type_char(rng)
        row.material_type = _type_char(document.entity, document.type_value, rng)
        row.task_code = document.tasks[0] if document.tasks else ""
        if document.country:
            row.country = document.country
        elif country_pool and rng.random() < 0.5:
            row.country = rng.choice(list(country_pool))
        else:
            row.country = ""
        if rng.random() < 0.05:
            row.country = "ZZZ"  # неизвестная страна
        row.quantity = rng.choice((1, 1, 2, 3, 9))
        row.group = str(rng.randint(1, 3))
        row.collection = rng.choice(COLLECTION_CODES) if rng.random() < 0.9 else ""
        row.costs = _costs_value(document, rng)
        row.effect = _effect_value(document, rng)
        row.their_no = (document.incoming_no or "")[:9]
        rows.append(row)

    _move_clean_row_first(rows)
    return rows


def _free_number(
    branch_id: str,
    taken_keys: Optional[Dict[Tuple[str, str], List[date]]],
    rng: random.Random,
) -> str:
    """Подбирает исходящий номер, которого нет у документов филиала.

    Номер строится по шаблону «ИСХ-#####», поэтому по базе проверяется только
    множество занятых номеров нужного филиала — так строка гарантированно не
    сопоставится ни с одним документом.
    """
    taken = set()
    if taken_keys:
        for (key_branch, number) in taken_keys:
            if key_branch == branch_id:
                taken.add(number)
    for _attempt in range(1000):
        candidate = f"ИСХ-{rng.randint(10000, 99999)}"
        if candidate not in taken:
            return candidate
    return f"ИСХ-{rng.randint(100000, 999999)}"


def _costs_value(document: Document, rng: random.Random) -> Optional[float]:
    """Стоимость для схемы «Оценочные данные»."""
    if document.cost is not None:
        return document.cost
    if rng.random() < 0.6:
        return round(rng.uniform(8_000, 490_000), 2)
    return None


def _effect_value(document: Document, rng: random.Random) -> Optional[float]:
    """Эффект для схемы «Эффект».

    Для материала эффект совпадает с его стоимостью (при загрузке она
    перезаписывается тем же значением), для телеграммы в большинстве случаев
    пуст.
    """
    if document.entity == "material":
        if document.cost is not None:
            return document.cost
        return round(rng.uniform(8_000, 490_000), 2)
    if rng.random() < 0.25:
        return round(rng.uniform(8_000, 490_000), 2)
    return None


def _move_clean_row_first(rows: List[PlanRow]) -> None:
    """Первая строка обязана быть без дефекта: по ней определяется схема."""
    for index, row in enumerate(rows):
        if row.defect is None and row.expectation == "match":
            if index != 0:
                rows[0], rows[index] = rows[index], rows[0]
            return


# ---------------------------------------------------------------------------
# Сборка строк
# ---------------------------------------------------------------------------

def row_values(row: PlanRow, scheme_name: str) -> Dict[str, Any]:
    """Значения полей строки в терминах схемы разметки."""
    first, second, third = _split_branch_code(row.branch_code)
    common = {
        "branch_part_1": first,
        "branch_part_2": second,
        "branch_part_3": third,
        "outgoing_no": row.outgoing_no,
        "task_code": row.task_code,
        "value": row.value_code,
        "evaluation_date": (
            row.evaluation_date.strftime("%d.%m.%Y") if row.evaluation_date else ""
        ),
        "year_month": row.year_month,
    }
    if scheme_name == "effect":
        return {
            **common,
            "material_type": row.material_type,
            "effect": row.effect,
            "their_no": row.their_no,
        }
    return {
        **common,
        "source_type": row.source_type,
        "material_type": row.material_type,
        "country": row.country,
        "quantity": row.quantity,
        "group": row.group,
        "collection": row.collection,
        "costs": row.costs,
    }


def _split_branch_code(code: str) -> Tuple[str, str, str]:
    """Делит код филиала на три части схемы; иначе — редкие заглушки."""
    parts = (code or "").split("-")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], parts[1], ""
    return (code or "")[:2], "", ""


def render_line(scheme, values: Dict[str, Any]) -> str:
    """Собирает строку фиксированной ширины по схеме."""
    total = scheme.line_length
    if total is None:
        raise ValueError("схема не фиксированной ширины")
    buffer = [" "] * total
    for spec in scheme.fields:
        if spec.start is None or spec.length is None:
            continue
        value = values.get(spec.name)
        text = "" if value is None else str(value)
        if spec.type in ("number", "integer"):
            text = text.rjust(spec.length)
        else:
            text = text.ljust(spec.length)
        text = text[: spec.length]
        begin = spec.start - 1
        buffer[begin : begin + spec.length] = list(text)
    return "".join(buffer)


def apply_defect(line: str, defect: Optional[str]) -> str:
    """Портит длину строки лишним или недостающим пробелом."""
    if defect == "extra":
        return line + " "
    if defect == "missing":
        return line[:-1]
    return line


def write_file(path: Path, lines: Sequence[str], encoding: str, eol: str) -> None:
    """Пишет строки без заголовка, завершая каждую переводом строки."""
    separator = "\r\n" if eol == "crlf" else "\n"
    text = "".join(line + separator for line in lines)
    path.write_text(text, encoding=encoding, newline="")


# ---------------------------------------------------------------------------
# Самопроверка
# ---------------------------------------------------------------------------

def verify_file(session, scheme, lines: Sequence[str], plan: Sequence[PlanRow]) -> Dict[str, Any]:
    """Разбирает готовый файл и сверяет результат с планом."""
    from internal_correspondence.text_import.matcher import Matcher
    from internal_correspondence.text_import.parsing import parse_rows

    report = parse_rows(list(lines), scheme)
    problems = {problem.row_no: problem.code for problem in report.problems}
    matcher = Matcher(session)
    results = matcher.match_auto(report.rows)
    matches = {result.row.row_no: result for result in results}

    mismatches: List[str] = []
    for index, row in enumerate(plan):
        row_no = index + 1
        row.actual_problem = problems.get(row_no, "")
        result = matches.get(row_no)
        if result is not None:
            row.actual_matched = bool(result.matched)
            row.actual_reason = str(result.reason or "")
        if row.expectation == "defect":
            if not row.actual_problem:
                mismatches.append(f"строка {row_no}: ожидался дефект длины, его нет")
            continue
        if row.expectation == "match":
            if not row.actual_matched:
                mismatches.append(
                    f"строка {row_no}: ожидалось совпадение, получено «{row.actual_reason}»"
                    + (f" ({row.actual_problem})" if row.actual_problem else "")
                )
            continue
        if row.actual_matched:
            mismatches.append(
                f"строка {row_no}: ожидалось «{row.expectation}», но документ найден"
            )
        elif row.actual_reason != row.expectation:
            mismatches.append(
                f"строка {row_no}: ожидалась причина «{row.expectation}», "
                f"получено «{row.actual_reason or row.actual_problem}»"
            )

    matched = sum(1 for result in results if result.matched)
    return {
        "rows": len(lines),
        "matched": matched,
        "matched_share": round(matched / len(lines), 4) if lines else 0.0,
        "problems": [
            {"row": number, "code": code} for number, code in sorted(problems.items())
        ],
        "mismatches": mismatches,
    }


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def load_schemes(project: Path):
    """Загружает схемы «Оценочные данные» и «Эффект» из каталога проекта."""
    from internal_correspondence.text_import.scheme import load_schemes as load_all

    schemes = load_all(project / "schemes")
    evaluation = next(
        (item for item in schemes if item.line_length == EVALUATION_LINE_LENGTH), None
    )
    effect = next((item for item in schemes if item.line_length == EFFECT_LINE_LENGTH), None)
    missing = [
        name
        for name, scheme in (("139", evaluation), ("101", effect))
        if scheme is None
    ]
    if missing:
        raise SystemExit(
            f"В каталоге {project / 'schemes'} нет схемы длиной {', '.join(missing)} символов"
        )
    return evaluation, effect


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Генератор тестовых файлов импорта оценок (139 и 101 символ).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--db", required=True, help="путь к файлу базы или URL SQLAlchemy")
    parser.add_argument(
        "--project",
        default=str(Path(__file__).resolve().parents[1]),
        help="каталог проекта (нужен для моделей, схем и пакета предметной области)",
    )
    parser.add_argument("--out", required=True, help="каталог для готовых файлов")
    parser.add_argument("--share", type=float, default=0.40, help="доля неоценённых документов")
    parser.add_argument(
        "--matched-share", type=float, default=0.85, help="доля совпадающих строк"
    )
    parser.add_argument(
        "--defect-share", type=float, default=0.03, help="доля строк с ошибкой длины"
    )
    parser.add_argument("--seed", type=int, default=20261126, help="начальное число генератора")
    parser.add_argument(
        "--branch-map",
        default="",
        help="карта кодов филиалов, например BR-001=11-1-12,BR-002=11-1-13",
    )
    parser.add_argument(
        "--use-db-branch-ids",
        action="store_true",
        help="писать идентификаторы филиалов из базы как есть",
    )
    parser.add_argument(
        "--year-month-formats",
        choices=("both", "gregorian", "month-first"),
        default="both",
        help="формат отчётного месяца в строках",
    )
    parser.add_argument("--encoding", default="utf-8", help="кодировка готовых файлов")
    parser.add_argument(
        "--eol", choices=("crlf", "lf"), default="crlf", help="перевод строки в файлах"
    )
    parser.add_argument("--quiet", action="store_true", help="печатать только итог")
    return parser.parse_args(argv)


def _parse_branch_map(text: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for chunk in (text or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise SystemExit(f"--branch-map: ожидается «BR-001=11-1-12», получено «{chunk}»")
        key, value = chunk.split("=", 1)
        mapping[key.strip()] = value.strip()
    return mapping


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    project = bootstrap(Path(args.project))
    rng = random.Random(args.seed)
    month_mode = args.year_month_formats

    from sqlalchemy.orm import Session

    evaluation_scheme, effect_scheme = load_schemes(project)
    engine = make_engine(args.db)
    session = Session(engine)

    materials, telegrams, warnings, taken_keys = load_documents(session)
    total_docs = len(materials) + len(telegrams)
    if total_docs == 0:
        raise SystemExit("В базе нет неоценённых документов — генерировать нечего")

    branch_codes, branch_warnings = resolve_branch_codes(
        session, _parse_branch_map(args.branch_map), args.use_db_branch_ids
    )
    warnings.extend(branch_warnings)

    total_rows = max(1, int(round(args.share * total_docs)))
    total_rows = min(total_rows, total_docs)
    documents = select_documents(materials, telegrams, total_rows, rng)

    country_pool = sorted({item.country for item in materials + telegrams if item.country})

    plans: Dict[str, List[PlanRow]] = {}
    for name, scheme in (("evaluation", evaluation_scheme), ("effect", effect_scheme)):
        plan_rng = random.Random(f"{args.seed}-{name}")
        plans[name] = build_plan(
            documents,
            branch_codes,
            plan_rng,
            args.matched_share,
            args.defect_share,
            month_mode,
            country_pool,
            taken_keys,
        )

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    files: Dict[str, Path] = {
        "evaluation": out_dir / "evaluation_data_139.txt",
        "effect": out_dir / "effect_101.txt",
    }
    schemes = {"evaluation": evaluation_scheme, "effect": effect_scheme}
    scheme_names = {"evaluation": "evaluation", "effect": "effect"}

    rendered: Dict[str, List[str]] = {}
    for name, plan in plans.items():
        lines = [
            apply_defect(
                render_line(schemes[name], row_values(row, scheme_names[name])), row.defect
            )
            for row in plan
        ]
        rendered[name] = lines
        write_file(files[name], lines, args.encoding, args.eol)

    report: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": str(args.db),
        "seed": args.seed,
        "branch_codes": branch_codes,
        "documents_total": total_docs,
        "unevaluated": {"materials": len(materials), "telegrams": len(telegrams)},
        "rows_per_file": len(documents),
        "files": {name: str(path) for name, path in files.items()},
        "warnings": warnings,
        "checks": {},
        "plans": {},
    }

    for name, plan in plans.items():
        try:
            checks = verify_file(session, schemes[name], rendered[name], plan)
        except Exception as exc:  # noqa: BLE001 - самопроверка не должна ломать генерацию
            checks = {"error": f"{type(exc).__name__}: {exc}"}
        report["checks"][name] = checks
        report["plans"][name] = [
            {
                "row": index + 1,
                "entity": row.document.entity,
                "entity_id": row.document.entity_id,
                "branch_code": row.branch_code,
                "outgoing_no": row.outgoing_no,
                "year_month": row.year_month,
                "value": row.value_code,
                "evaluation_date": (
                    row.evaluation_date.isoformat() if row.evaluation_date else None
                ),
                "expectation": row.expectation,
                "defect": row.defect,
                "actual_matched": row.actual_matched,
                "actual_reason": row.actual_reason,
                "actual_problem": row.actual_problem,
            }
            for index, row in enumerate(plan)
        ]

    manifest = out_dir / "manifest.json"
    manifest.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    session.close()
    engine.dispose()

    if not args.quiet:
        _print_report(report)
    return 0


def _print_report(report: Dict[str, Any]) -> None:
    print("Неоценённых документов: "
          f"материалов {report['unevaluated']['materials']}, "
          f"телеграмм {report['unevaluated']['telegrams']}")
    print(f"Строк в каждом файле: {report['rows_per_file']}")
    for name, path in report["files"].items():
        checks = report["checks"].get(name, {})
        print(f"  {path}")
        if "error" in checks:
            print(f"    самопроверка не выполнилась: {checks['error']}")
            continue
        print(
            f"    разобрано {checks['rows']}, совпало {checks['matched']} "
            f"({checks['matched_share'] * 100:.1f}%), "
            f"проблемных строк {len(checks['problems'])}"
        )
        for item in checks["problems"]:
            print(f"      строка {item['row']}: {item['code']}")
        for message in checks["mismatches"]:
            print(f"      расхождение с планом: {message}")
    for warning in report["warnings"]:
        print(f"! {warning}")
    print(f"Отчёт: {Path(report['files']['evaluation']).parent / 'manifest.json'}")


if __name__ == "__main__":
    raise SystemExit(main())
