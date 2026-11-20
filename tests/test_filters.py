"""Тесты фильтрации записей таблиц."""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtWidgets import QApplication, QLabel

from internal_correspondence.core.constants import MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.filter_dialog import (
    AddFilterDialog,
    FilterDialog,
    resolve_m2m_labels,
)
from internal_correspondence.gui.filter_model import (
    FilterCondition,
    deserialize_filters,
    format_filter_value,
    m2m_actual_keys,
    operators_for,
    resolve_nullable,
    resolve_pack_enum,
    resolve_value_type,
    serialize_filters,
)
from internal_correspondence.gui.table_model import ColumnDef, SqlAlchemyTableModel
from internal_correspondence.orm.models import (
    Branch,
    Country,
    Employee,
    Leader,
    ReportAddress,
    ScientificMaterial,
    ScientificTask,
    Telegram,
    TerritorialUnit,
)

MATERIAL_COLUMNS = [
    ColumnDef("type", "Тип"),
    ColumnDef("outgoing_number", "Исх. номер"),
    ColumnDef("outgoing_date", "Дата исх."),
    ColumnDef("name", "Наименование"),
    ColumnDef("branch.short_name", "Филиал"),
]

M2M_COLUMNS = [
    ColumnDef("name", "Наименование"),
    ColumnDef("countries", "Страны", filter_target=Country),
    ColumnDef(
        "tasks_display",
        "Задачи",
        filter_target=ScientificTask,
        filter_attr="tasks",
    ),
    ColumnDef(
        "report_addresses",
        "Адресация доклада",
        filter_target=Leader,
        filter_attr="report_addresses",
    ),
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
            ("Отчёт о воде", date(2024, 1, 15), MaterialType.DOCUMENT),
            ("Обзор отчётности", date(2025, 6, 1), MaterialType.MESSAGE),
            ("Методика измерений", date(2026, 1, 10), MaterialType.DOCUMENT),
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


def test_resolve_enum_and_nullable() -> None:
    """IntEnum-колонки распознаются как enum; nullability берётся из модели."""
    assert resolve_value_type(ScientificMaterial, "type") == "enum"
    assert resolve_pack_enum(ScientificMaterial, "type") == "material_type"
    assert resolve_value_type(ScientificMaterial, "name") == "text"
    assert resolve_pack_enum(ScientificMaterial, "name") is None
    assert resolve_nullable(ScientificMaterial, "incoming_number")
    assert not resolve_nullable(ScientificMaterial, "type")
    assert resolve_nullable(Telegram, "report_type")


def test_operators_for_enum_and_nullable() -> None:
    """Перечисление — условие «одно из»; nullable добавляет проверки пустоты."""
    assert [op for op, _label in operators_for("enum")] == ["in"]
    assert [op for op, _label in operators_for("enum", nullable=True)] == [
        "in", "empty", "not_empty",
    ]
    assert [op for op, _label in operators_for("text", nullable=True)] == [
        "contains", "startswith", "endswith", "empty", "not_empty",
    ]


def test_enum_condition_matches() -> None:
    """Условие «одно из» сопоставляет коды перечисления с записью."""
    condition = FilterCondition("type", "in", str(int(MaterialType.MESSAGE)))
    assert condition.matches(MaterialType.MESSAGE, "enum")
    assert condition.matches(int(MaterialType.MESSAGE), "enum")
    assert not condition.matches(MaterialType.DOCUMENT, "enum")
    assert not condition.matches(None, "enum")
    assert not condition.matches("мусор", "enum")


def test_null_operators_match() -> None:
    """«Пусто/не пусто» работают для пустых строк, NULL и любых типов."""
    empty = FilterCondition("incoming_number", "empty", "")
    assert empty.matches(None, "text")
    assert empty.matches("", "text")
    assert not empty.matches("ИСХ-1", "text")
    assert empty.matches(None, "date")
    not_empty = FilterCondition("incoming_number", "not_empty", "")
    assert not_empty.matches("ИСХ-1", "text")
    assert not not_empty.matches(None, "text")
    assert not not_empty.matches("", "text")


def test_describe_enum_and_null_conditions() -> None:
    """Описание: значения перечисления подписываются; унарные условия без значения."""
    described = FilterCondition("type", "in", str(int(MaterialType.MESSAGE))).describe(
        "Тип", "enum", "material_type"
    )
    assert described.startswith("Тип одно из «")
    assert described.endswith("»")
    assert "None" not in described
    assert (
        FilterCondition("incoming_number", "empty", "").describe("Вх. номер", "text")
        == "Вх. номер пусто"
    )


def test_condition_from_dict_accepts_new_operators() -> None:
    """Сериализация принимает «одно из» и проверки пустоты по nullability."""
    condition = FilterCondition.from_dict(
        {"column": "type", "operator": "in", "value": "0,1"}, ScientificMaterial
    )
    assert condition == FilterCondition("type", "in", "0,1")
    condition = FilterCondition.from_dict(
        {"column": "incoming_number", "operator": "empty", "value": ""},
        ScientificMaterial,
    )
    assert condition is not None
    # Проверка пустоты для обязательной колонки недопустима
    assert (
        FilterCondition.from_dict(
            {"column": "type", "operator": "not_empty", "value": ""},
            ScientificMaterial,
        )
        is None
    )
    # «Одно из» для неперечисления недопустимо
    assert (
        FilterCondition.from_dict(
            {"column": "name", "operator": "in", "value": "0"}, ScientificMaterial
        )
        is None
    )


def test_model_applies_enum_and_null_filters(db_with_materials: DatabaseManager) -> None:
    """Модель таблицы фильтрует по коду перечисления и по пустоте поля."""
    with db_with_materials.get_session() as session:
        model = SqlAlchemyTableModel(session, ScientificMaterial, MATERIAL_COLUMNS)
        model.set_filters(
            [FilterCondition("type", "in", str(int(MaterialType.DOCUMENT)))]
        )
        assert model.total() == 2

        model.set_filters([FilterCondition("incoming_number", "empty", "")])
        assert model.total() == 3


def test_filter_dialog_row_shows_field_label_without_header(qt_app) -> None:
    """Строка условия показывает метку поля, когда у колонки нет заголовка."""
    columns = [ColumnDef("name")]
    conditions = [FilterCondition("name", "contains", "отчёт")]
    dialog = FilterDialog(ScientificMaterial, columns, conditions)

    row = dialog._rows_layout.itemAt(0).widget()
    label = row.findChild(QLabel)
    assert "None" not in label.text()
    assert "Наименование" in label.text()


def test_add_filter_dialog_enum_checklist(qt_app) -> None:
    """Перечисление: чек-лист с мультивыбором; условие собирает коды выбранных."""
    columns = [ColumnDef("type", "Тип")]
    dialog = AddFilterDialog(ScientificMaterial, columns)

    assert dialog._value_type == "enum"
    assert dialog.value_stack.currentWidget() is dialog.enum_list
    assert dialog.enum_list.count() > 0
    assert [
        dialog.operator_combo.itemData(i)
        for i in range(dialog.operator_combo.count())
    ] == ["in"]
    assert dialog.condition() is None  # ничего не выбрано

    dialog.enum_list.item(0).setCheckState(Qt.Checked)
    dialog.enum_list.item(1).setCheckState(Qt.Checked)
    codes = [
        str(dialog.enum_list.item(row).data(Qt.UserRole))
        for row in range(dialog.enum_list.count())
        if dialog.enum_list.item(row).checkState() == Qt.Checked
    ]
    assert dialog.condition() == FilterCondition("type", "in", ",".join(codes))


def test_add_filter_dialog_nullable_empty_operator(qt_app) -> None:
    """Для nullable поля доступны «пусто/не пусто»; значение не требуется."""
    columns = [ColumnDef("incoming_number", "Вх. номер")]
    dialog = AddFilterDialog(ScientificMaterial, columns)
    operators = [
        dialog.operator_combo.itemData(i)
        for i in range(dialog.operator_combo.count())
    ]
    assert "empty" in operators
    assert "not_empty" in operators

    dialog.operator_combo.setCurrentIndex(dialog.operator_combo.findData("empty"))
    assert not dialog.value_stack.isEnabled()
    assert dialog.condition() == FilterCondition("incoming_number", "empty", "")

    dialog.operator_combo.setCurrentIndex(
        dialog.operator_combo.findData("contains")
    )
    assert dialog.value_stack.isEnabled()


def test_add_filter_dialog_loads_saved_condition(qt_app) -> None:
    """Редактирование: enum восстанавливает галочки, унарное условие — оператор."""
    columns = [ColumnDef("type", "Тип")]
    condition = FilterCondition("type", "in", "0")
    dialog = AddFilterDialog(ScientificMaterial, columns, condition=condition)
    assert dialog.condition() == condition
    checked = [
        dialog.enum_list.item(row).data(Qt.UserRole)
        for row in range(dialog.enum_list.count())
        if dialog.enum_list.item(row).checkState() == Qt.Checked
    ]
    assert checked == [0]

    columns = [ColumnDef("incoming_number", "Вх. номер")]
    dialog = AddFilterDialog(
        ScientificMaterial,
        columns,
        condition=FilterCondition("incoming_number", "not_empty", ""),
    )
    assert dialog.condition() == FilterCondition("incoming_number", "not_empty", "")
    assert not dialog.value_stack.isEnabled()


# ---------------------------------------------------------------------------
# Фильтры полей «многие ко многим»
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def db_with_countries(tmp_path: Path):
    """База с двумя странами и материалами, привязанными к ним."""
    from internal_correspondence.core.constants import ScientificTaskType

    db = DatabaseManager(f"sqlite:///{tmp_path / 'm2m_filters.db'}")
    db.create_tables()
    with db.get_session() as session:
        session.add(TerritorialUnit(id="TU1", name="Область"))
        session.add(Branch(id="BR1", name="Филиал 1", short_name="Ф-1", territorial_unit_id="TU1"))
        session.add(Country(id="C1", name="Австралия"))
        session.add(Country(id="C2", name="Япония"))
        session.add(
            ScientificTask(
                id="З-1",
                name="Задача первая",
                type=ScientificTaskType.MAIN,
                start_date=date(2024, 1, 1),
            )
        )
        session.commit()
        first = ScientificMaterial(
            type=MaterialType.DOCUMENT,
            outgoing_number="ИСХ-00001",
            outgoing_date=date(2026, 1, 15),
            name="Материал про Австралию",
            branch_id="BR1",
        )
        second = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="ИСХ-00002",
            outgoing_date=date(2026, 2, 1),
            name="Материал про Японию",
            branch_id="BR1",
        )
        session.add_all([first, second])
        session.flush()
        first.countries.append(session.get(Country, "C1"))
        first.tasks.append(session.get(ScientificTask, "З-1"))
        second.countries.append(session.get(Country, "C2"))
        session.commit()
    yield db
    db.close()


