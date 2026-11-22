"""Тесты скрипта справочных данных головного офиса (seed_reference)."""

import random
from argparse import Namespace
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from faker import Faker

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    AcademicTitle,
    AddedTask,
    Branch,
    Consumer,
    Country,
    Leader,
    ScientificTask,
    TerritorialUnit,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.services.task_distribution_service import NODE_BRANCH
from tests.seed_reference import build_task_periods, create_reference_data


def _args(**overrides) -> Namespace:
    """Формирует аргументы скрипта по умолчанию с подменами."""
    values = dict(
        units=5,
        branches_per_unit=2,
        countries=(30, 40),
        consumers=10,
        leaders=5,
        tasks=240,
    )
    values.update(overrides)
    return Namespace(**values)


@pytest.fixture()
def session(tmp_path: Path):
    """Сессия временной SQLite с зарегистрированным трекингом изменений."""
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'reference.db'}")
    db.create_tables()
    with db.get_session() as current:
        yield current
    db.close()


def test_build_task_periods_thirds_and_sixths() -> None:
    """60 задач делятся на трети и шестые доли с заданными сроками."""
    periods = build_task_periods(60)
    assert len(periods) == 60
    counts = Counter(periods)
    assert counts[(date(2025, 1, 1), date(2025, 12, 31))] == 20
    assert counts[(date(2026, 1, 1), date(2026, 12, 31))] == 20
    assert counts[(date(2025, 10, 1), date(2026, 9, 30))] == 10
    assert counts[(date(2025, 10, 1), None)] == 10


def test_build_task_periods_remainder_goes_to_last_spec() -> None:
    """Остаток от деления распределяется по периодам с начала списка."""
    periods = build_task_periods(7)
    assert len(periods) == 7
    counts = Counter(periods)
    # Веса 2:2:1:1 — при 7 задачах: 2, 2, 1 и остаток 2 в последний период
    assert counts[(date(2025, 1, 1), date(2025, 12, 31))] == 2
    assert counts[(date(2026, 1, 1), date(2026, 12, 31))] == 2
    assert counts[(date(2025, 10, 1), date(2026, 9, 30))] == 1
    assert counts[(date(2025, 10, 1), None)] == 2


def test_create_reference_data_counts(session) -> None:
    """Создаются справочники заданного состава."""
    stats = create_reference_data(session, Faker("ru_RU"), _args())
    assert stats["territorial_units"] == 5
    assert stats["branches"] == 10
    assert 30 <= stats["countries"] <= 40
    assert stats["academic_titles"] == 4
    assert stats["consumers"] == 10
    assert stats["leaders"] == 5
    assert stats["tasks"] == 240


def test_tasks_have_branch_assignments_with_overlaps(session) -> None:
    """Каждая задача назначена 1-3 филиалам; распределение с пересечениями."""
    random.seed(5)
    create_reference_data(session, Faker("ru_RU"), _args())
    assignments = session.query(AddedTask).all()
    assert 240 <= len(assignments) <= 240 * 3
    assert all(row.node_type == NODE_BRANCH for row in assignments)
    per_task = Counter(row.task_id for row in assignments)
    assert set(per_task.values()) <= {1, 2, 3}
    assert len(per_task) == 240
    per_branch = Counter(row.node_id for row in assignments)
    assert len(per_branch) == 10
    # Пересечения: не менее половины задач общие для нескольких филиалов
    assert sum(1 for count in per_task.values() if count > 1) >= 120


def test_task_periods_written_to_models(session) -> None:
    """Сроки действия задач в базе совпадают с заданными долями."""
    create_reference_data(session, Faker("ru_RU"), _args(tasks=60))
    periods = Counter(
        (task.start_date, task.end_date)
        for task in session.query(ScientificTask)
    )
    assert periods[(date(2025, 1, 1), date(2025, 12, 31))] == 20
    assert periods[(date(2026, 1, 1), date(2026, 12, 31))] == 20
    assert periods[(date(2025, 10, 1), date(2026, 9, 30))] == 10
    assert periods[(date(2025, 10, 1), None)] == 10


def test_reference_data_is_reproducible_with_seed(tmp_path: Path) -> None:
    """Одинаковое зерно даёт одинаковый набор задач филиала."""
    register_change_tracking()

    def run() -> Counter:
        db = DatabaseManager(f"sqlite:///{tmp_path / (str(random.random()) + '.db')}")
        db.create_tables()
        with db.get_session() as current:
            random.seed(42)
            Faker.seed(42)
            create_reference_data(current, Faker("ru_RU"), _args())
            current.commit()
            result = Counter(
                (row.task_id, row.node_id)
                for row in current.query(AddedTask).all()
            )
        db.close()
        return result

    assert run() == run()
