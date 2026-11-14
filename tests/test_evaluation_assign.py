"""Тесты ручного выставления оценок документам."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.constants import EvaluationValue, MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.evaluation_dialog import EvaluationAssignDialog
from internal_correspondence.orm.models import (
    Branch,
    Evaluation,
    ScientificMaterial,
    TerritorialUnit,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def env(tmp_path: Path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'evaluations.db'}")
    db.create_tables()
    with db.get_session() as session:
        session.add(TerritorialUnit(id="TU", name="Единица"))
        session.add(Branch(id="F1", name="Филиал 1", short_name="Ф1", territorial_unit_id="TU"))
        first = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-1",
            outgoing_date=date(2026, 1, 1),
            name="Материал 1",
            branch_id="F1",
        )
        second = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-2",
            outgoing_date=date(2026, 1, 2),
            name="Материал 2",
            branch_id="F1",
        )
        session.add_all([first, second])
        session.commit()
        ids = (first.id, second.id)
    yield db, ids
    db.close()


def test_manual_evaluation_without_list(qapp, env) -> None:
    """Одна ручная оценка привязывается к нескольким документам."""
    db, ids = env
    with db.get_session() as session:
        evaluation = Evaluation(
            value=EvaluationValue.IMPORTANT,
            date=date(2026, 5, 10),
        )
        session.add(evaluation)
        for pk in ids:
            evaluation.materials.append(session.get(ScientificMaterial, pk))
        session.commit()
        evaluation_id = evaluation.id

    with db.get_session() as session:
        evaluation = session.get(Evaluation, evaluation_id)
        # Список оценок необязателен, дата выставления сохранена
        assert evaluation.evaluation_list is None
        assert evaluation.date == date(2026, 5, 10)
        assert {material.id for material in evaluation.materials} == set(ids)
        # «Последняя» оценка документов — ручная
        material = session.get(ScientificMaterial, ids[0])
        assert material.latest_evaluation is not None
        assert material.latest_evaluation.value == EvaluationValue.IMPORTANT


def test_evaluation_assign_dialog_data(qapp) -> None:
    """Диалог выставления оценки отдаёт выбранные значение и дату."""
    dialog = EvaluationAssignDialog()
    dialog.value_combo.setCurrentIndex(2)
    dialog.date_edit.setDate(date(2026, 6, 15))
    value, assigned_date = dialog.get_data()
    assert value == EvaluationValue(dialog.value_combo.itemData(2))
    assert assigned_date == date(2026, 6, 15)
