"""Тесты скрипта наполнения базы данными головного офиса (``tests.seed_head_office``)."""

from argparse import Namespace
from datetime import timedelta
from pathlib import Path

import pytest
from faker import Faker

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    Evaluation,
    EvaluationList,
    ScientificMaterial,
    Telegram,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from tests import seed_branch, seed_head_office, seed_reference


def _seed_branch(tmp_path: Path) -> None:
    """Филиал: справочники ГО (как из архива) + данные филиала."""
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{(tmp_path / 'seed.db').as_posix()}")
    db.create_tables()
    with db.get_session() as session:
        seed_reference.create_reference_data(
            session,
            Faker("ru_RU"),
            Namespace(
                units=1,
                branches_per_unit=1,
                countries=(30, 40),
                consumers=10,
                leaders=5,
                tasks=60,
            ),
        )
        session.commit()
    db.close()
    assert seed_branch.main(
        [
            "--db-url", f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
            "--storage", (tmp_path / "storage").as_posix(),

            "--from", "2026-10-01",
            "--to", "2026-10-12",
            "--materials-per-day", "2-3",
            "--telegrams-per-day", "1-2",
            "--seed", "13",
        ]
    ) == 0


def _seed_head_office(tmp_path: Path) -> None:
    assert seed_head_office.main(
        [
            "--db-url", f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
            "--storage", (tmp_path / "storage").as_posix(),
            "--seed", "21",
        ]
    ) == 0


@pytest.fixture()
def seeded_db(tmp_path: Path) -> DatabaseManager:
    """База, заполненная филиалом и зарегистрированная головным офисом."""
    _seed_branch(tmp_path)
    _seed_head_office(tmp_path)
    db = DatabaseManager(f"sqlite:///{(tmp_path / 'seed.db').as_posix()}")
    yield db
    db.close()


def test_incoming_numbers_sequential_and_matching_dates(
    seeded_db: DatabaseManager,
) -> None:
    with seeded_db.get_session() as session:
        materials = (
            session.query(ScientificMaterial)
            .order_by(ScientificMaterial.outgoing_date,
                      ScientificMaterial.incoming_number)
            .all()
        )
        telegrams = session.query(Telegram).all()
        assert materials and telegrams
        nums = [int(m.incoming_number.split("-")[1]) for m in materials]
        assert nums == list(range(1, len(nums) + 1))
        assert all(m.incoming_number.startswith("ВХ-") for m in materials)
        # Дата входящего совпадает с датой исходящего.
        assert all(
            m.incoming_date == m.outgoing_date for m in materials
        )
        assert all(
            t.incoming_date == t.outgoing_date for t in telegrams
        )


def test_all_materials_evaluated_within_group_rules(
    seeded_db: DatabaseManager,
) -> None:
    with seeded_db.get_session() as session:
        materials = session.query(ScientificMaterial).all()
        evaluations = session.query(Evaluation).all()
        assert evaluations
        # Каждый материал получил ровно одну оценку.
        for material in materials:
            assert len(material.evaluations) == 1
        # Правила групп: 1-10 документов, разброс дат ≤ 14 дней,
        # дата оценки — от максимальной даты документов до +3 дней.
        for evaluation in evaluations:
            documents = list(evaluation.materials) + list(evaluation.telegrams)
            assert 1 <= len(documents) <= 10
            incoming_dates = [doc.incoming_date for doc in documents]
            assert max(incoming_dates) - min(incoming_dates) <= timedelta(
                days=14
            )
            latest = max(incoming_dates)
            assert latest <= evaluation.date <= latest + timedelta(days=3)


def test_evaluation_lists_group_evaluations(
    seeded_db: DatabaseManager,
) -> None:
    with seeded_db.get_session() as session:
        lists = session.query(EvaluationList).all()
        evaluations = session.query(Evaluation).all()
        assert lists
        # Каждая оценка привязана к списку.
        assigned = [
            evaluation.evaluation_list_id for evaluation in evaluations
        ]
        assert all(list_id is not None for list_id in assigned)
        # В списке 1-10 оценок, дата списка — максимум дат оценок,
        # номера — последовательность годового счётчика.
        for evaluation_list in lists:
            chunk = list(evaluation_list.evaluations)
            assert 1 <= len(chunk) <= 10
            assert evaluation_list.date == max(
                evaluation.date for evaluation in chunk
            )
        numbers = sorted(
            int(lst.number.split("-")[1]) for lst in lists
        )
        assert numbers == list(range(1, len(numbers) + 1))


def test_telegram_report_addresses_filled(
    seeded_db: DatabaseManager,
) -> None:
    with seeded_db.get_session() as session:
        telegrams = session.query(Telegram).all()
        assert telegrams
        for telegram in telegrams:
            # Тип доклада проставлен: «доказано» или «срочно доказано».
            assert telegram.report_type is not None
            addresses = list(telegram.report_addresses)
            assert 1 <= len(addresses) <= 3
            # Дата доклада совпадает с датой входящего номера.
            for address in addresses:
                assert address.report_date == telegram.incoming_date


def test_second_run_skips_registered_documents(tmp_path: Path) -> None:
    _seed_branch(tmp_path)
    _seed_head_office(tmp_path)
    with pytest.raises(seed_head_office.HeadOfficeSeedError):
        _seed_head_office(tmp_path)