def test_resolve_value_type_m2m() -> None:
    """Колонки-связи N→N распознаются по имени независимо от метаданных."""
    assert resolve_value_type(ScientificMaterial, "countries") == "m2m"
    assert resolve_value_type(ScientificMaterial, "tasks_display") == "m2m"
    assert resolve_value_type(ScientificMaterial, "participating_employees") == "m2m"
    assert resolve_value_type(Telegram, "report_addresses") == "m2m"
    assert resolve_value_type(ScientificMaterial, "name") == "text"


def test_operators_for_m2m() -> None:
    """У поля N→N единственное условие — «содержит любое из»."""
    assert [op for op, _label in operators_for("m2m")] == ["in"]
    assert operators_for("m2m")[0][1] == "содержит любое из"


def test_m2m_condition_matches() -> None:
    """Условие N→N сопоставляет идентификаторы связанных записей (логика ИЛИ)."""
    condition = FilterCondition("countries", "in", "C1,C3")
    assert condition.matches(
        [Country(id="C1", name="Австралия")], "m2m"
    )
    assert not condition.matches([Country(id="C2", name="Япония")], "m2m")
    assert not condition.matches([], "m2m")
    assert not condition.matches(None, "m2m")
    # Адресация доклада: ключ берётся из leader_id
    addresses = [ReportAddress(leader_id="L2", report_date=None)]
    assert FilterCondition("report_addresses", "in", "L2").matches(addresses, "m2m")
    assert not FilterCondition("report_addresses", "in", "L1").matches(addresses, "m2m")
    # Строковое представление (коды через запятую, как у tasks_display)
    assert FilterCondition("tasks_display", "in", "З-1").matches("З-1, З-2", "m2m")
    assert not FilterCondition("tasks_display", "in", "З-3").matches("З-1", "m2m")


