"""Тесты статистических подсчётов."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.constants import (
    EvaluationValue,
    MaterialType,
    ScientificTaskType,
    SourceType,
    TelegramType,
)
from internal_correspondence.orm.models import (
    AddedTask,
    Branch,
    Consumer,
    Department,
    Employee,
    Evaluation,
    EvaluationList,
    ScientificMaterial,
    ScientificTask,
    Source,
    Telegram,
    TerritorialUnit,
    WorkGroupMembership,
    WorkingGroup,
)
from internal_correspondence.reports.statistics_service import (
    CRITERION_BRANCH,
    CRITERION_CONSUMER,
    CRITERION_DEPARTMENT,
    CRITERION_EMPLOYEE,
    CRITERION_EVALUATION,
    CRITERION_SOURCE,
    CRITERION_TASK,
    CRITERION_WORKGROUP,
    PERIOD_HALF,
    PERIOD_MONTH,
    PERIOD_QUARTER,
    PERIOD_YEAR,
    StatisticsQuery,
    StatisticsService,
)
from internal_correspondence.services.change_tracking import register_change_tracking


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'statistics.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def statistics_setup(db_manager: DatabaseManager) -> dict:
    session = db_manager.get_session()
    session.add(TerritorialUnit(id="MSK", name="Москва"))
    session.add(Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK"))
    department = Department(id=None, name="Отдел", branch_id="F1")
    session.add(department)
    session.flush()

    workgroup = WorkingGroup(id=None, name="Группа", department_id=department.id)
    session.add(workgroup)
    session.flush()

    employee1 = Employee(
        id=None,
        last_name="Иванов",
        first_name="Иван",
        department_id=department.id,
        workgroup_memberships=[WorkGroupMembership(working_group=workgroup)],
    )
    employee2 = Employee(
        id=None,
        last_name="Петров",
        first_name="Пётр",
        department_id=department.id,
    )
    session.add_all([employee1, employee2])
    session.add(Consumer(id="C1", short_name="П1", name="Потребитель 1"))
    task = ScientificTask(
        id="T1",
        name="Задача 1",
        type=ScientificTaskType.MAIN,
        start_date=date(2026, 1, 1),
    )
    session.add(task)
    session.add(Source(id="S1", type=SourceType.SCIENTIFIC_WORK, comment="Первый"))
    session.add(Source(id="S2", type=SourceType.EXPERIMENTAL_EQUIPMENT, comment=None))
    session.flush()

    # Иванов назначен исполнителем задачи T1 (механизм распределения задач)
    session.add(
        AddedTask(task_id="T1", node_type="employee", node_id=str(employee1.id))
    )
    session.flush()

    material1 = ScientificMaterial(
        type=MaterialType.MESSAGE,
        name="Материал 1",
        branch_id="F1",
        outgoing_date=date(2026, 2, 10),
        consumer_id="C1",
        tasks=[task],
    )
    material2 = ScientificMaterial(
        type=MaterialType.MESSAGE,
        name="Материал 2",
        branch_id="F1",
        outgoing_date=date(2026, 5, 10),
        tasks=[task],
    )
    material3 = ScientificMaterial(
        type=MaterialType.MESSAGE,
        name="Материал 3",
        branch_id="F1",
        outgoing_date=date(2026, 8, 10),
    )
    material0 = ScientificMaterial(
        type=MaterialType.MESSAGE,
        name="Материал 0",
        branch_id="F1",
        outgoing_date=date(2025, 11, 5),
    )
    session.add_all([material0, material1, material2, material3])

    telegram = Telegram(
        type=TelegramType.THEMATIC,
        name="Телеграмма 1",
        branch_id="F1",
        outgoing_date=date(2026, 5, 10),
    )
    session.add(telegram)
    session.flush()

    material1.employees = [employee1]
    material1.sources = [session.get(Source, "S1")]
    material2.employees = [employee1, employee2]
    material2.sources = [session.get(Source, "S2")]
    material3.employees = [employee2]
    material0.employees = [employee1]
    telegram.employees = [employee1]

    evaluation_list1 = EvaluationList(id=None, number="1", date=date(2026, 3, 1))
    evaluation_list2 = EvaluationList(id=None, number="2", date=date(2026, 6, 1))
    session.add_all([evaluation_list1, evaluation_list2])
    session.flush()

    evaluation_useful = Evaluation(
        id=None,
        value=EvaluationValue.USEFUL,
        date=date(2026, 3, 1),
        evaluation_list_id=evaluation_list1.id,
    )
    evaluation_important = Evaluation(
        id=None,
        value=EvaluationValue.IMPORTANT,
        date=date(2026, 6, 1),
        evaluation_list_id=evaluation_list2.id,
    )
    session.add_all([evaluation_useful, evaluation_important])
    session.flush()
    material1.evaluations = [evaluation_useful]
    material2.evaluations = [evaluation_useful]
    material3.evaluations = [evaluation_important]

    session.commit()

    data = {
        "department_id": department.id,
        "workgroup_id": workgroup.id,
        "employee1_id": employee1.id,
        "employee2_id": employee2.id,
        "material1_id": material1.id,
    }
    session.close()
    return data


def _service(db_manager: DatabaseManager) -> StatisticsService:
    return StatisticsService(db_manager.get_session())


def _query(**overrides) -> StatisticsQuery:
    params = {
        "model_class": ScientificMaterial,
        "criterion": CRITERION_EMPLOYEE,
        "period_type": PERIOD_YEAR,
        "year": 2026,
    }
    params.update(overrides)
    return StatisticsQuery(**params)


def _by_column(result, values) -> dict:
    return {
        column.split(" (")[0]: value
        for column, value in zip(result.columns, values)
    }


def test_year_employee_counts(statistics_setup, db_manager: DatabaseManager) -> None:
    result = _service(db_manager).calculate(_query())

    assert len(result.columns) == 18
    assert len(result.month_columns) == 12
    assert [row.label for row in result.rows] == ["Иванов И.", "Петров П."]
    ivanov, petrov = result.rows

    ivanov_values = _by_column(result, ivanov.values)
    assert ivanov_values["Февраль"] == 1
    assert ivanov_values["Май"] == 1
    assert ivanov_values["I квартал"] == 1
    assert ivanov_values["II квартал"] == 1
    assert ivanov_values["I полугодие"] == 2
    assert ivanov_values["II полугодие"] == 0
    assert ivanov.total == 2

    petrov_values = _by_column(result, petrov.values)
    assert petrov_values["Май"] == 1
    assert petrov_values["Август"] == 1
    assert petrov_values["I полугодие"] == 1
    assert petrov_values["II полугодие"] == 1
    assert petrov_values["II квартал"] == 1
    assert petrov_values["III квартал"] == 1
    assert petrov.total == 2

    totals = _by_column(result, result.totals)
    assert totals["I полугодие"] == 3
    assert totals["II полугодие"] == 1
    assert totals["I квартал"] == 1
    assert totals["II квартал"] == 2
    assert totals["III квартал"] == 1
    assert totals["IV квартал"] == 0
    assert result.grand_total == 4


def test_departments_are_counted_once_per_document(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    result = _service(db_manager).calculate(_query(criterion=CRITERION_DEPARTMENT))

    assert len(result.rows) == 1
    assert result.rows[0].label == "Отдел"
    assert result.rows[0].total == 3
    assert result.grand_total == 3


def test_workgroups_count(statistics_setup, db_manager: DatabaseManager) -> None:
    result = _service(db_manager).calculate(_query(criterion=CRITERION_WORKGROUP))

    assert len(result.rows) == 1
    assert result.rows[0].label == "Группа"
    assert result.rows[0].total == 2


def test_consumer_and_task_and_source_counts(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    service = _service(db_manager)

    consumer = service.calculate(_query(criterion=CRITERION_CONSUMER))
    assert [row.label for row in consumer.rows] == ["П1"]
    assert consumer.rows[0].total == 1

    task = service.calculate(_query(criterion=CRITERION_TASK))
    assert [row.label for row in task.rows] == ["Задача 1"]
    assert task.rows[0].total == 2

    sources = service.calculate(_query(criterion=CRITERION_SOURCE))
    assert [row.label for row in sources.rows] == ["Научный труд (Первый)", "Экспериментальное оборудование"]
    assert [row.total for row in sources.rows] == [1, 1]


def test_evaluation_breakdown_by_values(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    result = _service(db_manager).calculate(_query(criterion=CRITERION_EVALUATION))

    assert [row.label for row in result.rows] == [
        "Бесполезно",
        "Интересно",
        "Полезно",
        "Важно",
    ]
    by_label = {row.label: row for row in result.rows}
    useful_values = _by_column(result, by_label["Полезно"].values)
    assert useful_values["Февраль"] == 1
    assert useful_values["Май"] == 1
    assert useful_values["I квартал"] == 1
    assert useful_values["II квартал"] == 1
    assert useful_values["I полугодие"] == 2
    assert by_label["Полезно"].total == 2

    important_values = _by_column(result, by_label["Важно"].values)
    assert important_values["Август"] == 1
    assert important_values["III квартал"] == 1
    assert important_values["II полугодие"] == 1
    assert by_label["Важно"].total == 1
    assert by_label["Бесполезно"].total == 0
    assert result.grand_total == 3


def test_telegrams_are_counted_separately(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    result = _service(db_manager).calculate(
        _query(model_class=Telegram, criterion=CRITERION_EMPLOYEE)
    )

    assert len(result.rows) == 1
    assert result.rows[0].label == "Иванов И."
    assert result.rows[0].total == 1


def test_financial_year_periods(statistics_setup, db_manager: DatabaseManager) -> None:
    result = _service(db_manager).calculate(_query(year=2025, financial=True))

    assert "Финансовый год 2025/2026" in result.period_label
    assert len(result.columns) == 18
    assert result.columns[0] == "Октябрь"
    assert result.columns[3] == "I квартал"
    assert result.columns[8] == "I полугодие"
    assert result.columns[12] == "III квартал"
    assert result.columns[16] == "IV квартал"
    assert result.columns[17] == "II полугодие"

    ivanov, petrov = result.rows
    ivanov_values = _by_column(result, ivanov.values)
    assert ivanov_values["Ноябрь"] == 1
    assert ivanov_values["Февраль"] == 1
    assert ivanov_values["Май"] == 1
    assert ivanov_values["I полугодие"] == 2
    assert ivanov_values["II полугодие"] == 1
    assert ivanov_values["I квартал"] == 1
    assert ivanov_values["II квартал"] == 1
    assert ivanov_values["III квартал"] == 1
    assert ivanov.total == 3

    petrov_values = _by_column(result, petrov.values)
    assert petrov_values["Май"] == 1
    assert petrov_values["Август"] == 1
    assert petrov_values["I полугодие"] == 0
    assert petrov_values["II полугодие"] == 2
    assert petrov_values["III квартал"] == 1
    assert petrov_values["IV квартал"] == 1
    assert petrov.total == 2


def test_half_quarter_and_month_columns(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    service = _service(db_manager)

    half = service.calculate(_query(period_type=PERIOD_HALF, half=1))
    assert half.columns == [
        "Январь",
        "Февраль",
        "Март",
        "I квартал",
        "Апрель",
        "Май",
        "Июнь",
        "II квартал",
    ]
    assert half.grand_total == 3

    quarter = service.calculate(_query(period_type=PERIOD_QUARTER, quarter=2))
    assert quarter.columns == ["Апрель", "Май", "Июнь"]
    by_label = {row.label: row for row in quarter.rows}
    assert by_label["Иванов И."].values == [0, 1, 0]
    assert by_label["Петров П."].values == [0, 1, 0]
    assert quarter.grand_total == 2

    month = service.calculate(_query(period_type=PERIOD_MONTH, month=5))
    assert month.columns == ["Май"]
    assert month.grand_total == 2


def test_available_years_follow_database(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    service = _service(db_manager)

    assert service.available_period_years(ScientificMaterial) == [2025, 2026]
    assert service.available_period_years(ScientificMaterial, financial=True) == [2025]

    telegram_service = StatisticsService(db_manager.get_session(), branch_id="UNKNOWN")
    assert telegram_service.available_period_years(Telegram) == [date.today().year]


def test_statistics_widget_displays_table(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        assert widget.year_combo.currentData() == 2026
        widget.refresh()

        assert widget.table.columnCount() == 20
        assert widget.table.rowCount() == 3
        assert widget.table.horizontalHeaderItem(0).text() == "Сотрудники"
        assert widget.table.horizontalHeaderItem(19).text() == "Итого"

        series = widget.chart_view.chart().series()
        assert series
        bar_sets = series[0].barSets()
        assert len(bar_sets) == 2
        assert bar_sets[0].count() == 12
        assert bar_sets[0].color() != bar_sets[1].color()
        horizontal_axes = widget.chart_view.chart().axes(Qt.Horizontal)
        assert horizontal_axes[0].categories() == [
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь",
        ]

                # Таблица — центральный элемент, график — док-панель
        assert widget.main_window.centralWidget() is widget.table
        assert widget.chart_dock.widget() is not widget.table
        assert widget.chart_dock.isVisibleTo(widget)

        widget.period_combo.setCurrentIndex(3)
        widget.refresh()
        assert widget.table.columnCount() == 3
        assert widget.table.horizontalHeaderItem(1).text() == "Январь"
        assert widget.table.horizontalHeaderItem(2).text() == "Итого"
    finally:
        session.close()



def test_branch_criterion(statistics_setup, db_manager: DatabaseManager) -> None:
    """Критерий «Филиалы»: документы группируются по филиалам."""
    result = _service(db_manager).calculate(_query(criterion=CRITERION_BRANCH))

    assert len(result.rows) == 1
    assert result.rows[0].label == "Ф"
    assert result.rows[0].key == "F1"
    assert result.rows[0].total == 3
    assert result.grand_total == 3


def test_grouped_by_department_and_employees(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    """Подкатегория: сотрудники сгруппированы по отделам, итог отдела — сумма."""
    result = _service(db_manager).calculate(
        _query(criterion=CRITERION_DEPARTMENT, subcriterion=CRITERION_EMPLOYEE)
    )

    assert [row.label for row in result.rows] == ["Отдел", "Иванов И.", "Петров П."]
    group = result.rows[0]
    assert group.is_group
    assert group.key == statistics_setup["department_id"]
    # Отдел: материал 1 (Иванов) + материал 2 (оба) + материал 3 (Петров)
    assert group.total == 4
    assert not result.rows[1].is_group
    assert result.rows[1].total == 2
    assert result.rows[2].total == 2
    assert result.grand_total == 4

    group_values = _by_column(result, group.values)
    assert group_values["Февраль"] == 1
    assert group_values["Май"] == 2
    assert group_values["Август"] == 1


def test_grouped_by_workgroup_and_employees(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    """Сотрудник вне рабочей группы не попадает в её итог."""
    result = _service(db_manager).calculate(
        _query(criterion=CRITERION_WORKGROUP, subcriterion=CRITERION_EMPLOYEE)
    )

    assert [row.label for row in result.rows] == ["Группа", "Иванов И."]
    assert result.rows[0].is_group
    assert result.rows[0].total == 2
    assert result.rows[1].total == 2


def test_grouped_by_workgroup_uses_group_on_document_date(
    db_manager: DatabaseManager,
) -> None:
    """Исторический документ относится к группе, где сотрудник был на его дату."""
    session = db_manager.get_session()
    try:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(
            Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK")
        )
        department = Department(name="Отдел", branch_id="F1")
        session.add(department)
        session.flush()

        group_one = WorkingGroup(name="Группа 1", department_id=department.id)
        group_two = WorkingGroup(name="Группа 2", department_id=department.id)
        employee = Employee(
            last_name="Иванов", first_name="Иван", department_id=department.id
        )
        session.add_all([group_one, group_two, employee])
        session.flush()

        employee.assign_working_group(group_one, start_date=date(2026, 1, 1))
        employee.current_membership.end_date = date(2026, 6, 30)
        employee.assign_working_group(group_two, start_date=date(2026, 7, 1))

        session.add_all(
            [
                ScientificMaterial(
                    type=MaterialType.MESSAGE,
                    outgoing_number="M-1",
                    outgoing_date=date(2026, 3, 10),
                    name="Материал 1",
                    branch_id="F1",
                    employees=[employee],
                ),
                ScientificMaterial(
                    type=MaterialType.MESSAGE,
                    outgoing_number="M-2",
                    outgoing_date=date(2026, 9, 10),
                    name="Материал 2",
                    branch_id="F1",
                    employees=[employee],
                ),
            ]
        )
        session.commit()

        result = StatisticsService(session).calculate(
            _query(criterion=CRITERION_WORKGROUP, subcriterion=CRITERION_EMPLOYEE)
        )

        assert [row.label for row in result.rows] == [
            "Группа 1",
            "Иванов И.",
            "Группа 2",
            "Иванов И.",
        ]
        assert [row.total for row in result.rows] == [1, 1, 1, 1]
    finally:
        session.close()


def test_evaluation_summary_average(statistics_setup, db_manager: DatabaseManager) -> None:
    """Для оценок выводится средний балл по весам пакета (П=2, В=3)."""
    result = _service(db_manager).calculate(_query(criterion=CRITERION_EVALUATION))

    # Полезно (вес 2) x2, Важно (вес 3) x1 → 7/3 ≈ 2.33
    assert result.summary == "Средний балл: 2.33"


def test_widget_branch_criterion_visibility(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Критерий «Филиалы» виден головному офису и скрыт от филиала."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        head_office_widget = StatisticsWidget(session, branch_id=None)
        branch_widget = StatisticsWidget(session, branch_id="F1")

        head_office_criteria = {
            head_office_widget.criterion_combo.itemData(index)
            for index in range(head_office_widget.criterion_combo.count())
        }
        branch_criteria = {
            branch_widget.criterion_combo.itemData(index)
            for index in range(branch_widget.criterion_combo.count())
        }
        assert CRITERION_BRANCH in head_office_criteria
        assert CRITERION_BRANCH not in branch_criteria

        head_office_widget.deleteLater()
        branch_widget.deleteLater()
    finally:
        session.close()


def test_widget_subcategory_and_chart_types(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Подкатегория и переключение типов диаграммы."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)

        # У критерия «Отделы» есть подкатегории, у «Потребители» — нет
        dept_index = widget.criterion_combo.findData(CRITERION_DEPARTMENT)
        widget.criterion_combo.setCurrentIndex(dept_index)
        assert widget.subcategory_combo.count() == 3  # «—», группы, сотрудники

        consumer_index = widget.criterion_combo.findData(CRITERION_CONSUMER)
        widget.criterion_combo.setCurrentIndex(consumer_index)
        assert widget.subcategory_combo.count() == 0

        # Группировка: строка отдела + его сотрудники
        widget.criterion_combo.setCurrentIndex(dept_index)
        widget.subcategory_combo.setCurrentIndex(
            widget.subcategory_combo.findData(CRITERION_EMPLOYEE)
        )
        widget.refresh()
        labels = [
            widget.table.item(row, 0).text() for row in range(widget.table.rowCount())
        ]
        assert labels[0] == "Отдел"
        assert labels[1].strip() == "Иванов И."
        assert labels[2].strip() == "Петров П."
        assert labels[3] == "ИТОГО"

        # Типы диаграмм строятся без ошибок
        for chart_type in range(widget.chart_type_combo.count()):
            widget.chart_type_combo.setCurrentIndex(chart_type)
            widget.refresh()
            assert widget.chart_view.chart() is not None

        widget.deleteLater()
    finally:
        session.close()


def test_widget_show_element_selects_row(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Переход из ОШС: критерий меняется, строка элемента выделяется."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        widget.show_element(("employee", str(statistics_setup["employee1_id"])))

        assert widget.criterion_combo.currentData() == CRITERION_EMPLOYEE
        selected = widget.table.selectionModel().selectedRows()
        assert len(selected) == 1
        label = widget.table.item(selected[0].row(), 0).text()
        assert "Иванов" in label

        widget.deleteLater()
    finally:
        session.close()



def test_grouped_by_task_and_employees(
    statistics_setup, db_manager: DatabaseManager
) -> None:
    """Подкатегория «Задачи → Сотрудники»: исполнители под своими задачами."""
    result = _service(db_manager).calculate(
        _query(criterion=CRITERION_TASK, subcriterion=CRITERION_EMPLOYEE)
    )

    # Исполнитель T1 — только Иванов (материалы 1 и 2); Петров не назначен
    assert [row.label for row in result.rows] == ["Задача 1", "Иванов И."]
    assert result.rows[0].is_group
    assert result.rows[0].total == 2
    assert result.rows[1].total == 2


def test_widget_grouped_chart_shades(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """На графике с подкатегорией элементы группы — оттенками её цвета."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        dept_index = widget.criterion_combo.findData(CRITERION_DEPARTMENT)
        widget.criterion_combo.setCurrentIndex(dept_index)
        widget.subcategory_combo.setCurrentIndex(
            widget.subcategory_combo.findData(CRITERION_EMPLOYEE)
        )
        widget.refresh()

        series = widget.chart_view.chart().series()
        assert series
        bar_sets = series[0].barSets()
        # На графике только элементы группы (2 сотрудника), без строки отдела
        assert len(bar_sets) == 2
        assert {bar_set.label() for bar_set in bar_sets} == {"Иванов И.", "Петров П."}
        # Оттенки одной цветовой группы: цвета различны, но оба «синего» семейства
        color1, color2 = bar_sets[0].color(), bar_sets[1].color()
        assert color1 != color2

        # Критерий «Научные задачи» тоже имеет подкатегорию
        task_index = widget.criterion_combo.findData(CRITERION_TASK)
        widget.criterion_combo.setCurrentIndex(task_index)
        assert widget.subcategory_combo.count() == 2  # «—» и «Сотрудники»

        widget.deleteLater()
    finally:
        session.close()


