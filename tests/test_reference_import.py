"""Тесты импорта справочных данных из Excel."""

from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy.orm import Session

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.importexport.reference_import import (
    ACTUAL_IMPORTERS,
    PRIMARY_IMPORTERS,
    import_actual_data,
    import_primary_data,
)
from internal_correspondence.orm.models import (
    AcademicTitle,
    Branch,
    Consumer,
    Country,
    Leader,
    ScientificTask,
    TerritorialUnit,
)
from internal_correspondence.services.change_tracking import register_change_tracking


def _create_primary_xlsx(path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)

    sheet = workbook.create_sheet("Территориальные единицы")
    sheet.append(["Сокращенное наименование", "Наименование"])
    sheet.append(["MSK", "Москва"])

    sheet = workbook.create_sheet("Филиалы")
    sheet.append(["Индекс", "Наименование", "Сокращенное наименование", "Территориальная единица"])
    sheet.append(["FIL001", "Филиал 1", "Ф-1", "MSK"])

    sheet = workbook.create_sheet("Страны")
    sheet.append(["Сокращенное наименование", "Наименование"])
    sheet.append(["RUS", "Россия"])

    sheet = workbook.create_sheet("Научные звания")
    sheet.append(["Сокращенное наименование", "Наименование", "Род. падеж", "Дат. падеж", "Порядок"])
    sheet.append(["Д-р", "Доктор", "Доктора", "Доктору", 1])

    workbook.save(path)


def _create_actual_xlsx(path: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)

    sheet = workbook.create_sheet("Научные задачи")
    sheet.append([
        "Код", "Наименование", "Тип", "Начало действия",
        "Конец действия", "Комментарий", "Частичное решение", "Полное решение",
    ])
    sheet.append(["TASK-1", "Задача 1", "ОЗ", "2024-01-01", "2024-12-31", "", 50, 100])

    sheet = workbook.create_sheet("Потребители")
    sheet.append(["Индекс", "Сокращенное наименование", "Наименование"])
    sheet.append(["CONS-1", "Потр-1", "Потребитель 1"])

    sheet = workbook.create_sheet("Руководители")
    sheet.append(["Сокращенное наименование", "Действительный"])
    sheet.append(["LEAD-1", "Да"])

    workbook.save(path)


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_tables()
    yield db
    db.close()


def test_import_primary_data(db_manager: DatabaseManager, tmp_path: Path) -> None:
    path = tmp_path / "primary.xlsx"
    _create_primary_xlsx(path)

    with db_manager.get_session() as session:
        results = import_primary_data(session, path)
        session.commit()

    assert results["Территориальные единицы"] == 1
    assert results["Филиалы"] == 1
    assert results["Страны"] == 1
    assert results["Научные звания"] == 1

    with db_manager.get_session() as session:
        assert session.query(TerritorialUnit).count() == 1
        assert session.query(Branch).count() == 1
        assert session.query(Country).count() == 1
        assert session.query(AcademicTitle).count() == 1


def test_import_actual_data(db_manager: DatabaseManager, tmp_path: Path) -> None:
    path = tmp_path / "actual.xlsx"
    _create_actual_xlsx(path)

    with db_manager.get_session() as session:
        results = import_actual_data(session, path)
        session.commit()

    assert results["Научные задачи"] == 1
    assert results["Потребители"] == 1
    assert results["Руководители"] == 1

    with db_manager.get_session() as session:
        assert session.query(ScientificTask).count() == 1
        assert session.query(Consumer).count() == 1
        assert session.query(Leader).count() == 1


def test_import_skips_existing(db_manager: DatabaseManager, tmp_path: Path) -> None:
    path = tmp_path / "primary.xlsx"
    _create_primary_xlsx(path)

    with db_manager.get_session() as session:
        import_primary_data(session, path)
        session.commit()

    with db_manager.get_session() as session:
        results = import_primary_data(session, path)
        session.commit()

    assert results["Территориальные единицы"] == 0
    assert results["Филиалы"] == 0
