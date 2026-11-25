"""Наполнение базы данных от имени головного офиса: общие справочники.

Создаёт территориальные единицы, филиалы, страны, научные звания,
потребителей, руководителей и научные задачи, распределяет задачи по
филиалам. Филиал на этих данных создаёт свою организационно-штатную
структуру и документы (см. ``tests.seed_branch``).

Состав данных:

- 5 территориальных единиц, по 2 филиала в каждой;
- 30–40 стран, 4 научных звания, 10 потребителей, 5 руководителей;
- 240 научных задач: треть — с 01.01.2025 по 31.12.2025, треть —
  с 01.01.2026 по 31.12.2026, 1/6 — с 01.10.2025 по 30.09.2026,
  1/6 — с 01.10.2025 без срока окончания;
- каждая задача назначена 1–3 филиалам (случайное распределение с
  пересечениями: задача может быть общей для нескольких филиалов).

Скрипт рассчитан на пустую базу: при наличии справочных данных требуется
``--clear``. Созданные записи регистрируются в журнале изменений и
попадают в экспортные архивы головного офиса.

Пример запуска:
    python -m tests.seed_data.seed_reference_1 --seed 42
"""

import argparse
import random
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from faker import Faker  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from internal_correspondence.core.constants import ScientificTaskType  # noqa: E402
from internal_correspondence.core.database import DatabaseManager  # noqa: E402
from internal_correspondence.orm.models import (  # noqa: E402
    AcademicTitle,
    AddedTask,
    Branch,
    Consumer,
    Country,
    Leader,
    ScientificTask,
    TerritorialUnit,
)
from internal_correspondence.services.change_tracking import (  # noqa: E402
    register_change_tracking,
)
from internal_correspondence.services.task_distribution_service import (  # noqa: E402
    NODE_BRANCH,
)
from tests.seed_common import (  # noqa: E402
    clear_database,
    parse_range,
    resolve_targets,
)

ACADEMIC_TITLES = [
    ("Д-р", "Доктор наук", "Доктора наук", "Доктору наук", 1),
    ("К-т", "Кандидат наук", "Кандидата наук", "Кандидату наук", 2),
    ("Доц.", "Доцент", "Доцента", "Доценту", 3),
    ("Проф.", "Профессор", "Профессора", "Профессору", 4),
]

DEFAULT_UNITS = 5
DEFAULT_BRANCHES_PER_UNIT = 2
DEFAULT_COUNTRIES = (30, 40)
DEFAULT_CONSUMERS = 10
DEFAULT_LEADERS = 5
DEFAULT_TASKS = 240

# Число филиалов-получателей одной задачи: задачи пересекаются между филиалами
TASK_BRANCH_COUNT = (1, 3)

# Доли сроков действия задач: (начало, конец, вес доли от общего числа)
TASK_PERIOD_SPECS: Tuple[Tuple[date, Optional[date], int], ...] = (
    (date(2025, 1, 1), date(2025, 12, 31), 2),  # треть
    (date(2026, 1, 1), date(2026, 12, 31), 2),  # треть
    (date(2025, 10, 1), date(2026, 9, 30), 1),  # 1/6
    (date(2025, 10, 1), None, 1),  # 1/6, без срока окончания
)


class ReferenceSeedError(Exception):
    """Ошибка наполнения базы справочными данными головного офиса."""


def build_task_periods(
    total: int, specs: Sequence[Tuple[date, Optional[date], int]] = TASK_PERIOD_SPECS,
) -> List[Tuple[date, Optional[date]]]:
    """Разворачивает доли сроков действия в список (начало, конец) задач.

    Доли задаются целыми весами (1/3, 1/3, 1/6, 1/6 — веса 1,1,1,1 не
    подойдут: приводим к общему знаменателю). Остаток от деления
    распределяется по периодам с начала списка.
    """
    weight_sum = sum(weight for _, _, weight in specs)
    periods: List[Tuple[date, Optional[date]]] = []
    allocated = 0
    for index, (start, end, weight) in enumerate(specs):
        if index == len(specs) - 1:
            count = total - allocated
        else:
            count = total * weight // weight_sum
            allocated += count
        periods.extend((start, end) for _ in range(count))
    return periods


