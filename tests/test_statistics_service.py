"""Тесты статистических подсчётов."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
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
    WorkingGroup,
)
from internal_correspondence.reports.statistics_service import (
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
        working_group_id=workgroup.id,
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
        type="ОЗ",
        start_date=date(2026, 1, 1),
    )
    session.add(task)
    session.add(Source(id="S1", type="НТ", comment="Первый"))
    session.add(Source(id="S2", type="ЭО", comment=None))
    session.flush()

    material1 = ScientificMaterial(
        type="С",
        name="Материал 1",
        branch_id="F1",
        outgoing_date=date(2026, 2, 10),
        consumer_id="C1",
        tasks=[task],
    )
    material2 = ScientificMaterial(
        type="С",
        name="Материал 2",
        branch_id="F1",
        outgoing_date=date(2026, 5, 10),
        tasks=[task],
    )
    material3 = ScientificMaterial(
        type="С",
        name="Материал 3",
        branch_id="F1",
        outgoing_date=date(2026, 8, 10),
    )
    material0 = ScientificMaterial(
        type="С",
        name="Материал 0",
        branch_id="F1",
        outgoing_date=date(2025, 11, 5),
    )
    session.add_all([material0, material1, material2, material3])

    telegram = Telegram(
        type="Т",
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
        id=None, value="П", evaluation_list_id=evaluation_list1.id
    )
    evaluation_important = Evaluation(
        id=None, value="В", evaluation_list_id=evaluation_list2.id
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

        assert widget.split_slider.value() == 50
        widget.split_slider.setValue(30)
        assert widget.content_layout.stretch(0) == 30
        assert widget.content_layout.stretch(2) == 70

        widget.period_combo.setCurrentIndex(3)
        widget.refresh()
        assert widget.table.columnCount() == 3
        assert widget.table.horizontalHeaderItem(1).text() == "Январь"
        assert widget.table.horizontalHeaderItem(2).text() == "Итого"
    finally:
        session.close()
