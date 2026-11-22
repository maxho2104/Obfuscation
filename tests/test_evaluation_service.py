"""Тесты сервиса изменения оценок (план, раздел 3)."""

import os
import uuid
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from internal_correspondence.core.constants import EvaluationValue
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    Branch,
    Change,
    Country,
    Evaluation,
    EvaluationList,
    ScientificMaterial,
    Telegram,
    TerritorialUnit,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.services.evaluation_service import EvaluationService
from internal_correspondence.gui.evaluation_dialog import EvaluationAssignDialog


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_tables()
    yield db
    db.close()


def _setup(session) -> None:
    session.add(TerritorialUnit(id="MSK", name="Москва"))
    session.add(
        Branch(id="FIL001", name="Филиал", short_name="Ф-1", territorial_unit_id="MSK")
    )
    session.add(Country(id="RUS", name="Россия"))
    session.commit()


def _material(session, name: str = "Материал") -> ScientificMaterial:
    material = ScientificMaterial(
        type=0,
        outgoing_number=f"ИСХ-{uuid.uuid4().hex[:8]}",
        outgoing_date=date(2026, 9, 1),
        name=name,
        branch_id="FIL001",
    )
    session.add(material)
    session.commit()
    return material


def _attach(
    evaluation: Evaluation, document
) -> None:
    if isinstance(document, ScientificMaterial):
        evaluation.materials.append(document)
    else:
        evaluation.telegrams.append(document)


# --- последняя оценка ---