def test_m2m_actual_keys() -> None:
    """Ключи связанных записей: id, при его отсутствии — leader_id."""
    assert m2m_actual_keys([Country(id="C1", name="x"), ReportAddress(leader_id="L1")]) == {
        "C1",
        "L1",
    }
    assert m2m_actual_keys("К-1, К-2") == {"К-1", "К-2"}
    assert m2m_actual_keys(None) == set()


def test_m2m_serialization_roundtrip() -> None:
    """Условие N→N сохраняется в настройки и восстанавливается без потерь."""
    condition = FilterCondition("countries", "in", "C1,C2")
    restored = deserialize_filters(
        serialize_filters([condition]), ScientificMaterial
    )
    assert restored == [condition]
    # Оператор «одно из» для перечисления недопустим для текстовой колонки —
    # но для N→N допустим; посторонний оператор отбрасывается
    assert (
        FilterCondition.from_dict(
            {"column": "countries", "operator": "contains", "value": "C1"},
            ScientificMaterial,
        )
        is None
    )


def test_model_applies_m2m_filter(db_with_countries: DatabaseManager) -> None:
    """Модель таблицы фильтрует записи по связанным записям N→N."""
    with db_with_countries.get_session() as session:
        model = SqlAlchemyTableModel(session, ScientificMaterial, M2M_COLUMNS)
        assert model.total() == 2

        model.set_filters([FilterCondition("countries", "in", "C1")])
        assert model.total() == 1
        assert model.item_at(0).name == "Материал про Австралию"

        # Несколько значений: подходит запись с любым из них
        model.set_filters([FilterCondition("countries", "in", "C1,C2")])
        assert model.total() == 2

        # Фильтр по задачам читает связь через filter_attr
        model.set_filters([FilterCondition("tasks_display", "in", "З-1")])
        assert model.total() == 1

        model.set_filters([])
        assert model.total() == 2