def test_widget_selection_highlights_bars(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Выделение строки таблицы перекрашивает её набор столбцов."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget
    from internal_correspondence.gui.theme import current_theme

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        widget.refresh()

        bar_sets = widget.chart_view.chart().series()[0].barSets()
        assert len(bar_sets) >= 2
        key1 = widget.table.item(0, 0).data(Qt.UserRole)
        key2 = widget.table.item(1, 0).data(Qt.UserRole)
        assert key1 != key2

        original = bar_sets[0].color()
        widget.table.selectRow(0)
        assert bar_sets[0].color().name() == current_theme().chart_selection.name()
        assert bar_sets[1].color().name() != current_theme().chart_selection.name()

        # Смена выделения переносит подсветку
        widget.table.selectRow(1)
        assert bar_sets[1].color().name() == current_theme().chart_selection.name()
        assert bar_sets[0].color() == original

        # Снятие выделения убирает подсветку
        widget.table.clearSelection()
        assert bar_sets[0].color() == original
        assert bar_sets[1].color().name() != current_theme().chart_selection.name()

        widget.deleteLater()
    finally:
        session.close()


def test_widget_selection_highlights_lines_and_pie(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Подсветка выделенной строки на линейной и круговой диаграммах."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget
    from internal_correspondence.gui.theme import current_theme

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        widget.refresh()

        lines_index = 1  # линейная диаграмма — второй пункт
        widget.chart_type_combo.setCurrentIndex(lines_index)
        widget.refresh()

        series_list = widget.chart_view.chart().series()
        assert len(series_list) >= 2
        normal_pen = series_list[0].pen()
        widget.table.selectRow(0)
        highlight_pen = series_list[0].pen()
        assert highlight_pen.color().name() == current_theme().chart_selection.name()
        assert highlight_pen.width() > normal_pen.width()
        assert series_list[1].pen().color().name() != current_theme().chart_selection.name()

        # Круговая диаграмма: подсветка — «взрыв» сектора
        pie_index = widget.chart_type_combo.count() - 1
        widget.chart_type_combo.setCurrentIndex(pie_index)
        widget.refresh()
        pie_series = widget.chart_view.chart().series()[0]
        slices = pie_series.slices()
        assert slices
        widget.table.selectRow(0)
        assert slices[0].isExploded()
        assert all(not slc.isExploded() for slc in slices[1:])
        # «ИТОГО» подсвечивает все сектора, снятие выделения — ни одного
        widget.table.selectRow(widget.table.rowCount() - 1)
        assert all(slc.isExploded() for slc in slices)
        widget.table.clearSelection()
        assert all(not slc.isExploded() for slc in slices)

        widget.deleteLater()
    finally:
        session.close()


def test_widget_header_fixed_and_content_stretches(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Блок заголовка фиксирован по вертикали, область таблицы/графика растягивается."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        widget.show()
        qt_app.processEvents()

        widget.resize(900, 400)
        qt_app.processEvents()
        header_height = widget.header_widget.height()
        content_height = widget.main_window.height()

        widget.resize(900, 800)
        qt_app.processEvents()
        # Заголовок не меняет высоту, область таблицы/графика забирает всё место
        assert widget.header_widget.height() == header_height
        assert widget.main_window.height() > content_height

        widget.deleteLater()
    finally:
        session.close()


def test_widget_chart_dock_is_floatable(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """График — док-панель: открепляется в отдельное окно и переносится по краям."""
    from PyQt5.QtWidgets import QDockWidget

    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        widget.show()
        qt_app.processEvents()

        features = widget.chart_dock.features()
        assert features & QDockWidget.DockWidgetFloatable
        assert features & QDockWidget.DockWidgetMovable
        # Панель нельзя закрыть и потерять
        assert not features & QDockWidget.DockWidgetClosable

        # Открепление в отдельное окно
        widget.chart_dock.setFloating(True)
        assert widget.chart_dock.isFloating()
        widget.chart_dock.setFloating(False)
        assert not widget.chart_dock.isFloating()

        # Перенос к левому краю области
        widget.main_window.addDockWidget(
            Qt.LeftDockWidgetArea, widget.chart_dock
        )
        assert widget.main_window.dockWidgetArea(widget.chart_dock) == (
            Qt.LeftDockWidgetArea
        )

        widget.deleteLater()
    finally:
        session.close()


def test_widget_nested_pie_with_subcategory(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Подкатегория + круговая: внутри категории, снаружи подкатегории
    с подписями «категория - подкатегория»."""
    from PyQt5.QtChart import QPieSeries

    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        dept_index = widget.criterion_combo.findData(CRITERION_DEPARTMENT)
        widget.criterion_combo.setCurrentIndex(dept_index)
        widget.subcategory_combo.setCurrentIndex(
            widget.subcategory_combo.findData(CRITERION_EMPLOYEE)
        )
        widget.chart_type_combo.setCurrentIndex(widget.chart_type_combo.count() - 1)
        widget.refresh()

        series = widget.chart_view.chart().series()
        assert len(series) == 2  # два кольца
        outer, inner = series[0], series[1]
        assert isinstance(outer, QPieSeries) and isinstance(inner, QPieSeries)

        # Внутреннее кольцо — категории (1 отдел), без подписей
        inner_slices = inner.slices()
        assert len(inner_slices) == 1
        assert not inner_slices[0].isLabelVisible()
        assert inner_slices[0].label() == "Отдел"

        # Внешнее кольцо — подкатегории с подписями «категория - подкатегория»
        outer_slices = outer.slices()
        assert len(outer_slices) == 2
        for slice_ in outer_slices:
            assert slice_.isLabelVisible()
            assert slice_.label().startswith("Отдел - ")
        assert {s.label() for s in outer_slices} == {
            "Отдел - Иванов И.",
            "Отдел - Петров П.",
        }

        # Выделение групповой строки взрывает и категорию, и её элементы
        widget.table.selectRow(0)
        assert inner_slices[0].isExploded()
        assert all(s.isExploded() for s in outer_slices)

        # Клик по сектору внутреннего кольца выделяет групповую строку
        qt_app.processEvents()
        inner.clicked.emit(inner_slices[0])
        qt_app.processEvents()
        rows = widget.table.selectionModel().selectedRows()
        assert len(rows) == 1
        assert widget.table.item(rows[0].row(), 0).text() == "Отдел"

        widget.deleteLater()
    finally:
        session.close()


def test_widget_chart_elements_are_thick(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Столбцы и линии нарисованы толще дефолтных."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        widget.refresh()

        bar_series = widget.chart_view.chart().series()[0]
        assert bar_series.barWidth() > 0.5

        widget.chart_type_combo.setCurrentIndex(1)  # линейная
        widget.refresh()
        line_series = widget.chart_view.chart().series()[0]
        assert line_series.pen().width() >= 3

        widget.deleteLater()
    finally:
        session.close()


def test_widget_group_selection_highlights_members(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Выделение групповой строки подсвечивает все её элементы на графике."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget
    from internal_correspondence.gui.theme import current_theme

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        dept_index = widget.criterion_combo.findData(CRITERION_DEPARTMENT)
        widget.criterion_combo.setCurrentIndex(dept_index)
        widget.subcategory_combo.setCurrentIndex(
            widget.subcategory_combo.findData(CRITERION_EMPLOYEE)
        )
        widget.refresh()

        bar_sets = widget.chart_view.chart().series()[0].barSets()
        assert len(bar_sets) == 2
        assert bar_sets[0].color().name() != current_theme().chart_selection.name()
        assert bar_sets[1].color().name() != current_theme().chart_selection.name()

        # Строка 0 — группа (отдел), строки 1-2 — её сотрудники
        widget.table.selectRow(0)
        assert bar_sets[0].color().name() == current_theme().chart_selection.name()
        assert bar_sets[1].color().name() == current_theme().chart_selection.name()

        widget.deleteLater()
    finally:
        session.close()


def test_widget_totals_selection_highlights_whole_chart(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Выбор строки «ИТОГО» подсвечивает всю диаграмму."""
    from internal_correspondence.gui.statistics_widget import StatisticsWidget
    from internal_correspondence.gui.theme import current_theme

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        widget.refresh()

        bar_sets = widget.chart_view.chart().series()[0].barSets()
        assert len(bar_sets) >= 2
        assert bar_sets[0].color().name() != current_theme().chart_selection.name()

        # Последняя строка таблицы — «ИТОГО»; выделение подсвечивает все наборы
        widget.table.selectRow(widget.table.rowCount() - 1)
        for bar_set in bar_sets:
            assert bar_set.color().name() == current_theme().chart_selection.name()

        # Возврат к обычной строке подсвечивает только её
        widget.table.selectRow(0)
        assert bar_sets[0].color().name() == current_theme().chart_selection.name()
        assert bar_sets[1].color().name() != current_theme().chart_selection.name()

        widget.deleteLater()
    finally:
        session.close()


def test_widget_chart_click_selects_table_row(
    statistics_setup, db_manager: DatabaseManager, qt_app
) -> None:
    """Клик по элементу диаграммы выделяет соответствующую строку таблицы."""
    from PyQt5.QtCore import QPointF

    from internal_correspondence.gui.statistics_widget import StatisticsWidget

    session = db_manager.get_session()
    try:
        widget = StatisticsWidget(session)
        widget.refresh()

        def selected_label() -> str:
            # выделение строки откладывается таймером на следующую итерацию цикла событий
            qt_app.processEvents()
            rows = widget.table.selectionModel().selectedRows()
            assert len(rows) == 1
            return widget.table.item(rows[0].row(), 0).text().strip()

        # Столбцы: клик по второму набору выделяет вторую строку
        bar_series = widget.chart_view.chart().series()[0]
        bar_sets = bar_series.barSets()
        second_label = widget.table.item(1, 0).text().strip()
        bar_series.clicked.emit(0, bar_sets[1])
        assert selected_label() == second_label

        # Линии: клик по точке первой серии выделяет первую строку
        widget.chart_type_combo.setCurrentIndex(1)
        widget.refresh()
        line_series = widget.chart_view.chart().series()[0]
        first_label = widget.table.item(0, 0).text().strip()
        line_series.clicked.emit(QPointF(0, 0))
        assert selected_label() == first_label

        # Круговая: клик по сектору выделяет его строку
        widget.chart_type_combo.setCurrentIndex(widget.chart_type_combo.count() - 1)
        widget.refresh()
        pie_series = widget.chart_view.chart().series()[0]
        slices = pie_series.slices()
        slice_label = slices[1].label().strip()
        pie_series.clicked.emit(slices[1])
        assert selected_label() == slice_label

        widget.deleteLater()
    finally:
        session.close()



def test_excel_export(statistics_setup, db_manager: DatabaseManager, tmp_path: Path) -> None:
    """Выгрузка результата в Excel: заголовки, строки, итоги, жирные группы."""
    from openpyxl import load_workbook

    from internal_correspondence.reports.statistics_export import export_statistics

    result = _service(db_manager).calculate(
        _query(criterion=CRITERION_DEPARTMENT, subcriterion=CRITERION_EMPLOYEE)
    )
    path = tmp_path / "statistics.xlsx"
    export_statistics(result, "Отделы / Сотрудники", path)

    workbook = load_workbook(path)
    sheet = workbook.active

    assert sheet.cell(row=1, column=1).value == "Научные материалы — Отделы / Сотрудники"
    assert sheet.cell(row=5, column=1).value == "Отделы / Сотрудники"
    assert sheet.cell(row=5, column=20).value == "Итого"

    # Строка 6 — группа «Отдел» (жирная), далее её сотрудники
    assert sheet.cell(row=6, column=1).value == "Отдел"
    assert sheet.cell(row=6, column=1).font.bold
    assert sheet.cell(row=6, column=20).value == 4
    assert sheet.cell(row=7, column=1).value == "Иванов И."
    assert not sheet.cell(row=7, column=1).font.bold

    # Последняя строка — общий итог
    last_row = 6 + len(result.rows)
    assert sheet.cell(row=last_row, column=1).value == "ИТОГО"
    assert sheet.cell(row=last_row, column=20).value == 4
