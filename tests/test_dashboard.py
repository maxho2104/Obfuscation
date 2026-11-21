"""Тесты вкладки «Дашборд»."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtChart import QStackedBarSeries
from PyQt5.QtWidgets import QApplication, QScrollArea

from internal_correspondence.core.constants import (
    EvaluationValue,
    MaterialType,
    ScientificTaskType,
    TelegramReportType,
    TelegramType,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.dashboard_widget import (
    _EVALUATION_COLORS,
    DashboardWidget,
    KpiCard,
)
from internal_correspondence.orm.models import (
    AddedTask,
    Branch,
    Department,
    Evaluation,
    EvaluationList,
    ScientificMaterial,
    ScientificTask,
    Telegram,
    TerritorialUnit,
)
from internal_correspondence.reports.dashboard_service import (
    DashboardFilter,
    DashboardService,
)
from internal_correspondence.reports.statistics_service import PERIOD_MONTH
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.utils.string_resources import STRINGS


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'dashboard.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def dashboard_data(db_manager: DatabaseManager) -> dict:
    session = db_manager.get_session()
    session.add(TerritorialUnit(id="REG", name="Регион"))
    session.add(Branch(id="F1", name="Филиал 1", short_name="Ф-1", territorial_unit_id="REG"))
    department = Department(name="Отдел 1", branch_id="F1")
    session.add(department)
    session.flush()

    evaluation_list = EvaluationList(number="1", date=date(2026, 1, 10))
    session.add(evaluation_list)
    session.flush()

    material1 = ScientificMaterial(
        type=MaterialType.MESSAGE,
        outgoing_number="M-1",
        outgoing_date=date(2026, 3, 5),
        name="Материал 1",
        branch_id="F1",
    )
    material2 = ScientificMaterial(
        type=MaterialType.DOCUMENT,
        outgoing_number="M-2",
        outgoing_date=date(2026, 3, 20),
        name="Материал 2",
        branch_id="F1",
    )
    telegram = Telegram(
        type=TelegramType.THEMATIC,
        outgoing_number="T-1",
        outgoing_date=date(2026, 4, 2),
        name="Телеграмма 1",
        report_type=TelegramReportType.REPORTED,
        branch_id="F1",
    )
    session.add_all([material1, material2, telegram])
    session.flush()

    session.add(
        Evaluation(
            value=EvaluationValue.USEFUL,
            date=date(2026, 3, 10),
            evaluation_list_id=evaluation_list.id,
            materials=[material1],
        )
    )
    task = ScientificTask(
        id="T-1",
        name="Задача 1",
        type=ScientificTaskType.MAIN,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    session.add(task)
    session.flush()
    session.add(AddedTask(task_id="T-1", node_type="branch", node_id="F1"))
    session.commit()
    yield {"session": session, "department_id": department.id}
    session.close()


def test_service_counts_and_average(dashboard_data, db_manager):
    service = DashboardService(dashboard_data["session"], "head_office")
    data = service.load(DashboardFilter(year=2026))

    assert data.documents_total == 3
    assert data.materials_total == 2
    assert data.telegrams_total == 1
    assert data.evaluated_count == 1
    assert data.evaluation_average == 2.0
    assert data.tasks_total == 1
    assert data.tasks_assigned == 1
    assert [item[0] for item in data.attention] == [STRINGS.dashboard_without_evaluation]


def test_service_month_and_branch_filter(dashboard_data):
    service = DashboardService(dashboard_data["session"], "head_office")
    month = service.load(DashboardFilter(period_type=PERIOD_MONTH, year=2026, month=3))
    assert month.documents_total == 2
    assert month.materials_total == 2

    branch = service.load(DashboardFilter(year=2026, branch_id="F1"))
    assert branch.documents_total == 3
    assert branch.materials_total == 2


def test_service_without_import_tables_is_safe(dashboard_data):
    service = DashboardService(dashboard_data["session"], "head_office")
    data = service.load(DashboardFilter(year=2026))
    assert data.import_status is None
    assert data.import_matched == 0


def test_widget_renders_kpi_and_charts(dashboard_data, qt_app):
    widget = DashboardWidget(dashboard_data["session"], "head_office")
    assert widget.kpi_layout.count() == 3
    assert widget.financial_check.isChecked()
    assert widget.date_label.text()
    assert all(
        isinstance(widget.kpi_layout.itemAt(i).widget(), KpiCard)
        for i in range(widget.kpi_layout.count())
    )
    assert not widget.findChildren(QScrollArea)
    # По умолчанию включён финансовый год; для данных теста переключаемся
    # на календарный 2026 год.
    widget.financial_check.setChecked(False)
    assert not widget.financial_check.isChecked()
    assert widget.monthly_view.chart().series()
    assert widget.types_view.chart().series()
    evaluation_series = widget.evaluations_view.chart().series()
    assert evaluation_series
    assert isinstance(evaluation_series[0], QStackedBarSeries)
    assert len(evaluation_series[0].barSets()) == len(widget.data.evaluation_counts)
    first_code = widget.data.evaluation_counts[0][0]
    assert evaluation_series[0].barSets()[0].color().name() == _EVALUATION_COLORS[
        first_code
    ].lower()
    assert widget.evaluations_view.chart().title() == STRINGS.dashboard_chart_evaluations
    assert widget.ranking_view.chart().series()
    assert widget.ranking_view.chart().title() == STRINGS.dashboard_chart_ranking

    card = widget.kpi_layout.itemAt(0).widget()
    assert card.layout().contentsMargins().top() == 5
    assert card.layout().contentsMargins().bottom() == 5

    widget.types_combo.setCurrentIndex(1)
    assert widget.types_view.chart().series()

    widget.period_combo.setCurrentIndex(widget.period_combo.findData(PERIOD_MONTH))
    widget.index_combo.setCurrentIndex(2)
    assert widget.data.documents_total == 2
    widget.close()


def test_widget_scales_to_window_size(dashboard_data, qt_app):
    widget = DashboardWidget(dashboard_data["session"], "head_office")
    widget.resize(900, 620)
    widget._apply_scale()
    small_card = widget.kpi_layout.itemAt(0).widget()
    small_size = small_card.value_label.font().pointSize()
    widget.resize(1500, 950)
    widget._apply_scale()
    large_size = small_card.value_label.font().pointSize()
    assert large_size > small_size
    widget.close()


def test_widget_branch_role_hides_branch_filter(dashboard_data, qt_app):
    widget = DashboardWidget(dashboard_data["session"], "branch", "F1")
    assert widget.branch_combo.isHidden()
    assert widget.kpi_layout.count() == 4
    widget.financial_check.setChecked(False)
    assert widget.data.documents_total == 3
    widget.close()