def test_latest_evaluation_by_date_then_value(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        material = _material(session)
        older = Evaluation(value=EvaluationValue.USEFUL, date=date(2026, 9, 1))
        _attach(older, material)
        newer = Evaluation(value=EvaluationValue.INTERESTING, date=date(2026, 9, 5))
        _attach(newer, material)
        session.add_all([older, newer])
        session.commit()

        assert material.latest_evaluation is newer

        # При равенстве дат выигрывает большее значение оценки.
        tie_weak = Evaluation(value=EvaluationValue.INTERESTING, date=date(2026, 9, 10))
        tie_strong = Evaluation(value=EvaluationValue.IMPORTANT, date=date(2026, 9, 10))
        _attach(tie_weak, material)
        _attach(tie_strong, material)
        session.add_all([tie_weak, tie_strong])
        session.commit()
        assert material.latest_evaluation is tie_strong


# --- смена оценки ---


def test_set_evaluation_first_time_keeps_document_changed(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        material = _material(session)
        # «Создание» материала уже экспортировано: смена оценки должна
        # дать отдельную запись об изменении документа.
        for change in session.query(Change).all():
            change.exported_at = change.changed_at
        session.commit()

        service = EvaluationService(session)
        evaluation_list = service.create_list("ОЦ-00001", date(2026, 9, 20))
        evaluation = service.set_evaluation(
            material, EvaluationValue.USEFUL, date(2026, 9, 20), evaluation_list
        )
        session.commit()

        assert material.latest_evaluation is evaluation
        assert evaluation.evaluation_list_id == evaluation_list.id
        material_change = (
            session.query(Change)
            .filter(Change.entity_name == "ScientificMaterial")
            .one_or_none()
        )
        assert material_change is not None
        assert material_change.exported_at is None
        assert "evaluations" in (material_change.changed_fields or [])


def test_set_evaluation_replaces_exclusive_last(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        material = _material(session)
        service = EvaluationService(session)
        first = service.set_evaluation(
            material, EvaluationValue.INTERESTING, date(2026, 9, 1)
        )
        session.commit()
        first_id = first.id

        second = service.set_evaluation(
            material, EvaluationValue.IMPORTANT, date(2026, 9, 5)
        )
        session.commit()

        assert material.latest_evaluation is second
        # Одиночная прежняя оценка удалена.
        assert session.get(Evaluation, first_id) is None
        assert {e.id for e in material.evaluations} == {second.id}


def test_set_evaluation_keeps_shared_last(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        material_one = _material(session, "Первый")
        material_two = _material(session, "Второй")
        telegram = Telegram(
            type=0,
            outgoing_number="ТЛГ-1",
            outgoing_date=date(2026, 9, 2),
            name="Телеграмма",
            branch_id="FIL001",
        )
        session.add(telegram)
        session.commit()

        service = EvaluationService(session)
        shared = service.set_evaluation(
            material_one, EvaluationValue.USEFUL, date(2026, 9, 3)
        )
        shared.materials.append(material_two)
        shared.telegrams.append(telegram)
        session.commit()

        # Меняем оценку только первого документа: общая оценка
        # остаётся последней для остальных и не удаляется.
        replacement = service.set_evaluation(
            material_one, EvaluationValue.IMPORTANT, date(2026, 9, 10)
        )
        session.commit()

        assert session.get(Evaluation, shared.id) is not None
        assert material_two.latest_evaluation is shared
        assert telegram.latest_evaluation is shared
        assert material_one.latest_evaluation is replacement
        assert len(shared.materials) == 1
        assert shared.materials[0].id == material_two.id
        assert len(shared.telegrams) == 1


def test_set_evaluation_deletes_when_others_have_newer(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        material_one = _material(session, "Первый")
        material_two = _material(session, "Второй")
        service = EvaluationService(session)
        shared = service.set_evaluation(
            material_one, EvaluationValue.USEFUL, date(2026, 9, 3)
        )
        shared.materials.append(material_two)
        newer_for_two = Evaluation(
            value=EvaluationValue.IMPORTANT, date=date(2026, 9, 8)
        )
        newer_for_two.materials.append(material_two)
        session.add(newer_for_two)
        session.commit()

        # Для второго документа общая оценка уже не последняя —
        # при смене у первого она удаляется.
        replacement = service.set_evaluation(
            material_one, EvaluationValue.IMPORTANT, date(2026, 9, 12)
        )
        session.commit()

        assert session.get(Evaluation, shared.id) is None
        assert material_one.latest_evaluation is replacement
        assert material_two.latest_evaluation is newer_for_two


def test_set_evaluation_same_value_newer_date_replaces(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        material = _material(session)
        service = EvaluationService(session)
        service.set_evaluation(material, EvaluationValue.USEFUL, date(2026, 9, 1))
        again = service.set_evaluation(
            material, EvaluationValue.USEFUL, date(2026, 9, 2)
        )
        session.commit()

        assert material.latest_evaluation is again
        assert len(material.evaluations) == 1


# --- списки оценок ---


def test_suggest_list_number_continues_year_sequence(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        service = EvaluationService(session)
        assert service.suggest_list_number(date(2026, 9, 1)) == "ОЦ-00001"

        service.create_list("ОЦ-00007", date(2026, 5, 1))
        service.create_list("ОЦ-00003", date(2025, 12, 1))  # другой год
        session.commit()

        assert service.suggest_list_number(date(2026, 9, 1)) == "ОЦ-00008"
        assert service.suggest_list_number(date(2027, 1, 1)) == "ОЦ-00001"


def test_new_evaluation_goes_into_created_list(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        material = _material(session)
        service = EvaluationService(session)
        evaluation_list = service.create_list("ОЦ-00042", date(2026, 9, 15))
        evaluation = service.set_evaluation(
            material, EvaluationValue.USEFUL, date(2026, 9, 15), evaluation_list
        )
        session.commit()

        assert evaluation.evaluation_list is evaluation_list
        assert len(evaluation_list.evaluations) == 1


# --- диалог выставления оценки ---


def test_assign_dialog_suggests_number_and_filters_lists(
    db_manager: DatabaseManager,
) -> None:
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    with db_manager.get_session() as session:
        _setup(session)
        service = EvaluationService(session)
        today = date.today()
        service.create_list("ОЦ-00003", today)
        session.commit()

        dialog = EvaluationAssignDialog(session)
        # Номер следующего списка предложен автоматически.
        assert dialog.number_edit.text() == "ОЦ-00004"
        # Существующий список доступен для выбора и фильтруется по номеру;
        # текст элементов виден (не пустой).
        assert dialog.lists_widget.count() == 1
        assert dialog.lists_widget.item(0).text()
        dialog.filter_edit.setText("00003")
        assert dialog.lists_widget.count() == 1
        dialog.filter_edit.setText("9999")
        assert dialog.lists_widget.count() == 0
        dialog.filter_edit.setText("")
        assert dialog.selected_list() is not None

        value, assigned_date, mode, number, list_date, existing = dialog.get_data()
        assert mode == "new"
        assert number == "ОЦ-00004"
        assert list_date == today
        assert existing is None


# --- совокупностная оценка выделенных записей ---


def test_assign_evaluation_group_single_evaluation_with_share(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        first = _material(session, "Первый")
        second = _material(session, "Второй")
        service = EvaluationService(session)

        evaluation = service.assign_evaluation(
            [first, second], EvaluationValue.USEFUL, date(2026, 9, 20)
        )
        session.commit()

        # Одна оценка на совокупность: в списках у каждого документа
        # перед значением выводится дробная доля.
        assert len(evaluation.materials) == 2
        assert first.latest_evaluation is evaluation
        assert second.latest_evaluation is evaluation
        assert first.evaluation_share == 0.5
        assert first.evaluation_display.startswith("0,50")
        assert second.evaluation_display.startswith("0,50")


def test_assign_evaluation_group_replaces_shared_previous(
    db_manager: DatabaseManager,
) -> None:
    with db_manager.get_session() as session:
        _setup(session)
        first = _material(session, "Первый")
        second = _material(session, "Второй")
        service = EvaluationService(session)
        shared = service.set_evaluation(
            first, EvaluationValue.INTERESTING, date(2026, 9, 1)
        )
        shared.materials.append(second)
        session.commit()
        shared_id = shared.id

        # Совокупностная оценка вытесняет общую прежнюю: после снятия
        # связей она не остаётся последней ни для кого и удаляется.
        replacement = service.assign_evaluation(
            [first, second], EvaluationValue.IMPORTANT, date(2026, 9, 10)
        )
        session.commit()

        assert session.get(Evaluation, shared_id) is None
        assert first.latest_evaluation is replacement
        assert second.latest_evaluation is replacement
        assert len(replacement.materials) == 2
