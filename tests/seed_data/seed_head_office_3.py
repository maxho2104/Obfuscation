"""Наполнение базы данных от имени головного офиса (фаза ГО).

Скрипт моделирует регистрацию в головном офисе документов, созданных
филиалами (см. ``tests.seed_branch``):

- каждому материалу и телеграмме проставляется входящий номер
  (``ВХ-NNNNN``, единый годовой счётчик на все филиалы) и дата входящего
  номера (совпадает с датой исходящего);
- с вероятностью 1/30 у материала меняется потребитель, с вероятностью
  1/5 — комментарий (материал/телеграмма);
- каждый материал получает оценку, телеграммы — с вероятностью 1/100.
  Одна оценка объединяет от 1 до 10 документов, разброс дат которых
  не превышает двух недель; дата оценки — от максимальной даты входящих
  документов группы до неё же плюс 3 дня;
- оценки объединяются в списки оценок (``ОЦ-NNNNN``, годовой счётчик):
  в списке от 1 до 10 оценок, дата списка — максимальная дата оценок;
- телеграммам проставляется тип доклада («доказано» чаще, «срочно
  доказано» реже), адресатам доклада — дата, совпадающая с датой
  входящего номера.

Повторный запуск пропускает документы, уже зарегистрированные в ГО
(с проставленным входящим номером).

Пример запуска:
    python -m tests.seed_data.seed_head_office_3 --seed 42
"""

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from faker import Faker  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from internal_correspondence.core.constants import (  # noqa: E402
    EvaluationValue,
    TelegramReportType,
)
from internal_correspondence.core.database import DatabaseManager  # noqa: E402
from internal_correspondence.orm.models import (  # noqa: E402
    Consumer,
    Evaluation,
    EvaluationList,
    Leader,
    ReportAddress,
    ScientificMaterial,
    Telegram,
)
from internal_correspondence.services.change_tracking import (  # noqa: E402
    register_change_tracking,
)
from tests.seed_common import (  # noqa: E402
    YearlyCounter,
    parse_range,
    resolve_targets,
)

# Вероятности правок, вносимых головным офисом при регистрации
CONSUMER_CHANGE_PROBABILITY = 1 / 30
COMMENT_CHANGE_PROBABILITY = 1 / 5
# Доля телеграмм, получающих оценку
DEFAULT_TELEGRAM_EVALUATION_PROBABILITY = 1 / 100
# Документы одной оценки не должны различаться по дате более чем на это число дней
EVALUATION_GROUP_SPREAD_DAYS = 14
# Дата оценки: от максимальной даты документов до неё же + это число дней
EVALUATION_DATE_SLACK_DAYS = 3
# Тип доклада телеграммы: «срочно доказано» реже «доказано»
URGENT_REPORT_PROBABILITY = 0.2
# Число адресатов доклада: обычно 1, до 3
MAX_REPORT_ADDRESSES = 3
EXTRA_REPORT_ADDRESS_PROBABILITY = 0.25

DEFAULT_EVAL_GROUP = (1, 10)  # документов в одной оценке
DEFAULT_LIST_GROUP = (1, 10)  # оценок в одном списке оценок


class HeadOfficeSeedError(Exception):
    """Ошибка наполнения базы данными головного офиса."""


def _build_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Наполнение базы данных от имени головного офиса.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db-url", help="URL базы данных (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--storage", help="Каталог файлового хранилища (по умолчанию из settings.ini)"
    )
    parser.add_argument(
        "--telegram-evaluation-probability",
        type=float,
        default=DEFAULT_TELEGRAM_EVALUATION_PROBABILITY,
        help="Вероятность получения оценки телеграммой (0..1)",
    )
    parser.add_argument(
        "--eval-group",
        type=parse_range,
        default=DEFAULT_EVAL_GROUP,
        help="Количество документов в одной оценке (N-M)",
    )
    parser.add_argument(
        "--list-group",
        type=parse_range,
        default=DEFAULT_LIST_GROUP,
        help="Количество оценок в одном списке оценок (N-M)",
    )
    parser.add_argument(
        "--seed", type=int, help="Зерно генератора для воспроизводимых данных"
    )
    return parser


