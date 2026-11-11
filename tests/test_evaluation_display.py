"""Тесты отображения оценки научных материалов и телеграмм."""

from datetime import date
from pathlib import Path

import pytest

from internal_correspondence.core.constants import (
    EvaluationValue,
    MaterialType,
    TelegramType,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    Branch,
    Evaluation,
    EvaluationList,
    ScientificMaterial,
    Telegram,
    TerritorialUnit,
)


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'evaluations.db'}")
    db.create_tables()
    yield db
    db.close()


def _create_documents(session):
    session.add(TerritorialUnit(id="MSK", name="Москва"))
    session.add(Branch(id="FIL001", name="Филиал 1", short_name="Ф-1", territorial_unit_id="MSK"))
    session.commit()

    material_one = ScientificMaterial(
        type=MaterialType.MESSAGE,
        outgoing_number="M-1",
        outgoing_date=date(2024, 1, 1),
        name="Материал 1",
        branch_id="FIL001",
    )
    material_two = ScientificMaterial(
        type=MaterialType.MESSAGE,
        outgoing_number="M-2",
        outgoing_date=date(2024, 1, 2),
        name="Материал 2",
        branch_id="FIL001",
    )
    telegram = Telegram(
        type=TelegramType.THEMATIC,
        outgoing_number="T-1",
        outgoing_date=date(2024, 1, 3),
        name="Телеграмма 1",
        branch_id="FIL001",
    )
    session.add_all([material_one, material_two, telegram])
    session.commit()
    return material_one, material_two, telegram


def _add_evaluation(session, number: str, value_date: date, value: EvaluationValue, materials, telegrams):
    evaluation_list = EvaluationList(number=number, date=value_date)
    evaluation = Evaluation(value=value, materials=list(materials), telegrams=list(telegrams))
    evaluation_list.evaluations.append(evaluation)
    session.add(evaluation_list)
    session.commit()
    return evaluation


def test_evaluation_is_divided_between_documents(db_manager: DatabaseManager) -> None:
    """Оценка распределяется как 1/n между всеми документами совокупности."""
    with db_manager.get_session() as session:
        material_one, material_two, telegram = _create_documents(session)
        _add_evaluation(
            session,
            "ОЦ-0001",
            date(2024, 2, 1),
            EvaluationValue.INTERESTING,
            materials=[material_one, material_two],
            telegrams=[telegram],
        )

        for document in (material_one, material_two, telegram):
            assert document.evaluation_display == "0,33 И"
            assert document.evaluation_share == pytest.approx(1 / 3)


def test_latest_evaluation_is_used(db_manager: DatabaseManager) -> None:
    """Из нескольких оценок отображается оценка из последнего списка."""
    with db_manager.get_session() as session:
        material_one, material_two, telegram = _create_documents(session)
        _add_evaluation(
            session,
            "ОЦ-0001",
            date(2024, 2, 1),
            EvaluationValue.INTERESTING,
            materials=[material_one, material_two],
            telegrams=[telegram],
        )
        _add_evaluation(
            session,
            "ОЦ-0002",
            date(2024, 3, 1),
            EvaluationValue.IMPORTANT,
            materials=[material_one],
            telegrams=[],
        )

        assert material_one.evaluation_display == "В"
        assert material_two.evaluation_display == "0,33 И"
        assert telegram.evaluation_display == "0,33 И"
        assert material_one.latest_evaluation.value == EvaluationValue.IMPORTANT


def test_evaluation_is_blank_when_missing(db_manager: DatabaseManager) -> None:
    """Без оценки ячейка остаётся пустой."""
    with db_manager.get_session() as session:
        material_one, _material_two, _telegram = _create_documents(session)

        assert material_one.latest_evaluation is None
        assert material_one.evaluation_share is None
        assert material_one.evaluation_display == ""


def test_evaluation_value_role_is_exposed_by_table_model(db_manager: DatabaseManager) -> None:
    """Модель таблицы передаёт значение оценки делегату через отдельную роль."""
    from internal_correspondence.gui.application import MATERIAL_COLUMNS
    from internal_correspondence.gui.table_model import (
        EVALUATION_VALUE_ROLE,
        SqlAlchemyTableModel,
    )

    with db_manager.get_session() as session:
        material_one, _material_two, _telegram = _create_documents(session)
        _add_evaluation(
            session,
            "ОЦ-0001",
            date(2024, 2, 1),
            EvaluationValue.USEFUL,
            materials=[material_one],
            telegrams=[],
        )

        model = SqlAlchemyTableModel(session, ScientificMaterial, MATERIAL_COLUMNS)
        column_index = next(
            index
            for index, column in enumerate(MATERIAL_COLUMNS)
            if column.name == "evaluation_display"
        )

        assert model.index(0, column_index).data(EVALUATION_VALUE_ROLE) == EvaluationValue.USEFUL
        assert model.index(0, column_index).data() == "П"


def test_delegate_has_colors_for_all_evaluation_values() -> None:
    """Для каждого значения оценки задан цвет отображения."""
    from internal_correspondence.gui.evaluation_delegate import EvaluationItemDelegate

    for value in EvaluationValue:
        assert value.value in EvaluationItemDelegate.COLORS
