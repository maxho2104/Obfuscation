"""Тесты вкладки статистики: подсветка элементов диаграммы по строке таблицы."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtChart import QPieSeries
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.statistics_widget import (
    _CHART_BARS,
    _CHART_PIE,
    StatisticsWidget,
)
from internal_correspondence.gui.theme import current_theme
from internal_correspondence.reports.statistics_service import (
    StatisticsResult,
    StatisticsRow,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_manager(tmp_path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'stats.db'}")
    db.create_tables()
    yield db
    db.close()


def _grouped_result() -> StatisticsResult:
    """«Задачи / сотрудники»: сотрудник Иванов входит в две группы-задачи."""
    rows = [
        StatisticsRow("Задача 1", [1], 1, key="task1", is_group=True),
        StatisticsRow("Иванов", [1], 1, key="emp1"),
        StatisticsRow("Задача 2", [2], 2, key="task2", is_group=True),
        StatisticsRow("Иванов", [1], 1, key="emp1"),
        StatisticsRow("Петров", [1], 1, key="emp2"),
    ]
    return StatisticsResult(
        title="Статистика",
        period_label="2026 год",
        columns=["Январь"],
        rows=rows,
        totals=[3],
        grand_total=3,
        month_columns=["Январь"],
        month_indices=[0],
    )


def _make_widget(db_manager, chart_type) -> StatisticsWidget:
    widget = StatisticsWidget(db_manager.get_session())
    index = widget.chart_type_combo.findData(chart_type)
    assert index >= 0
    widget.chart_type_combo.setCurrentIndex(index)
    widget._display(_grouped_result())
    return widget


def test_pie_select_member_highlights_all_his_slices(qt_app, db_manager):
    """Выбор сотрудника с несколькими задачами выделяет все его секторы."""
    widget = _make_widget(db_manager, _CHART_PIE)
    widget.table.selectRow(1)  # «Иванов» в группе «Задача 1»
    exploded = [
        slice_.label()
        for series in widget._chart.series()
        if isinstance(series, QPieSeries)
        for slice_ in series.slices()
        if slice_.isExploded()
    ]
    # Внешнее кольцо: оба сектора Иванова (по одному в каждой задаче)
    assert len(exploded) == 2
    assert all("Иванов" in label for label in exploded)
    widget.deleteLater()


def test_bars_select_member_highlights_all_his_bar_sets(qt_app, db_manager):
    """В столбчатой диаграмме подсвечиваются все наборы столбцов сотрудника."""
    widget = _make_widget(db_manager, _CHART_BARS)
    widget.table.selectRow(1)
    selection = current_theme().chart_selection
    highlighted = [
        bar_set
        for series in widget._chart.series()
        for bar_set in series.barSets()
        if bar_set.color() == selection
    ]
    assert len(highlighted) == 2
    widget.deleteLater()