def _build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Наполнение базы справочными данными головного офиса.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-url", help="URL базы данных (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--storage", help="Каталог файлового хранилища (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--units", type=int, default=DEFAULT_UNITS,
        help="Количество территориальных единиц",
    )
    parser.add_argument(
        "--branches-per-unit", type=int, default=DEFAULT_BRANCHES_PER_UNIT,
        help="Количество филиалов в территориальной единице",
    )
    parser.add_argument(
        "--countries", type=parse_range, default=DEFAULT_COUNTRIES,
        help="Количество стран (N-M)",
    )
    parser.add_argument(
        "--consumers", type=int, default=DEFAULT_CONSUMERS,
        help="Количество потребителей научных материалов",
    )
    parser.add_argument(
        "--leaders", type=int, default=DEFAULT_LEADERS,
        help="Количество руководителей",
    )
    parser.add_argument(
        "--tasks", type=int, default=DEFAULT_TASKS,
        help="Количество научных задач",
    )
    parser.add_argument(
        "--seed", type=int, help="Зерно генератора для воспроизводимых данных"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Удалить существующие данные перед наполнением",
    )
    return parser


def create_reference_data(
    session: Session, fake: Faker, args: argparse.Namespace
) -> Dict[str, int]:
    """Создаёт справочники головного офиса; возвращает статистику."""
    units = [
        TerritorialUnit(id=f"TU-{index:03d}", name=fake.region())
        for index in range(1, args.units + 1)
    ]
    session.add_all(units)

    branches: List[Branch] = []
    branch_index = 1
    for unit in units:
        for _ in range(args.branches_per_unit):
            company = (
                fake.company().replace("«", "").replace("»", "").replace('"', "").strip()
            )
            branches.append(
                Branch(
                    id=f"BR-{branch_index:03d}",
                    name=f"Филиал «{company}»",
                    short_name=f"Ф-{branch_index}",
                    territorial_unit_id=unit.id,
                )
            )
            branch_index += 1
    session.add_all(branches)

    used_codes = set()
    countries = []
    for _ in range(random.randint(*args.countries)):
        code = fake.unique.country_code(representation="alpha-3")
        if code in used_codes:
            continue
        used_codes.add(code)
        countries.append(Country(id=code, name=fake.country()))
    session.add_all(countries)

    session.add_all(
        AcademicTitle(
            id=title_id,
            name=name,
            genitive=genitive,
            dative=dative,
            sort_order=order,
        )
        for title_id, name, genitive, dative, order in ACADEMIC_TITLES
    )
    session.add_all(
        Consumer(
            id=f"CONS-{index:03d}",
            short_name=f"Потр-{index}",
            name=f"{fake.company()} ({fake.city()})",
        )
        for index in range(1, args.consumers + 1)
    )
    session.add_all(
        Leader(id=f"LEAD-{index:03d}") for index in range(1, args.leaders + 1)
    )

    task_periods = build_task_periods(args.tasks)
    tasks = []
    for index, (start, end) in enumerate(task_periods, start=1):
        tasks.append(
            ScientificTask(
                id=f"TASK-{index:04d}",
                name=f"Научная задача «{fake.catch_phrase()}»",
                type=(
                    ScientificTaskType.MAIN.value
                    if index % 2
                    else ScientificTaskType.ADDITIONAL.value
                ),
                start_date=start,
                end_date=end,
                comment=fake.sentence(nb_words=10)[:300],
                partial_threshold=fake.random_int(30, 70),
                full_threshold=fake.random_int(80, 100),
            )
        )
    session.add_all(tasks)

    # Случайное распределение с пересечениями: каждая задача назначается
    # 1-3 филиалам, поэтому филиалы получают десятки задач, а часть задач
    # оказывается общей для нескольких филиалов.
    session.add_all(
        AddedTask(
            task_id=task.id,
            node_type=NODE_BRANCH,
            node_id=branch.id,
        )
        for task in tasks
        for branch in random.sample(
            branches, k=min(len(branches), random.randint(*TASK_BRANCH_COUNT))
        )
    )

    session.flush()
    return {
        "territorial_units": len(units),
        "branches": len(branches),
        "countries": len(countries),
        "academic_titles": len(ACADEMIC_TITLES),
        "consumers": args.consumers,
        "leaders": args.leaders,
        "tasks": len(tasks),
    }


_REFERENCE_TABLES = (TerritorialUnit, Branch, Country, AcademicTitle, Consumer, Leader)


def _print_statistics(session: Session, stats: Dict[str, int]) -> None:
    """Выводит количество созданных записей."""
    print("Создано справочных данных головного офиса:")
    for title, key in (
        ("Территориальные единицы", "territorial_units"),
        ("Филиалы", "branches"),
        ("Страны", "countries"),
        ("Научные звания", "academic_titles"),
        ("Потребители", "consumers"),
        ("Руководители", "leaders"),
        ("Научные задачи", "tasks"),
    ):
        print(f"  {title}: {stats[key]}")
    print("Итого в базе:")
    for title, model in (
        ("Территориальные единицы", TerritorialUnit),
        ("Филиалы", Branch),
        ("Страны", Country),
        ("Научные звания", AcademicTitle),
        ("Потребители", Consumer),
        ("Руководители", Leader),
        ("Научные задачи", ScientificTask),
        ("Назначения задач", AddedTask),
    ):
        print(f"  {title}: {session.query(model).count()}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа скрипта наполнения справочными данными головного офиса."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.units < 1 or args.branches_per_unit < 1:
        parser.error("Территориальные единицы и филиалы должны быть в количестве >= 1")
    if args.tasks < 1:
        parser.error("Количество научных задач должно быть >= 1")

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    fake = Faker("ru_RU")
    db_url, storage_root, _settings = resolve_targets(args)

    register_change_tracking()
    db_manager = DatabaseManager(db_url, PROJECT_ROOT)
    db_manager.create_tables()

    try:
        with db_manager.get_session() as session:
            if args.clear:
                clear_database(session)
                print("Существующие данные удалены.")
            existing = sum(session.query(model).count() for model in _REFERENCE_TABLES)
            if existing:
                raise ReferenceSeedError(
                    "База уже содержит справочные данные. Перезапустите с --clear, "
                    "чтобы не смешивать наборы."
                )
            stats = create_reference_data(session, fake, args)
            session.commit()
            _print_statistics(session, stats)
    finally:
        db_manager.close()

    print(f"База данных: {db_url}")
    print(f"Хранилище: {storage_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
