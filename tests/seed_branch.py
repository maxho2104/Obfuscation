"""Наполнение базы данных от имени филиала (фаза филиала).

Скрипт моделирует работу филиала за заданный период: создаёт (при
отсутствии) справочные значения, организационно-штатную структуру
филиала (отделы, рабочие группы, сотрудники), источники, научные
материалы и телеграммы по правилам нумерации:

- исходящие номера материалов (``ИСХ-NNNNN``) и телеграмм (``ТЛГ-NNNNN``)
  — отдельные годовые счётчики, цифры по порядку в течение года;
- номера разрешительных документов (``РАЗР-NNNNN``) — отдельный годовой
  счётчик;
- для типов «ОБРАЗЕЦ_ПРОДУКЦИИ» и «ТЕХНИЧЕСКИЙ_ДОКУМЕНТ» заполняются
  серийный номер, год выпуска и разрешительный документ, для образцов
  продукции — ещё стоимость.

Филиал задаётся параметром ``--branch`` (сокращённое наименование); если
он не указан или филиал в базе отсутствует — генерируется новый филиал.

Примеры запуска:
    python -m tests.seed_branch --branch Ф-1
    python -m tests.seed_branch --from 2026-09-01 --to 2026-09-30 \
        --materials-per-day 2-4 --telegrams-per-day 1-2 --with-files
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from faker import Faker  # noqa: E402
from sqlalchemy import Integer, cast, func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from internal_correspondence.core.constants import (  # noqa: E402
    MaterialType,
    ScientificTaskType,
    SourceType,
    TelegramType,
)
from internal_correspondence.core.database import DatabaseManager  # noqa: E402
from internal_correspondence.orm.models import (  # noqa: E402
    AcademicTitle,
    Branch,
    Consumer,
    Country,
    Department,
    Employee,
    Leader,
    ReportAddress,
    ScientificMaterial,
    ScientificTask,
    Source,
    Telegram,
    TerritorialUnit,
    WorkGroupMembership,
    WorkingGroup,
)
from internal_correspondence.services.change_tracking import (  # noqa: E402
    register_change_tracking,
)
from tests.seed_common import (  # noqa: E402
    YearlyCounter,
    attach_file,
    clear_database,
    default_period,
    document_files_subdirectory,
    new_uuid,
    parse_date,
    parse_range,
    random_dates,
    resolve_targets,
)

POSITIONS = [
    "Начальник отдела",
    "Заместитель начальника отдела",
    "Начальник лаборатории",
    "Ведущий научный сотрудник",
    "Старший научный сотрудник",
    "Научный сотрудник",
    "Младший научный сотрудник",
    "Инженер-исследователь",
    "Ведущий специалист",
    "Аналитик",
]

ACADEMIC_TITLES = [
    ("Д-р", "Доктор наук", "Доктора наук", "Доктору наук", 1),
    ("К-т", "Кандидат наук", "Кандидата наук", "Кандидату наук", 2),
    ("Доц.", "Доцент", "Доцента", "Доценту", 3),
    ("Проф.", "Профессор", "Профессора", "Профессору", 4),
    ("Акад.", "Академик", "Академика", "Академику", 5),
]

DEPARTMENT_NAMES = [
    "Научно-технический отдел",
    "Отдел математического моделирования",
    "Отдел экспериментальных исследований",
    "Отдел информационных систем",
    "Отдел перспективных разработок",
    "Лаборатория испытаний",
    "Отдел анализа данных",
    "Планово-экономический отдел",
]

MATERIAL_NAME_TEMPLATES = [
    "Отчёт о {topic}",
    "Обзор {topic}",
    "Методика {topic}",
    "Результаты исследований: {topic}",
    "Аналитическая справка: {topic}",
    "Техническое описание: {topic}",
]

TELEGRAM_NAME_TEMPLATES = {
    TelegramType.THEMATIC.value: [
        "Тематическая телеграмма: {topic}",
        "Сведения по теме «{topic}»",
    ],
    TelegramType.PROGRESS_REPORT.value: [
        "О ходе работ по теме «{topic}»",
        "О состоянии работ по теме «{topic}»",
    ],
    TelegramType.RESULTS_REPORT.value: [
        "О достигнутых результатах по теме «{topic}»",
        "Об итогах работ по теме «{topic}»",
    ],
}

# Типы материалов, для которых заполняются реквизиты разрешительного документа
PERMIT_MATERIAL_TYPES = {
    MaterialType.PRODUCT_SAMPLE.value,
    MaterialType.TECHNICAL_DOCUMENT.value,
}

DEFAULT_MATERIALS_PER_DAY = (1, 3)
DEFAULT_TELEGRAMS_PER_DAY = (0, 2)
DEFAULT_DEPARTMENTS = (2, 4)
DEFAULT_WORKGROUPS = (1, 3)
DEFAULT_EMPLOYEES = (3, 8)
DEFAULT_SOURCES = 10


class BranchSeedError(Exception):
    """Ошибка наполнения базы данными филиала."""


def _build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Наполнение базы данных от имени филиала.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-url", help="URL базы данных (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--storage", help="Каталог файлового хранилища (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--branch",
        help="Сокращённое наименование филиала; если филиала нет в базе — "
        "он будет создан (по умолчанию генерируется новый филиал)",
    )
    parser.add_argument(
        "--from",
        dest="date_from",
        type=parse_date,
        help="Начало периода генерации (ГГГГ-ММ-ДД)",
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        type=parse_date,
        help="Конец периода генерации (ГГГГ-ММ-ДД)",
    )
    parser.add_argument(
        "--materials-per-day",
        type=parse_range,
        default=DEFAULT_MATERIALS_PER_DAY,
        help="Количество научных материалов в сутки (N-M)",
    )
    parser.add_argument(
        "--telegrams-per-day",
        type=parse_range,
        default=DEFAULT_TELEGRAMS_PER_DAY,
        help="Количество телеграмм в сутки (N-M)",
    )
    parser.add_argument(
        "--sources",
        type=int,
        default=DEFAULT_SOURCES,
        help="Количество источников филиала",
    )
    parser.add_argument(
        "--departments",
        type=parse_range,
        default=DEFAULT_DEPARTMENTS,
        help="Количество отделов филиала (N-M)",
    )
    parser.add_argument(
        "--workgroups",
        type=parse_range,
        default=DEFAULT_WORKGROUPS,
        help="Количество рабочих групп в отделе (N-M)",
    )
    parser.add_argument(
        "--employees",
        type=parse_range,
        default=DEFAULT_EMPLOYEES,
        help="Количество сотрудников отдела (N-M)",
    )
    parser.add_argument(
        "--seed", type=int, help="Зерно генератора для воспроизводимых данных"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Удалить существующие данные перед наполнением",
    )
    parser.add_argument(
        "--with-files", action="store_true", help="Создавать файлы-вложения в хранилище"
    )
    return parser


def _ensure_reference_data(
    session: Session, fake: Faker, branches_count: int, today: date
) -> Dict[str, list]:
    """Создаёт справочники, если они отсутствуют в базе."""
    if session.query(TerritorialUnit).count() == 0:
        units = [
            TerritorialUnit(id=f"TU-{index:03d}", name=fake.region())
            for index in range(1, max(2, branches_count) + 1)
        ]
        session.add_all(units)
    if session.query(Country).count() == 0:
        used_codes = set()
        countries = []
        for index in range(1, 11):
            code = fake.country_code(representation="alpha-3")
            if code in used_codes:
                code = f"C{index:02d}"
            used_codes.add(code)
            countries.append(Country(id=code, name=fake.country()))
        session.add_all(countries)
    if session.query(AcademicTitle).count() == 0:
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
    if session.query(Consumer).count() == 0:
        session.add_all(
            Consumer(
                id=f"CONS-{index:03d}",
                short_name=f"Потр-{index}",
                name=f"{fake.company()} ({fake.city()})",
            )
            for index in range(1, 7)
        )
    if session.query(Leader).count() == 0:
        session.add_all(Leader(id=f"LEAD-{index:03d}") for index in range(1, 5))
    if session.query(ScientificTask).count() == 0:
        tasks = []
        for index in range(1, 7):
            start = fake.date_between_dates(
                date_start=today - timedelta(days=730), date_end=today
            )
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
                    end_date=start + timedelta(days=365),
                    comment=fake.sentence(nb_words=10)[:300],
                    partial_threshold=fake.random_int(30, 70),
                    full_threshold=fake.random_int(80, 100),
                )
            )
        session.add_all(tasks)
    session.flush()
    return {
        "territorial_units": list(session.query(TerritorialUnit)),
        "countries": list(session.query(Country)),
        "academic_titles": list(session.query(AcademicTitle)),
        "consumers": list(session.query(Consumer)),
        "leaders": list(session.query(Leader)),
        "tasks": list(session.query(ScientificTask)),
    }


def _resolve_branch(
    session: Session, fake: Faker, branch_arg: Optional[str]
) -> Branch:
    """Возвращает существующий филиал или создаёт новый."""
    if branch_arg:
        existing = (
            session.query(Branch).filter(Branch.short_name == branch_arg).one_or_none()
        )
        if existing is not None:
            return existing

    company = (
        fake.company().replace("«", "").replace("»", "").replace('"', "").strip()
    )
    if branch_arg:
        short_name = branch_arg
    else:
        used = {name for (name,) in session.query(Branch.short_name)}
        index = 1
        while f"Ф-{index}" in used:
            index += 1
        short_name = f"Ф-{index}"
    unit = session.query(TerritorialUnit).order_by(TerritorialUnit.id).first()
    index = session.query(Branch).count() + 1
    branch = Branch(
        id=f"BR-{index:03d}",
        name=f"Филиал «{company}»",
        short_name=short_name,
        territorial_unit_id=unit.id if unit else None,
    )
    session.add(branch)
    session.flush()
    return branch


def _create_branch_structure(
    fake: Faker,
    branch: Branch,
    academic_titles: Sequence,
    departments_range: tuple,
    workgroups_range: tuple,
    employees_range: tuple,
    today: date,
) -> None:
    """Создаёт отделы, рабочие группы и сотрудников филиала."""
    for dept_index in range(random.randint(*departments_range)):
        offset = sum(ord(char) for char in branch.id)
        department = Department(
            name=DEPARTMENT_NAMES[(dept_index + offset) % len(DEPARTMENT_NAMES)],
            short_name=f"О-{dept_index + 1}",
            active=fake.boolean(chance_of_getting_true=90),
        )
        branch.departments.append(department)

        groups = [
            WorkingGroup(
                name=f"Рабочая группа «{fake.catch_phrase()}»",
                comment=fake.sentence(nb_words=6)[:200],
                active=fake.boolean(chance_of_getting_true=85),
            )
            for _ in range(random.randint(*workgroups_range))
        ]
        for group in groups:
            department.workgroups.append(group)

        for _ in range(random.randint(*employees_range)):
            gender = random.choice(("male", "female"))
            last_name = (
                fake.last_name_male() if gender == "male" else fake.last_name_female()
            )
            first_name = (
                fake.first_name_male()
                if gender == "male"
                else fake.first_name_female()
            )
            middle_name = (
                fake.middle_name_male()
                if gender == "male"
                else fake.middle_name_female()
            )
            employee = Employee(
                last_name=last_name,
                first_name=first_name,
                middle_name=middle_name,
                position=random.choice(POSITIONS),
                active=fake.boolean(chance_of_getting_true=90),
                academic_title=(
                    fake.random_element(academic_titles)
                    if fake.boolean(chance_of_getting_true=35)
                    else None
                ),
            )
            if groups and fake.boolean(chance_of_getting_true=60):
                group = fake.random_element(groups)
                start = fake.date_between_dates(
                    date_start=today - timedelta(days=730), date_end=today
                )
                employee.workgroup_memberships.append(
                    WorkGroupMembership(
                        working_group=group,
                        start_date=start,
                        end_date=(
                            start + timedelta(days=365)
                            if fake.boolean(chance_of_getting_true=30)
                            else None
                        ),
                    )
                )
            department.employees.append(employee)


def _create_sources(
    fake: Faker, count: int, existing: int, branch: Branch
) -> List[Source]:
    """Создаёт источники филиала с UUID-идентификаторами и индексами.

    Индекс уникален в сети: порядковый номер филиала задаёт старшие
    разряды («SRC-2NNNN» для BR-002), порядковый номер источника —
    младшие. Так источники разных филиалов не конфликтуют в базе
    головного офиса.
    """
    branch_seq = int(branch.id.rsplit("-", 1)[1])
    return [
        Source(
            id=new_uuid(),
            index=f"SRC-{branch_seq * 10000 + existing + offset:05d}",
            type=(
                SourceType.EXPERIMENTAL_EQUIPMENT.value
                if fake.boolean()
                else SourceType.SCIENTIFIC_WORK.value
            ),
            comment=fake.sentence(nb_words=8)[:200],
        )
        for offset in range(1, count + 1)
    ]


def _align_counters(session: Session, counters: Dict[str, YearlyCounter]) -> None:
    """Продолжает счётчики за максимумом существующих номеров в базе.

    В одной базе могут соседствовать данные нескольких филиалов, а составной
    уникальный индекс (номер, дата) глобален — поэтому нумерация нового
    филиала продолжает общую последовательность года, а не начинается с 1.
    """
    specs = (
        (
            ScientificMaterial.outgoing_date,
            ScientificMaterial.outgoing_number,
            counters["materials"],
        ),
        (Telegram.outgoing_date, Telegram.outgoing_number, counters["telegrams"]),
        (
            ScientificMaterial.outgoing_date,
            ScientificMaterial.permit_number,
            counters["permits"],
        ),
    )
    for date_column, number_column, counter in specs:
        year_expr = func.extract("year", date_column)
        # +2: позиция за дефисом после префикса («ИСХ-00001»: цифры с 5-й).
        number_expr = func.substr(number_column, len(counter.prefix) + 2)
        rows = (
            session.query(year_expr, func.max(cast(number_expr, Integer)))
            .filter(number_column.isnot(None))
            .group_by(year_expr)
            .all()
        )
        for year, maximum in rows:
            if maximum:
                counter.basis(int(year), int(maximum) + 1)


def _pick_participants(fake: Faker, branch: Branch) -> Dict[str, list]:
    """Выбирает отделы, рабочие группы и сотрудников документа филиала."""
    departments = list(branch.departments)
    picked_departments = (
        random.sample(departments, k=min(len(departments), fake.random_int(1, 3)))
        if departments
        else []
    )
    employees = [
        employee
        for department in picked_departments
        for employee in department.employees
    ]
    workgroups = [
        group for department in picked_departments for group in department.workgroups
    ]
    return {
        "departments": picked_departments,
        # Сотрудники — обязательное поле документа: минимум один участник.
        "employees": (
            random.sample(employees, k=min(len(employees), fake.random_int(1, 3)))
            if employees
            else []
        ),
        "workgroups": (
            random.sample(workgroups, k=min(len(workgroups), fake.random_int(0, 2)))
            if workgroups
            else []
        ),
    }


def _create_material(
    fake: Faker,
    branch: Branch,
    day: date,
    counters: Dict[str, YearlyCounter],
    countries: Sequence,
    consumers: Sequence,
    tasks: Sequence,
    sources: Sequence,
) -> ScientificMaterial:
    """Создаёт один научный материал за дату по правилам нумерации."""
    material_type = fake.random_element(list(MaterialType)).value
    topic = fake.catch_phrase().lower()
    participants = _pick_participants(fake, branch)

    material = ScientificMaterial(
        type=material_type,
        outgoing_number=counters["materials"].next(day),
        outgoing_date=day,
        name=fake.random_element(MATERIAL_NAME_TEMPLATES).format(topic=topic)[:500],
        comment=fake.sentence(nb_words=12)[:300],
        # Страны — обязательное поле документа: минимум одна.
        countries=random.sample(
            list(countries), k=min(len(countries), fake.random_int(1, 2))
        ),
        consumer_id=(
            fake.random_element(list(consumers)).id
            if fake.boolean(chance_of_getting_true=60)
            else None
        ),
        branch_id=branch.id,
        tasks=(
            random.sample(list(tasks), k=fake.random_int(1, min(2, len(tasks))))
            if tasks
            else []
        ),
        departments=participants["departments"],
        employees=participants["employees"],
        workgroups=participants["workgroups"],
        sources=(
            random.sample(list(sources), k=fake.random_int(0, 2)) if sources else []
        ),
    )
    if material_type in PERMIT_MATERIAL_TYPES:
        material.serial_number = f"SN-{new_uuid().hex[:12].upper()}"
        material.release_year = fake.random_int(max(2010, day.year - 10), day.year)
        material.permit_number = counters["permits"].next(day)
        material.permit_date = day
        if fake.boolean(chance_of_getting_true=50):
            material.permit_date = day - timedelta(days=1)
        if material_type == MaterialType.PRODUCT_SAMPLE.value:
            material.cost = round(random.uniform(1000, 500000), 2)
    return material


def _create_telegram(
    session: Session,
    fake: Faker,
    branch: Branch,
    day: date,
    counters: Dict[str, YearlyCounter],
    countries: Sequence,
    tasks: Sequence,
    sources: Sequence,
    leaders: Sequence,
) -> Telegram:
    """Создаёт одну телеграмму за дату; адресация — без даты доклада."""
    telegram_type = fake.random_element(list(TelegramType)).value
    topic = fake.catch_phrase().lower()
    participants = _pick_participants(fake, branch)

    telegram = Telegram(
        type=telegram_type,
        outgoing_number=counters["telegrams"].next(day),
        outgoing_date=day,
        name=fake.random_element(TELEGRAM_NAME_TEMPLATES[telegram_type]).format(
            topic=topic
        )[:500],
        comment=fake.sentence(nb_words=12)[:300],
        # Страны — обязательное поле документа: минимум одна.
        countries=[fake.random_element(list(countries))],
        branch_id=branch.id,
        tasks=(
            random.sample(list(tasks), k=fake.random_int(1, min(2, len(tasks))))
            if tasks
            else []
        ),
        departments=participants["departments"],
        employees=participants["employees"],
        workgroups=participants["workgroups"],
        sources=(
            random.sample(list(sources), k=fake.random_int(0, 2)) if sources else []
        ),
    )
    active_leaders = [leader for leader in leaders if leader.active]
    if active_leaders:
        session.add(
            ReportAddress(
                report_date=None,
                telegram=telegram,
                leader_id=fake.random_element(active_leaders).id,
            )
        )
    return telegram


def _seed(
    session: Session,
    fake: Faker,
    args: argparse.Namespace,
    storage_root: Path,
    today: date,
) -> Branch:
    """Создаёт данные филиала за период; возвращает филиал."""
    references = _ensure_reference_data(session, fake, 3, today)
    branch = _resolve_branch(session, fake, args.branch)
    if not branch.departments:
        _create_branch_structure(
            fake,
            branch,
            references["academic_titles"],
            args.departments,
            args.workgroups,
            args.employees,
            today,
        )
    session.flush()

    existing_sources = session.query(Source).count()
    sources = _create_sources(fake, args.sources, existing_sources, branch)
    session.add_all(sources)
    session.flush()

    counters = {
        "materials": YearlyCounter("ИСХ"),
        "telegrams": YearlyCounter("ТЛГ"),
        "permits": YearlyCounter("РАЗР"),
    }
    _align_counters(session, counters)

    created_documents = []
    for day in random_dates(args.date_from, args.date_to):
        for _ in range(random.randint(*args.materials_per_day)):
            material = _create_material(
                fake,
                branch,
                day,
                counters,
                references["countries"],
                references["consumers"],
                references["tasks"],
                sources,
            )
            session.add(material)
            created_documents.append(material)
        for _ in range(random.randint(*args.telegrams_per_day)):
            telegram = _create_telegram(
                session,
                fake,
                branch,
                day,
                counters,
                references["countries"],
                references["tasks"],
                sources,
                references["leaders"],
            )
            session.add(telegram)
            created_documents.append(telegram)
    session.flush()

    if args.with_files:
        for document in created_documents:
            if fake.boolean(chance_of_getting_true=25):
                attach_file(
                    session,
                    storage_root,
                    document,
                    document_files_subdirectory(document),
                )

    session.commit()
    return branch


def _print_statistics(session: Session, branch: Branch) -> None:
    """Выводит количество созданных записей по основным сущностям."""
    entities = [
        ("Территориальные единицы", TerritorialUnit),
        ("Филиалы", Branch),
        ("Страны", Country),
        ("Научные звания", AcademicTitle),
        ("Научные задачи", ScientificTask),
        ("Потребители", Consumer),
        ("Руководители", Leader),
        ("Источники", Source),
        ("Отделы", Department),
        ("Рабочие группы", WorkingGroup),
        ("Сотрудники", Employee),
        ("Научные материалы", ScientificMaterial),
        ("Телеграммы", Telegram),
        ("Адреса докладов", ReportAddress),
    ]
    print("Данные в базе:")
    for title, model in entities:
        print(f"  {title}: {session.query(model).count()}")
    print(f"Филиал: {branch.id} — {branch.name} ({branch.short_name})")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа скрипта наполнения данными филиала."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    default_from, default_to = default_period(date.today())
    args.date_from = args.date_from or default_from
    args.date_to = args.date_to or default_to
    if args.date_to < args.date_from:
        parser.error("Конец периода не может быть раньше начала")

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

            branch = _seed(session, fake, args, storage_root, date.today())
            _print_statistics(session, branch)
    finally:
        db_manager.close()

    print(f"База данных: {db_url}")
    print(f"Хранилище: {storage_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
