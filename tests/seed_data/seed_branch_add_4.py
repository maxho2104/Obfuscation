"""Добавление порций документов филиала (продолжение фазы филиала).

Скрипт дополняет базу, наполненную ``tests.seed_data.seed_branch_2``,
новыми научными материалами и телеграммами: период генерации начинается
со дня, следующего за крайней датой исходящих документов филиала в базе
(материалы и телеграммы), и заканчивается датой ``--to`` (по умолчанию —
сегодняшним днём).

В отличие от ``seed_branch_2`` скрипт не создаёт организационно-штатную
структуру, не распределяет задачи по ОШС и не создаёт источники:
документы ссылаются на имеющиеся записи (участники — из действующей
ОШС, источники — из справочника филиала). Нумерация продолжает годовые
счётчики (``ИСХ-NNNNN``, ``ТЛГ-NNNNN``, ``РАЗР-NNNNN``), реквизиты
разрешительных документов заполняются по тем же правилам.

При отсутствии в базе ОШС или документов филиала скрипт завершается
ошибкой — сначала наполните базу ``tests.seed_data.seed_branch_2``.

Примеры запуска:
    python -m tests.seed_data.seed_branch_add_4
    python -m tests.seed_data.seed_branch_add_4 --to 2026-09-30 \
        --materials-per-day 2-4 --telegrams-per-day 1-2 --with-files
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from faker import Faker  # noqa: E402
from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from internal_correspondence.core.database import DatabaseManager  # noqa: E402
from internal_correspondence.orm.models import (  # noqa: E402
    ScientificMaterial,
    Source,
    Telegram,
)
from internal_correspondence.services.change_tracking import (  # noqa: E402
    register_change_tracking,
)
from tests.seed_common import (  # noqa: E402
    YearlyCounter,
    attach_file,
    document_files_subdirectory,
    parse_date,
    parse_range,
    random_dates,
    resolve_targets,
)
from tests.seed_data import seed_branch_2  # noqa: E402
from tests.seed_data.seed_branch_2 import BranchSeedError  # noqa: E402

DEFAULT_MATERIALS_PER_DAY = (1, 3)
DEFAULT_TELEGRAMS_PER_DAY = (0, 2)


def _build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description=(
            "Добавление порций документов филиала за период "
            "после крайней даты в базе."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-url", help="URL базы данных (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--storage", help="Каталог файлового хранилища (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        type=parse_date,
        help="Конец периода генерации (ГГГГ-ММ-ДД); по умолчанию — сегодня",
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
        "--seed", type=int, help="Зерно генератора для воспроизводимых данных"
    )
    parser.add_argument(
        "--with-files", action="store_true", help="Создавать файлы-вложения в хранилище"
    )
    return parser


def _latest_document_date(session: Session, branch_id: str) -> Optional[date]:
    """Возвращает крайнюю дату исходящих документов филиала (None — документов нет)."""
    latest_material = (
        session.query(func.max(ScientificMaterial.outgoing_date))
        .filter(ScientificMaterial.branch_id == branch_id)
        .scalar()
    )
    latest_telegram = (
        session.query(func.max(Telegram.outgoing_date))
        .filter(Telegram.branch_id == branch_id)
        .scalar()
    )
    dates = [
        value for value in (latest_material, latest_telegram) if value is not None
    ]
    return max(dates) if dates else None


def _seed(
    session: Session,
    fake: Faker,
    args: argparse.Namespace,
    storage_root: Path,
) -> Tuple[date, List[object]]:
    """Добавляет документы со дня после крайней даты в базе до args.date_to.

    Возвращает начало добавленного периода и созданные документы.
    """
    references = seed_branch_2._load_reference_data(session)
    branch = seed_branch_2._resolve_branch(session)
    if not branch.departments:
        raise BranchSeedError(
            "В базе нет организационно-штатной структуры филиала. Сначала "
            "наполните базу: python -m tests.seed_data.seed_branch_2."
        )
    latest = _latest_document_date(session, branch.id)
    if latest is None:
        raise BranchSeedError(
            "В базе нет документов филиала — начало периода не определить. "
            "Сначала наполните базу: python -m tests.seed_data.seed_branch_2."
        )
    date_from = latest + timedelta(days=1)
    if args.date_to < date_from:
        raise BranchSeedError(
            f"Крайняя дата документов в базе — {latest}, добавляемые документы "
            f"должны начинаться не раньше {date_from}."
        )

    counters = {
        "materials": YearlyCounter("ИСХ"),
        "telegrams": YearlyCounter("ТЛГ"),
        "permits": YearlyCounter("РАЗР"),
    }
    seed_branch_2._align_counters(session, counters)

    existing_sources = list(session.query(Source))

    created_documents: List[object] = []
    for day in random_dates(date_from, args.date_to):
        for _ in range(random.randint(*args.materials_per_day)):
            material = seed_branch_2._create_material(
                fake,
                branch,
                day,
                counters,
                references["countries"],
                references["consumers"],
                references["tasks"],
                existing_sources,
            )
            session.add(material)
            created_documents.append(material)
        for _ in range(random.randint(*args.telegrams_per_day)):
            telegram = seed_branch_2._create_telegram(
                session,
                fake,
                branch,
                day,
                counters,
                references["countries"],
                references["tasks"],
                existing_sources,
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
    return date_from, created_documents


def _print_statistics(
    session: Session, date_from: date, date_to: date, stats: Dict[str, int]
) -> None:
    """Выводит количество добавленных и итоговое количество документов."""
    print(f"Добавлено документов за {date_from} — {date_to}:")
    print(f"  Научные материалы: {stats['materials']}")
    print(f"  Телеграммы: {stats['telegrams']}")
    print("Итого в базе:")
    for title, model in (
        ("Научные материалы", ScientificMaterial),
        ("Телеграммы", Telegram),
    ):
        print(f"  {title}: {session.query(model).count()}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа скрипта добавления документов филиала."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    args.date_to = args.date_to or date.today()

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
            date_from, created_documents = _seed(session, fake, args, storage_root)
            stats = {
                "materials": sum(
                    isinstance(document, ScientificMaterial)
                    for document in created_documents
                ),
                "telegrams": sum(
                    isinstance(document, Telegram) for document in created_documents
                ),
            }
            _print_statistics(session, date_from, args.date_to, stats)
    finally:
        db_manager.close()

    print(f"База данных: {db_url}")
    print(f"Хранилище: {storage_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