def _register_documents(
    session: Session,
    fake: Faker,
    incoming_counter: YearlyCounter,
) -> Tuple[List[ScientificMaterial], List[Telegram]]:
    """Проставляет входящие номера и даты; возвращает зарегистрированные документы."""
    consumers = list(session.query(Consumer))
    leaders = [leader for leader in session.query(Leader) if leader.active]

    materials = (
        session.query(ScientificMaterial)
        .filter(ScientificMaterial.incoming_number.is_(None))
        .order_by(ScientificMaterial.outgoing_date)
        .all()
    )
    telegrams = (
        session.query(Telegram)
        .filter(Telegram.incoming_number.is_(None))
        .order_by(Telegram.outgoing_date)
        .all()
    )
    if not materials and not telegrams:
        raise HeadOfficeSeedError(
            "Нет документов для регистрации: все материалы и телеграммы уже "
            "имеют входящие номера (или база пуста)."
        )

    registered_materials: List[ScientificMaterial] = []
    for material in materials:
        material.incoming_number = incoming_counter.next(material.outgoing_date)
        material.incoming_date = material.outgoing_date
        if consumers and random.random() < CONSUMER_CHANGE_PROBABILITY:
            material.consumer_id = fake.random_element(consumers).id
        # Потребитель не остаётся пустым: при регистрации ГО заполняет
        # поле, если филиал его не указал.
        if consumers and not material.consumer_id:
            material.consumer_id = fake.random_element(consumers).id
        if random.random() < COMMENT_CHANGE_PROBABILITY:
            material.comment = fake.sentence(nb_words=12)[:300]
        registered_materials.append(material)

    registered_telegrams: List[Telegram] = []
    for telegram in telegrams:
        telegram.incoming_number = incoming_counter.next(telegram.outgoing_date)
        telegram.incoming_date = telegram.outgoing_date
        telegram.report_type = (
            TelegramReportType.URGENTLY_REPORTED.value
            if random.random() < URGENT_REPORT_PROBABILITY
            else TelegramReportType.REPORTED.value
        )
        if random.random() < COMMENT_CHANGE_PROBABILITY:
            telegram.comment = fake.sentence(nb_words=12)[:300]
        _fill_report_addresses(session, fake, telegram, leaders)
        registered_telegrams.append(telegram)

    session.flush()
    return registered_materials, registered_telegrams


def _fill_report_addresses(
    session: Session,
    fake: Faker,
    telegram: Telegram,
    leaders: Sequence,
) -> None:
    """Проставляет даты адресатам доклада и при необходимости добавляет адресатов."""
    if not leaders:
        return
    addresses = list(telegram.report_addresses)
    if not addresses:
        addresses = [
            ReportAddress(telegram=telegram, leader_id=fake.random_element(leaders).id)
        ]
        session.add(addresses[0])
    while (
        len(addresses) < MAX_REPORT_ADDRESSES
        and random.random() < EXTRA_REPORT_ADDRESS_PROBABILITY
    ):
        address = ReportAddress(
            telegram=telegram, leader_id=fake.random_element(leaders).id
        )
        session.add(address)
        addresses.append(address)
    for address in addresses:
        address.report_date = telegram.incoming_date


def _evaluation_candidates(
    materials: Sequence[ScientificMaterial],
    telegrams: Sequence[Telegram],
    telegram_probability: float,
) -> List:
    """Возвращает неоценённые документы: все материалы + часть телеграмм."""
    candidates: List = [m for m in materials if not m.evaluations]
    for telegram in telegrams:
        if not telegram.evaluations and random.random() < telegram_probability:
            candidates.append(telegram)
    candidates.sort(key=lambda doc: doc.incoming_date)
    return candidates


