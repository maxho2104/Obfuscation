"""Тесты связи документов с задачами (N-N) и адресации доклада телеграмм."""

from datetime import date
from pathlib import Path

import pytest

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    Branch,
    Change,
    Leader,
    ReportAddress,
    ScientificMaterial,
    ScientificTask,
    Telegram,
    TerritorialUnit,
)
from internal_correspondence.reports.statistics_service import (
    CRITERION_TASK,
    PERIOD_YEAR,
    StatisticsQuery,
    StatisticsService,
)
from internal_correspondence.services.change_tracking import register_change_tracking


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    """Создаёт временную БД с актуальными таблицами."""
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'tasks.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="function")
def base_records(db_manager: DatabaseManager) -> dict:
    """Минимальный набор записей: филиал, две задачи, руководитель."""
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(
            Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK")
        )
        task1 = ScientificTask(
            id="T1", name="Задача 1", type="ОЗ", start_date=date(2026, 1, 1)
        )
        task2 = ScientificTask(
            id="T2", name="Задача 2", type="ОЗ", start_date=date(2026, 1, 1)
        )
        leader = Leader(id="НГ", active=True)
        session.add_all([task1, task2, leader])
        session.commit()
    return {"tasks": (task1, task2), "leader": leader}


def test_material_tasks_many_to_many(db_manager: DatabaseManager, base_records) -> None:
    """Материал связывается с несколькими задачами в обе стороны."""
    task1, task2 = base_records["tasks"]
    with db_manager.get_session() as session:
        material = ScientificMaterial(
            type="С",
            name="Материал",
            branch_id="F1",
            outgoing_date=date(2026, 3, 1),
            tasks=[task1, task2],
        )
        session.add(material)
        session.commit()

        loaded = session.get(ScientificMaterial, material.id)
        assert {task.id for task in loaded.tasks} == {"T1", "T2"}
        assert session.get(ScientificTask, "T1").materials[0].id == material.id
        assert session.get(ScientificTask, "T2").materials[0].id == material.id

        # Переназначение связей работает через обычную коллекцию
        loaded.tasks = [session.get(ScientificTask, "T2")]
        session.commit()
        assert [task.id for task in loaded.tasks] == ["T2"]


def test_telegram_tasks_many_to_many(db_manager: DatabaseManager, base_records) -> None:
    """Телеграмма связывается с несколькими задачами."""
    task1, task2 = base_records["tasks"]
    with db_manager.get_session() as session:
        telegram = Telegram(
            type="ДК",
            name="Телеграмма",
            branch_id="F1",
            outgoing_date=date(2026, 3, 1),
            tasks=[task1, task2],
        )
        session.add(telegram)
        session.commit()

        loaded = session.get(Telegram, telegram.id)
        assert {task.id for task in loaded.tasks} == {"T1", "T2"}
        assert session.get(ScientificTask, "T1").telegrams[0].id == telegram.id


def test_tasks_change_tracked(db_manager: DatabaseManager, base_records) -> None:
    """Изменение связи tasks фиксируется в записи Change документа."""
    task1, _ = base_records["tasks"]
    with db_manager.get_session() as session:
        material = ScientificMaterial(
            type="С",
            name="Материал",
            branch_id="F1",
            outgoing_date=date(2026, 3, 1),
        )
        session.add(material)
        session.commit()

        material.tasks = [task1]
        session.commit()

        change = session.query(Change).filter_by(
            entity_name="ScientificMaterial", entity_pk=str(material.id)
        ).one()
        assert "tasks" in change.changed_fields


def test_report_addresses_cascade_delete(
    db_manager: DatabaseManager, base_records
) -> None:
    """Удаление телеграммы удаляет записи адресации доклада."""
    leader = base_records["leader"]
    with db_manager.get_session() as session:
        telegram = Telegram(
            type="ДК",
            name="Телеграмма",
            branch_id="F1",
            outgoing_date=date(2026, 3, 1),
            report_addresses=[
                ReportAddress(leader_id=leader.id, report_date=date(2026, 3, 5))
            ],
        )
        session.add(telegram)
        session.commit()
        telegram_id = telegram.id
        assert len(telegram.report_addresses) == 1

        session.delete(telegram)
        session.commit()

        assert session.query(ReportAddress).count() == 0
        assert session.get(Telegram, telegram_id) is None


def test_report_addresses_replace_orphans(
    db_manager: DatabaseManager, base_records
) -> None:
    """Замена коллекции адресации удаляет исключённые записи (delete-orphan)."""
    leader = base_records["leader"]
    with db_manager.get_session() as session:
        telegram = Telegram(
            type="ДК",
            name="Телеграмма",
            branch_id="F1",
            outgoing_date=date(2026, 3, 1),
        )
        first = ReportAddress(leader_id=leader.id, report_date=date(2026, 3, 5))
        second = ReportAddress(leader_id=leader.id, report_date=date(2026, 4, 5))
        telegram.report_addresses = [first, second]
        session.add(telegram)
        session.commit()

        telegram.report_addresses = [second]
        session.commit()

        remaining = session.query(ReportAddress).all()
        assert len(remaining) == 1
        assert remaining[0].id == second.id


def test_statistics_task_counts_document_in_each_task(
    db_manager: DatabaseManager, base_records
) -> None:
    """Документ с несколькими задачами учитывается в статистике по каждой."""
    task1, task2 = base_records["tasks"]
    with db_manager.get_session() as session:
        session.add(
            ScientificMaterial(
                type="С",
                name="Материал",
                branch_id="F1",
                outgoing_date=date(2026, 3, 1),
                tasks=[task1, task2],
            )
        )
        session.commit()

    query = StatisticsQuery(
        model_class=ScientificMaterial,
        criterion=CRITERION_TASK,
        period_type=PERIOD_YEAR,
        year=2026,
    )
    result = StatisticsService(db_manager.get_session()).calculate(query)

    labels = {row.label: row.total for row in result.rows}
    assert labels == {"Задача 1": 1, "Задача 2": 1}
