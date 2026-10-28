"""Тесты фильтрации записей таблиц."""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.filter_dialog import AddFilterDialog, FilterDialog
from internal_correspondence.gui.filter_model import (
    FilterCondition,
    format_filter_value,
    operators_for,
    resolve_value_type,
)
from internal_correspondence.gui.table_model import ColumnDef, SqlAlchemyTableModel
from internal_correspondence.orm.models import (
    Branch,
    Employee,
    ScientificMaterial,
    TerritorialUnit,
)

MATERIAL_COLUMNS = [
    ColumnDef("type", "Тип"),
    ColumnDef("outgoing_number", "Исх. номер"),
    ColumnDef("outgoing_date", "Дата исх."),
    ColumnDef("name", "Наименование"),
    ColumnDef("branch.short_name", "Филиал"),
]


@pytest.fixture(scope="module")
def qt_app():
    """Создаёт единственный QApplication для тестов виджетов."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_with_materials(tmp_path: Path):
    """Создаёт БД с тремя научными материалами."""
    db = DatabaseManager(f"sqlite:///{tmp_path / 'filters.db'}")
    db.create_tables()
    with db.get_session() as session:
        session.add(TerritorialUnit(id="TU1", name="Область"))
        session.add(Branch(id="BR1", name="Филиал 1", short_name="Ф-1", territorial_unit_id="TU1"))
        session.commit()
        rows = [
            ("Отчёт о воде", date(2024, 1, 15), "ДОК"),
            ("Обзор отчётности", date(2025, 6, 1), "С"),
            ("Методика измерений", date(2026, 1, 10), "ДОК"),
        ]
        for index, (name, outgoing_date, material_type) in enumerate(rows, start=1):
            session.add(
                ScientificMaterial(
                    type=material_type,
                    outgoing_number=f"ИСХ-{index:05d}",
                    outgoing_date=outgoing_date,
                    name=name,
                    branch_id="BR1",
                )
            )
        session.commit()
    yield db
    db.close()


def test_resolve_value_types() -> None:
    """Типы колонок определяются по ORM-модели, включая вложенные связи."""
    assert resolve_value_type(ScientificMaterial, "name") == "text"
    assert resolve_value_type(ScientificMaterial, "outgoing_date") == "date"
    assert resolve_value_type(ScientificMaterial, "release_year") == "integer"
    assert resolve_value_type(ScientificMaterial, "cost") == "number"
    assert resolve_value_type(ScientificMaterial, "branch.short_name") == "text"
    assert resolve_value_type(Employee, "active") == "bool"


def test_operators_by_type() -> None:
    """Набор условий зависит от типа поля."""
    assert [label for _, label in operators_for("text")] == [
        "содержит",
        "начинается с",
        "заканчивается на",
    ]
    assert [label for _, label in operators_for("date")] == ["=", "≠", ">", "≥", "<", "≤"]
    assert [label for _, label in operators_for("number")] == ["=", "≠", ">", "≥", "<", "≤"]
    assert [label for _, label in operators_for("integer")] == ["=", "≠", ">", "≥", "<", "≤"]
    assert [label for _, label in operators_for("bool")] == ["=", "≠"]


def test_text_conditions() -> None:
    """Текстовые условия не чувствительны к регистру."""
    assert FilterCondition("name", "contains", "отчёт").matches("Отчёт о воде", "text")
    assert not FilterCondition("name", "contains", "отчёт").matches("Методика", "text")
    assert FilterCondition("name", "startswith", "отч").matches("Отчёт", "text")
    assert FilterCondition("name", "endswith", "воде").matches("Отчёт о воде", "text")


def test_date_and_number_conditions() -> None:
    """Условия сравнения работают для дат, чисел и логических значений."""
    assert FilterCondition("outgoing_date", "ge", "2025-01-01").matches(date(2025, 6, 1), "date")
    assert not FilterCondition("outgoing_date", "lt", "2025-01-01").matches(date(2025, 6, 1), "date")
    assert not FilterCondition("outgoing_date", "gt", "").matches(date(2025, 6, 1), "date")
    assert not FilterCondition("outgoing_date", "gt", "2025-01-01").matches(None, "date")
    assert FilterCondition("cost", "gt", "100.5").matches(Decimal("150.00"), "number")
    assert FilterCondition("active", "eq", "true").matches(True, "bool")
    assert FilterCondition("active", "ne", "true").matches(False, "bool")


def test_describe_formatting() -> None:
    """Описание условия показывает заголовок, условие и форматированное значение."""
    assert FilterCondition("name", "contains", "отчёт").describe("Наименование", "text") == (
        "Наименование содержит «отчёт»"
    )
    assert FilterCondition("outgoing_date", "ge", "2025-01-01").describe("Дата исх.", "date") == (
        "Дата исх. ≥ 01.01.2025"
    )
    assert format_filter_value("true", "bool") == "Да"


def test_model_applies_filters(db_with_materials: DatabaseManager) -> None:
    """Модель таблицы учитывает все условия фильтрации одновременно."""
    with db_with_materials.get_session() as session:
        model = SqlAlchemyTableModel(session, ScientificMaterial, MATERIAL_COLUMNS)
        assert model.total() == 3

        model.set_filters([FilterCondition("name", "contains", "отчёт")])
        assert model.total() == 2
        assert model.page() == 1

        model.set_filters(
            [
                FilterCondition("name", "contains", "отчёт"),
                FilterCondition("outgoing_date", "ge", "2025-01-01"),
            ]
        )
        assert model.total() == 1
        assert model.item_at(0).name == "Обзор отчётности"

        model.set_filters([])
        assert model.total() == 3


def test_filter_dialog_rows_and_removal(qt_app, db_with_materials: DatabaseManager) -> None:
    """Диалог показывает условия и удаляет их по кнопке."""
    conditions = [
        FilterCondition("name", "contains", "отчёт"),
        FilterCondition("outgoing_date", "ge", "2025-01-01"),
    ]
    dialog = FilterDialog(ScientificMaterial, MATERIAL_COLUMNS, conditions)

    labels = [
        dialog._rows_layout.itemAt(index).widget()
        for index in range(dialog._rows_layout.count())
        if dialog._rows_layout.itemAt(index).widget() is not None
    ]
    assert len(labels) == 2

    emitted = []
    dialog.filtersChanged.connect(emitted.append)
    dialog._remove_filter(conditions[1])

    assert dialog.filters() == [conditions[0]]
    assert emitted == [[conditions[0]]]


def test_add_filter_dialog_switches_value_editor(qt_app) -> None:
    """Диалог добавления подстраивает условия и редактор значения под тип поля."""
    dialog = AddFilterDialog(ScientificMaterial, MATERIAL_COLUMNS)

    dialog.column_combo.setCurrentIndex(3)
    assert dialog._value_type == "text"
    assert [dialog.operator_combo.itemText(i) for i in range(dialog.operator_combo.count())] == [
        "содержит",
        "начинается с",
        "заканчивается на",
    ]
    assert dialog.condition() is None

    dialog.text_edit.setText("отчёт")
    assert dialog.condition() == FilterCondition("name", "contains", "отчёт")

    dialog.column_combo.setCurrentIndex(2)
    assert dialog._value_type == "date"
    assert dialog.value_stack.currentWidget() is dialog.date_edit
    dialog.operator_combo.setCurrentIndex(3)
    dialog.date_edit.setDate(QDate.fromString("2025-03-01", "yyyy-MM-dd"))
    assert dialog.condition() == FilterCondition("outgoing_date", "ge", "2025-03-01")


def test_add_filter_dialog_integer_editor(qt_app) -> None:
    """Для целочисленного поля используется числовой редактор без дробной части."""
    columns = [ColumnDef("release_year", "Год выпуска")]
    dialog = AddFilterDialog(ScientificMaterial, columns)

    assert dialog._value_type == "integer"
    assert dialog.value_stack.currentWidget() is dialog.int_edit
    dialog.int_edit.setValue(2024)
    assert dialog.condition() == FilterCondition("release_year", "eq", "2024")