def _create_evaluations(
    session: Session,
    fake: Faker,
    candidates: Sequence,
    group_range: Tuple[int, int],
) -> List[Evaluation]:
    """Объединяет документы в оценки: 1-10 документов, разброс дат ≤ 14 дней."""
    evaluations: List[Evaluation] = []
    pending = list(candidates)
    while pending:
        anchor_date = pending[0].incoming_date
        group: List = []
        limit_date = anchor_date + timedelta(days=EVALUATION_GROUP_SPREAD_DAYS)
        group_size = random.randint(*group_range)
        for document in list(pending):
            if len(group) >= group_size:
                break
            if document.incoming_date > limit_date:
                break
            group.append(document)
            pending.remove(document)
        latest = max(document.incoming_date for document in group)
        evaluation = Evaluation(
            value=fake.random_element(list(EvaluationValue)).value,
            date=latest
            + timedelta(days=random.randint(0, EVALUATION_DATE_SLACK_DAYS)),
        )
        for document in group:
            if isinstance(document, ScientificMaterial):
                evaluation.materials.append(document)
            else:
                evaluation.telegrams.append(document)
        session.add(evaluation)
        evaluations.append(evaluation)
    session.flush()
    return evaluations


def _create_evaluation_lists(
    session: Session,
    evaluations: Sequence[Evaluation],
    list_counter: YearlyCounter,
    group_range: Tuple[int, int],
) -> List[EvaluationList]:
    """Объединяет оценки в списки: 1-10 оценок, дата = max дата оценок."""
    lists: List[EvaluationList] = []
    pending = list(evaluations)
    while pending:
        size = min(random.randint(*group_range), len(pending))
        chunk = pending[:size]
        del pending[:size]
        evaluation_list = EvaluationList(
            number=list_counter.next(chunk[0].date),
            date=max(evaluation.date for evaluation in chunk),
        )
        for evaluation in chunk:
            evaluation_list.evaluations.append(evaluation)
        session.add(evaluation_list)
        lists.append(evaluation_list)
    session.flush()
    return lists


def _seed(session: Session, fake: Faker, args: argparse.Namespace) -> dict:
    """Регистрирует документы и выставляет оценки; возвращает статистику."""
    incoming_counter = YearlyCounter("ВХ")
    list_counter = YearlyCounter("ОЦ")

    materials, telegrams = _register_documents(session, fake, incoming_counter)
    candidates = _evaluation_candidates(
        materials, telegrams, args.telegram_evaluation_probability
    )
    evaluations = _create_evaluations(session, fake, candidates, args.eval_group)
    lists = _create_evaluation_lists(session, evaluations, list_counter, args.list_group)

    session.commit()
    return {
        "materials": len(materials),
        "telegrams": len(telegrams),
        "evaluations": len(evaluations),
        "lists": len(lists),
    }


def _print_statistics(session: Session, stats: dict) -> None:
    """Выводит итоги регистрации и оценивания."""
    print("Зарегистрировано в головном офисе:")
    print(f"  Материалов с входящим номером: {stats['materials']}")
    print(f"  Телеграмм с входящим номером: {stats['telegrams']}")
    print(f"  Оценок: {stats['evaluations']}")
    print(f"  Списков оценок: {stats['lists']}")
    print("Итого в базе:")
    for title, model in (
        ("Научные материалы", ScientificMaterial),
        ("Телеграммы", Telegram),
        ("Оценки", Evaluation),
        ("Списки оценок", EvaluationList),
        ("Адреса докладов", ReportAddress),
    ):
        print(f"  {title}: {session.query(model).count()}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа скрипта наполнения данными головного офиса."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not 0 <= args.telegram_evaluation_probability <= 1:
        parser.error("Вероятность оценки телеграммы должна быть в диапазоне 0..1")

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
            stats = _seed(session, fake, args)
            _print_statistics(session, stats)
    finally:
        db_manager.close()

    print(f"База данных: {db_url}")
    print(f"Хранилище: {storage_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