def test_add_filter_dialog_m2m_editor(qt_app, db_with_countries: DatabaseManager) -> None:
    """Диалог добавления: список с «+»/«−», условие собирает идентификаторы."""
    with db_with_countries.get_session() as session:
        dialog = AddFilterDialog(
            ScientificMaterial, M2M_COLUMNS, session=session
        )
        dialog.column_combo.setCurrentIndex(1)  # countries
        assert dialog._value_type == "m2m"
        assert dialog.value_stack.currentWidget() is dialog.m2m_widget
        assert [
            dialog.operator_combo.itemData(i)
            for i in range(dialog.operator_combo.count())
        ] == ["in"]
        assert dialog.condition() is None  # ничего не выбрано

        australia = session.get(Country, "C1")
        japan = session.get(Country, "C2")
        dialog._m2m_items = [japan, australia]
        dialog._m2m_refresh()
        # Список отображается в алфавитном порядке
        texts = [
            dialog.m2m_list.item(row).text()
            for row in range(dialog.m2m_list.count())
        ]
        assert texts == ["Австралия", "Япония"]
        # Значение условия — идентификаторы в порядке выбора (совпадение — по множеству)
        assert dialog.condition() == FilterCondition("countries", "in", "C2,C1")

        # «−» удаляет выделенный элемент
        dialog.m2m_list.item(1).setSelected(True)
        dialog._m2m_remove_items()
        assert dialog.condition() == FilterCondition("countries", "in", "C1")


def test_add_filter_dialog_m2m_loads_condition(
    qt_app, db_with_countries: DatabaseManager
) -> None:
    """Редактирование: список восстанавливает выбранные записи по идентификаторам."""
    with db_with_countries.get_session() as session:
        condition = FilterCondition("countries", "in", "C2,C1")
        dialog = AddFilterDialog(
            ScientificMaterial,
            M2M_COLUMNS,
            condition=condition,
            session=session,
        )
        assert dialog.condition() == condition
        texts = [
            dialog.m2m_list.item(row).text()
            for row in range(dialog.m2m_list.count())
        ]
        assert texts == ["Австралия", "Япония"]


def test_filter_dialog_m2m_row_shows_names(
    qt_app, db_with_countries: DatabaseManager
) -> None:
    """Строка условия показывает имена связанных записей, а не идентификаторы."""
    with db_with_countries.get_session() as session:
        condition = FilterCondition("countries", "in", "C1,C2")
        dialog = FilterDialog(
            ScientificMaterial, M2M_COLUMNS, [condition], session=session
        )
        row = dialog._rows_layout.itemAt(0).widget()
        label = row.findChild(QLabel)
        assert "Страны содержит любое из «Австралия, Япония»" == label.text()

        # Без сессии отображаются сырые идентификаторы — диалог не падает
        dialog = FilterDialog(ScientificMaterial, M2M_COLUMNS, [condition])
        row = dialog._rows_layout.itemAt(0).widget()
        label = row.findChild(QLabel)
        assert "C1" in label.text() and "C2" in label.text()


def test_resolve_m2m_labels_and_uuid_coercion(
    db_with_countries: DatabaseManager,
) -> None:
    """Имена связанных записей разрешаются по идентификаторам; UUID-ключи приводятся."""
    import uuid as uuid_module

    from internal_correspondence.gui.filter_model import coerce_filter_ids

    with db_with_countries.get_session() as session:
        labels = resolve_m2m_labels(session, Country, "C2,C1")
        assert labels == ["Япония", "Австралия"]
        # Порядок следует условию, а не алфавиту
        labels = resolve_m2m_labels(session, Country, "C1,C2")
        assert labels == ["Австралия", "Япония"]

    valid = str(uuid_module.uuid4())
    coerced = coerce_filter_ids(Employee, ["not-a-uuid", valid])
    assert coerced == [uuid_module.UUID(valid)]
    assert coerce_filter_ids(Country, ["C1"]) == ["C1"]
