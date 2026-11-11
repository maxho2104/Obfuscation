"""Наполнение базы данных случайно сгенерированными данными.

Скрипт создаёт согласованный набор справочников, организационно-штатной
структуры, научных материалов, телеграмм, оценок и адресации докладов.
Данные генерируются библиотекой Faker (локаль ru_RU) с учётом ограничений
ORM-моделей: уникальности исходящих номеров и связей между сущностями.

Примеры запуска:
    python -m tests.seed_data
    python tests/seed_data.py --clear --materials 200 --telegrams 100 --seed 42
    python tests/seed_data.py --with-files --storage "D:/Projects/Obfuscation/Файловое хранилище"
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
from sqlalchemy.orm import Session  # noqa: E402

from internal_correspondence.core.constants import (  # noqa: E402
    FILES_DIR,
    MATERIAL_FILES_DIR,
    TELEGRAM_FILES_DIR,
    EvaluationValue,
    MaterialType,
    ScientificTaskType,
    SourceType,
    TelegramReportType,
    TelegramType,
)
from internal_correspondence.core.database import DatabaseManager  # noqa: E402
from internal_correspondence.core.settings import AppSettings, SettingsManager  # noqa: E402
from internal_correspondence.orm.base import Base  # noqa: E402
from internal_correspondence.orm.models import (  # noqa: E402
    AcademicTitle,
    Branch,
    Consumer,
    Country,
    Department,
    Employee,
    Evaluation,
    EvaluationList,
    FileRecord,
    Leader,
    ReportAddress,
    ScientificMaterial,
    ScientificTask,
    Source,
    Telegram,
    TerritorialUnit,
    WorkingGroup,
)
from internal_correspondence.services.change_tracking import (  # noqa: E402
    register_change_tracking,
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

DEFAULT_BRANCHES = 3
DEFAULT_MATERIALS = 120
DEFAULT_TELEGRAMS = 60
HISTORY_YEARS = 3


def _build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Наполнение базы данных случайно сгенерированными данными.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-url", help="URL базы данных (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--storage", help="Каталог файлового хранилища (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--branches", type=int, default=DEFAULT_BRANCHES, help="Количество филиалов"
    )
    parser.add_argument(
        "--materials",
        type=int,
        default=DEFAULT_MATERIALS,
        help="Количество научных материалов",
    )
    parser.add_argument(
        "--telegrams", type=int, default=DEFAULT_TELEGRAMS, help="Количество телеграмм"
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


def _resolve_targets(args: argparse.Namespace) -> tuple[str, Path, AppSettings]:
    """Определяет URL базы данных, каталог хранилища и настройки приложения."""
    settings_manager = SettingsManager(PROJECT_ROOT)
    settings: AppSettings = (
        settings_manager.load() if settings_manager.exists else AppSettings()
    )

    db_url = args.db_url or settings.db_url
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", "", 1))
        if not db_path.is_absolute():
            db_url = f"sqlite:///{(PROJECT_ROOT / db_path).as_posix()}"

    storage = Path(args.storage) if args.storage else None
    if storage is None:
        storage = (
            Path(settings.storage_path)
            if settings.storage_path
            else PROJECT_ROOT / "Файловое хранилище"
        )

    return db_url, storage, settings


def _clear_database(session: Session) -> None:
    """Удаляет все записи из всех таблиц базы данных."""
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()


def _create_territorial_units(fake: Faker, count: int) -> List[TerritorialUnit]:
    """Создаёт справочник территориальных единиц."""
    units: List[TerritorialUnit] = []
    used_names = set()
    for index in range(1, count + 1):
        name = fake.region()
        if name in used_names:
            name = f"{name} ({index})"
        used_names.add(name)
        units.append(TerritorialUnit(id=f"TU-{index:03d}", name=name))
    return units


def _create_branches(
    fake: Faker, territorial_units: Sequence[TerritorialUnit], count: int
) -> List[Branch]:
    """Создаёт филиалы, привязанные к территориальным единицам."""
    branches: List[Branch] = []
    for index in range(1, count + 1):
        unit = territorial_units[(index - 1) % len(territorial_units)]
        company = (
            fake.company().replace("«", "").replace("»", "").replace('"', "").strip()
        )
        branch_id = f"BR-{index:03d}"
        branches.append(
            Branch(
                id=branch_id,
                name=f"Филиал «{company}»",
                short_name=f"Ф-{index}",
                territorial_unit_id=unit.id,
            )
        )
    return branches


def _create_countries(fake: Faker, count: int) -> List[Country]:
    """Создаёт справочник стран с уникальными трёхбуквенными кодами."""
    countries: List[Country] = []
    used_codes = set()
    used_names = set()
    for index in range(1, count + 1):
        name = fake.country()
        if name in used_names:
            name = f"{name} ({index})"
        code = fake.country_code(representation="alpha-3")
        if code in used_codes:
            code = f"C{index:02d}"
        used_names.add(name)
        used_codes.add(code)
        countries.append(Country(id=code, name=name))
    return countries


def _create_academic_titles() -> List[AcademicTitle]:
    """Создаёт справочник научных званий."""
    return [
        AcademicTitle(
            id=title_id,
            name=name,
            genitive=genitive,
            dative=dative,
            sort_order=order,
        )
        for title_id, name, genitive, dative, order in ACADEMIC_TITLES
    ]


def _create_consumers(fake: Faker, count: int) -> List[Consumer]:
    """Создаёт справочник потребителей."""
    consumers: List[Consumer] = []
    for index in range(1, count + 1):
        consumers.append(
            Consumer(
                id=f"CONS-{index:03d}",
                short_name=f"Потр-{index}",
                name=f"{fake.company()} ({fake.city()})",
            )
        )
    return consumers


def _create_leaders(count: int) -> List[Leader]:
    """Создаёт справочник руководителей, которым докладываются телеграммы."""
    leaders: List[Leader] = []
    for index in range(1, count + 1):
        leaders.append(
            Leader(id=f"LEAD-{index:03d}", active=index <= max(1, count - 1))
        )
    return leaders


def _create_sources(fake: Faker, count: int) -> List[Source]:
    """Создаёт справочник источников научных материалов."""
    source_types = [
        SourceType.EXPERIMENTAL_EQUIPMENT.value,
        SourceType.SCIENTIFIC_WORK.value,
    ]
    sources: List[Source] = []
    for index in range(1, count + 1):
        sources.append(
            Source(
                id=f"SRC-{index:03d}",
                type=random.choice(source_types),
                comment=fake.sentence(nb_words=8)[:200],
            )
        )
    return sources


def _create_tasks(fake: Faker, count: int, today: date) -> List[ScientificTask]:
    """Создаёт научные задачи со сроками выполнения."""
    tasks: List[ScientificTask] = []
    task_types = [ScientificTaskType.MAIN.value, ScientificTaskType.ADDITIONAL.value]
    for index in range(1, count + 1):
        start = fake.date_between_dates(
            date_start=today - timedelta(days=365 * HISTORY_YEARS), date_end=today
        )
        end = start + timedelta(days=fake.random_int(180, 365 * 2))
        tasks.append(
            ScientificTask(
                id=f"TASK-{index:04d}",
                name=f"Научная задача «{fake.catch_phrase()}»",
                type=task_types[index % len(task_types)],
                start_date=start,
                end_date=end,
                comment=fake.sentence(nb_words=10)[:300],
                partial_threshold=fake.random_int(30, 70),
                full_threshold=fake.random_int(80, 100),
            )
        )
    return tasks


def _create_oshm(
    fake: Faker,
    branches: Sequence[Branch],
    academic_titles: Sequence[AcademicTitle],
    today: date,
) -> None:
    """Создаёт отделы, рабочие группы и сотрудников для каждого филиала."""
    for branch_index, branch in enumerate(branches):
        departments_count = fake.random_int(2, 4)
        for dept_index in range(departments_count):
            name = DEPARTMENT_NAMES[
                (branch_index * 2 + dept_index) % len(DEPARTMENT_NAMES)
            ]
            department = Department(
                name=name,
                short_name=f"О-{dept_index + 1}",
                active=fake.boolean(chance_of_getting_true=90),
            )
            branch.departments.append(department)

            for _ in range(fake.random_int(1, 3)):
                department.workgroups.append(
                    WorkingGroup(
                        name=f"Рабочая группа «{fake.catch_phrase()}»",
                        comment=fake.sentence(nb_words=6)[:200],
                        active=fake.boolean(chance_of_getting_true=85),
                    )
                )

            for _ in range(fake.random_int(3, 8)):
                gender = random.choice(("male", "female"))
                last_name = (
                    fake.last_name_male()
                    if gender == "male"
                    else fake.last_name_female()
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
                title = (
                    fake.random_element(academic_titles)
                    if fake.boolean(chance_of_getting_true=35)
                    else None
                )
                group = (
                    fake.random_element(department.workgroups)
                    if fake.boolean(chance_of_getting_true=60)
                    else None
                )
                start = fake.date_between_dates(
                    date_start=today - timedelta(days=365 * HISTORY_YEARS),
                    date_end=today,
                )
                end = (
                    start + timedelta(days=fake.random_int(90, 365 * 2))
                    if group
                    else None
                )
                department.employees.append(
                    Employee(
                        last_name=last_name,
                        first_name=first_name,
                        middle_name=middle_name,
                        position=random.choice(POSITIONS),
                        active=fake.boolean(chance_of_getting_true=90),
                        academic_title=title,
                        working_group=group,
                        workgroup_start_date=start if group else None,
                        workgroup_end_date=end,
                    )
                )


def _pick_document_relations(
    fake: Faker,
    branch: Branch,
    sources: Sequence[Source],
) -> Dict[str, list]:
    """Выбирает подразделения, сотрудников, рабочие группы и источники документа."""
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
        "employees": random.sample(
            employees, k=min(len(employees), fake.random_int(0, 3))
        )
        if employees
        else [],
        "workgroups": random.sample(
            workgroups, k=min(len(workgroups), fake.random_int(0, 2))
        )
        if workgroups
        else [],
        "sources": random.sample(
            list(sources), k=min(len(sources), fake.random_int(0, 2))
        )
        if sources
        else [],
    }


def _create_materials(
    fake: Faker,
    count: int,
    branches: Sequence[Branch],
    countries: Sequence[Country],
    consumers: Sequence[Consumer],
    tasks: Sequence[ScientificTask],
    sources: Sequence[Source],
    today: date,
) -> List[ScientificMaterial]:
    """Создаёт научные материалы с распределением по филиалам."""
    material_types = [item.value for item in MaterialType]
    materials: List[ScientificMaterial] = []

    for index in range(1, count + 1):
        branch = branches[(index - 1) % len(branches)]
        outgoing_date = fake.date_between_dates(
            date_start=today - timedelta(days=365 * HISTORY_YEARS),
            date_end=today,
        )
        has_incoming = fake.boolean(chance_of_getting_true=40)
        incoming_date = (
            min(outgoing_date + timedelta(days=fake.random_int(1, 60)), today)
            if has_incoming
            else None
        )
        topic = fake.catch_phrase().lower()
        relations = _pick_document_relations(fake, branch, sources)

        material = ScientificMaterial(
            type=fake.random_element(material_types),
            outgoing_number=f"ИСХ-{index:05d}",
            outgoing_date=outgoing_date,
            name=fake.random_element(MATERIAL_NAME_TEMPLATES).format(topic=topic)[:500],
            incoming_number=f"ВХ-{index:05d}" if has_incoming else None,
            incoming_date=incoming_date,
            serial_number=f"SN-{index:05d}",
            release_year=fake.random_int(2010, today.year),
            permit_number=f"РАЗР-{fake.random_int(1000, 9999)}"
            if fake.boolean(chance_of_getting_true=30)
            else None,
            cost=round(random.uniform(1000, 500000), 2)
            if fake.boolean(chance_of_getting_true=60)
            else None,
            comment=fake.sentence(nb_words=12)[:300],
            country_id=fake.random_element(countries).id
            if fake.boolean(chance_of_getting_true=50)
            else None,
            consumer_id=fake.random_element(consumers).id
            if fake.boolean(chance_of_getting_true=60)
            else None,
            branch_id=branch.id,
            tasks=random.sample(
                list(tasks), k=fake.random_int(1, min(2, len(tasks)))
            )
            if fake.boolean(chance_of_getting_true=70)
            else [],
            departments=relations["departments"],
            employees=relations["employees"],
            workgroups=relations["workgroups"],
            sources=relations["sources"],
        )
        materials.append(material)

    return materials


def _create_telegrams(
    session: Session,
    fake: Faker,
    count: int,
    branches: Sequence[Branch],
    countries: Sequence[Country],
    tasks: Sequence[ScientificTask],
    sources: Sequence[Source],
    leaders: Sequence[Leader],
    today: date,
) -> List[Telegram]:
    """Создаёт телеграммы и адресацию их доклада руководителям."""
    telegram_types = [item.value for item in TelegramType]
    report_types = [item.value for item in TelegramReportType]
    telegrams: List[Telegram] = []

    for index in range(1, count + 1):
        branch = branches[(index - 1) % len(branches)]
        telegram_type = fake.random_element(telegram_types)
        outgoing_date = fake.date_between_dates(
            date_start=today - timedelta(days=365 * HISTORY_YEARS),
            date_end=today,
        )
        has_incoming = fake.boolean(chance_of_getting_true=40)
        incoming_date = (
            min(outgoing_date + timedelta(days=fake.random_int(1, 30)), today)
            if has_incoming
            else None
        )
        topic = fake.catch_phrase().lower()
        relations = _pick_document_relations(fake, branch, sources)

        telegram = Telegram(
            type=telegram_type,
            outgoing_number=f"ТЛГ-{index:05d}",
            outgoing_date=outgoing_date,
            name=fake.random_element(TELEGRAM_NAME_TEMPLATES[telegram_type]).format(
                topic=topic
            )[:500],
            incoming_number=f"ВХ-ТЛГ-{index:05d}" if has_incoming else None,
            incoming_date=incoming_date,
            report_type=fake.random_element(report_types)
            if fake.boolean(chance_of_getting_true=70)
            else None,
            comment=fake.sentence(nb_words=12)[:300],
            country_id=fake.random_element(countries).id
            if fake.boolean(chance_of_getting_true=40)
            else None,
            branch_id=branch.id,
            tasks=random.sample(
                list(tasks), k=fake.random_int(1, min(2, len(tasks)))
            )
            if fake.boolean(chance_of_getting_true=70)
            else [],
            departments=relations["departments"],
            employees=relations["employees"],
            workgroups=relations["workgroups"],
            sources=relations["sources"],
        )

        if leaders and fake.boolean(chance_of_getting_true=35):
            session.add(
                ReportAddress(
                    report_date=min(
                        outgoing_date + timedelta(days=fake.random_int(0, 10)), today
                    ),
                    telegram=telegram,
                    leader_id=fake.random_element(leaders).id,
                )
            )

        telegrams.append(telegram)

    return telegrams


def _create_evaluations(
    fake: Faker,
    count: int,
    materials: Sequence[ScientificMaterial],
    telegrams: Sequence[Telegram],
    today: date,
) -> List[EvaluationList]:
    """Создаёт списки оценок с оценками, привязанными к документам."""
    values = [item.value for item in EvaluationValue]
    documents = list(materials) + list(telegrams)
    evaluation_lists: List[EvaluationList] = []

    for index in range(1, count + 1):
        evaluation_list = EvaluationList(
            number=f"ОЦ-{index:04d}",
            date=fake.date_between_dates(
                date_start=today - timedelta(days=365 * HISTORY_YEARS),
                date_end=today,
            ),
        )
        for _ in range(fake.random_int(3, 8)):
            evaluation = Evaluation(value=fake.random_element(values))
            for document in random.sample(
                documents, k=min(len(documents), fake.random_int(1, 4))
            ):
                if isinstance(document, ScientificMaterial):
                    evaluation.materials.append(document)
                else:
                    evaluation.telegrams.append(document)
            evaluation_list.evaluations.append(evaluation)
        evaluation_lists.append(evaluation_list)

    return evaluation_lists


def _attach_file(
    session: Session,
    fake: Faker,
    storage_root: Path,
    document,
    subdirectory: str,
) -> None:
    """Создаёт файл в хранилище и регистрирует его как вложение документа."""
    date_str = (
        document.outgoing_date.isoformat() if document.outgoing_date else "unknown"
    )
    relative_dir = (
        Path(FILES_DIR)
        / subdirectory
        / date_str
        / (document.outgoing_number or str(document.id))
    )
    target_dir = storage_root / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    name = f"Приложение-{fake.random_int(1, 999):03d}"
    target_path = target_dir / f"{name}.txt"
    target_path.write_text(
        f"{document.name}\n\nСгенерировано для тестирования.\n",
        encoding="utf-8",
    )

    record = FileRecord(name=name, extension="txt", path=relative_dir.as_posix())
    session.add(record)
    document.files.append(record)


def _seed(
    session: Session,
    fake: Faker,
    args: argparse.Namespace,
    storage_root: Path,
    today: date,
    preferred_branch_id: Optional[str] = None,
) -> None:
    """Создаёт полный набор связанных данных."""
    territorial_units = _create_territorial_units(fake, max(2, args.branches))
    branches = _create_branches(fake, territorial_units, args.branches)
    countries = _create_countries(fake, 10)
    academic_titles = _create_academic_titles()
    consumers = _create_consumers(fake, 6)
    leaders = _create_leaders(4)
    sources = _create_sources(fake, 12)
    tasks = _create_tasks(fake, max(2, args.branches), today)

    session.add_all(territorial_units)
    session.add_all(branches)
    session.add_all(countries)
    session.add_all(academic_titles)
    session.add_all(consumers)
    session.add_all(leaders)
    session.add_all(sources)
    session.add_all(tasks)
    session.flush()

    _create_oshm(fake, branches, academic_titles, today)
    session.flush()

    materials = _create_materials(
        fake, args.materials, branches, countries, consumers, tasks, sources, today
    )
    telegrams = _create_telegrams(
        session,
        fake,
        args.telegrams,
        branches,
        countries,
        tasks,
        sources,
        leaders,
        today,
    )
    session.add_all(materials)
    session.add_all(telegrams)
    session.flush()

    documents = list(materials) + list(telegrams)
    evaluation_lists = _create_evaluations(
        fake, max(1, len(documents) // 20), materials, telegrams, today
    )
    session.add_all(evaluation_lists)
    session.flush()

    if args.with_files:
        for document in documents:
            if not fake.boolean(chance_of_getting_true=25):
                continue
            subdirectory = (
                MATERIAL_FILES_DIR
                if isinstance(document, ScientificMaterial)
                else TELEGRAM_FILES_DIR
            )
            _attach_file(session, fake, storage_root, document, subdirectory)

    session.commit()


def _print_statistics(session: Session) -> None:
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
        ("Списки оценок", EvaluationList),
        ("Оценки", Evaluation),
        ("Файлы", FileRecord),
    ]
    print("Созданные данные:")
    for title, model in entities:
        print(f"  {title}: {session.query(model).count()}")

    print("Филиалы (идентификаторы для settings.ini):")
    for branch in session.query(Branch).order_by(Branch.id).all():
        print(f"  {branch.id} — {branch.name}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа скрипта наполнения базы данных."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.branches < 1:
        parser.error("Количество филиалов должно быть не меньше 1")
    if args.materials < 0 or args.telegrams < 0:
        parser.error("Количество материалов и телеграмм не может быть отрицательным")

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    fake = Faker("ru_RU")
    db_url, storage_root, settings = _resolve_targets(args)

    register_change_tracking()
    db_manager = DatabaseManager(db_url, PROJECT_ROOT)
    db_manager.create_tables()

    try:
        with db_manager.get_session() as session:
            existing_branches = session.query(Branch).count()
            if existing_branches and not args.clear:
                print(
                    f"В базе уже есть данные (филиалов: {existing_branches}). "
                    "Используйте --clear, чтобы удалить их перед наполнением."
                )
                return 1

            if args.clear:
                _clear_database(session)
                print("Существующие данные удалены.")

            _seed(session, fake, args, storage_root, date.today(), settings.branch_id)
            _print_statistics(session)
    finally:
        db_manager.close()

    print(f"База данных: {db_url}")
    print(f"Хранилище: {storage_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
