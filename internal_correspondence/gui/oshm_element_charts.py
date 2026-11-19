"""Диаграммы и выбор периода панели сведений об элементе ОШС."""

from datetime import date
from typing import Dict, Optional

from PyQt5.QtChart import QChart, QChartView, QPieSeries
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from internal_correspondence.core.domain_pack import enum_label
from internal_correspondence.core.enum_registry import pack_enum_display
from internal_correspondence.gui.statistics_widget import _chart_color
from internal_correspondence.gui.theme import current_theme
from internal_correspondence.reports.statistics_service import (
    _MONTH_NAMES,
    PERIOD_HALF,
    PERIOD_LABELS,
    PERIOD_MONTH,
    PERIOD_QUARTER,
    PERIOD_YEAR,
    Period,
    build_month_period,
    build_reporting_period,
)
from internal_correspondence.utils.string_resources import STRINGS

# Смещение базового цвета палитры для каждого кольца, чтобы кольца различались
_RING_COLOR_OFFSET = (0, 2, 4)


class ElementDonutWidget(QChartView):
    """Круговая диаграмма из трёх концентрических колец.

    Внутреннее кольцо — материалы по типам, среднее — телеграммы по типам,
    внешнее — оценки по значениям. В центре — общее количество материалов.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(QChart())
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumSize(230, 230)
        self._center = QLabel(self)
        self._center.setAlignment(Qt.AlignCenter)
        self._center.setStyleSheet(
            "font-size: 16pt; font-weight: bold; background: transparent;"
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        side = min(self.width(), self.height())
        inner = int(side * 0.45)
        self._center.setGeometry(
            (self.width() - inner) // 2,
            (self.height() - inner) // 2,
            inner,
            inner,
        )

    def set_data(
        self,
        title: str,
        materials: Dict[int, int],
        telegrams: Dict[int, int],
        evaluations: Dict[int, int],
    ) -> None:
        """Строит диаграмму: словари «код перечисления -> количество»."""
        chart = QChart()
        chart.setTheme(
            QChart.ChartThemeDark
            if current_theme().key == "dark"
            else QChart.ChartThemeLight
        )
        chart.setTitle(title)
        total_materials = sum(materials.values())
        total_all = total_materials + sum(telegrams.values()) + sum(evaluations.values())
        if total_all == 0:
            chart.setTitle(f"{title} — {STRINGS.chart_no_data}")
            self.setChart(chart)
            self._center.setText("0")
            self._center.show()
            return

        specs = (
            (materials, 0.45, 0.0, "material_type"),
            (telegrams, 0.70, 0.47, "telegram_type"),
            (evaluations, 0.95, 0.72, "evaluation_value"),
        )
        for ring_index, (data, pie_size, hole_size, enum_name) in enumerate(specs):
            series = QPieSeries()
            series.setPieSize(pie_size)
            series.setHoleSize(hole_size)
            for item_index, (code, count) in enumerate(sorted(data.items())):
                if count <= 0:
                    continue
                short = pack_enum_display(enum_name, code)
                label = f"{enum_label(enum_name, short)} ({count})"
                slice_ = series.append(label, count)
                color_index = _RING_COLOR_OFFSET[ring_index] + item_index
                slice_.setColor(_chart_color(color_index))
            if series.count() > 0:
                chart.addSeries(series)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignBottom)
        self.setChart(chart)
        self._center.setText(str(total_materials))
        self._center.show()
        self._center.raise_()


class PeriodSelectorWidget(QWidget):
    """Выбор периода как во вкладке «Статистика» (год/полугодие/квартал/месяц).

    По умолчанию — текущий месяц.
    """

    period_changed = pyqtSignal(object)  # Period

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(STRINGS.label_period))
        self.period_combo = QComboBox()
        for key, label in PERIOD_LABELS.items():
            self.period_combo.addItem(label, key)
        layout.addWidget(self.period_combo)
        self.index_combo = QComboBox()
        layout.addWidget(self.index_combo)
        layout.addWidget(QLabel(STRINGS.label_year))
        self.year_combo = QComboBox()
        today = date.today()
        for year in range(today.year - 6, today.year + 2):
            self.year_combo.addItem(str(year), year)
        self.year_combo.setCurrentIndex(6)  # текущий год
        layout.addWidget(self.year_combo)
        layout.addStretch()

        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        self.index_combo.currentIndexChanged.connect(self._emit_period)
        self.year_combo.currentIndexChanged.connect(self._on_period_changed)
        self.period_combo.setCurrentIndex(3)  # месяц
        self._on_period_changed()

    def _on_period_changed(self) -> None:
        """Обновляет список подпериодов для выбранного типа периода."""
        period_type = self.period_combo.currentData()
        self.index_combo.clear()
        if period_type == PERIOD_HALF:
            self.index_combo.addItem(STRINGS.half_year_1, 1)
            self.index_combo.addItem(STRINGS.half_year_2, 2)
        elif period_type == PERIOD_QUARTER:
            for number in range(1, 5):
                self.index_combo.addItem(
                    STRINGS.quarter_label.format(roman=_ROMAN_QUARTER[number - 1]),
                    number,
                )
        elif period_type == PERIOD_MONTH:
            for number, name in enumerate(_MONTH_NAMES, start=1):
                self.index_combo.addItem(name, number)
        self.index_combo.setEnabled(period_type != PERIOD_YEAR)
        # Дефолт — текущий месяц (для месяца без смены типа)
        if period_type == PERIOD_MONTH and self.index_combo.count() > 0:
            self.index_combo.setCurrentIndex(date.today().month - 1)
        self._emit_period()

    def _emit_period(self) -> None:
        period = self.current_period()
        if period is not None:
            self.period_changed.emit(period)

    def current_period(self) -> Optional[Period]:
        """Возвращает выбранный период."""
        period_type = self.period_combo.currentData()
        year = self.year_combo.currentData()
        if year is None:
            return None
        reporting = build_reporting_period(year)
        if period_type == PERIOD_YEAR:
            return Period(reporting.label, reporting.start, reporting.end)
        index = self.index_combo.currentData()
        if index is None:
            return None
        if period_type == PERIOD_HALF:
            return reporting.halves[min(max(index, 1), 2) - 1]
        if period_type == PERIOD_QUARTER:
            return reporting.quarters[min(max(index, 1), 4) - 1]
        if period_type == PERIOD_MONTH:
            return build_month_period(year, index)
        return None


_ROMAN_QUARTER = ("I", "II", "III", "IV")
