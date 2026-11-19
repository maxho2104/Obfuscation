"""Диаграммы и выбор периода панели сведений об элементе ОШС."""

from datetime import date
from typing import Dict, List, Optional, Tuple

from PyQt5.QtChart import QChart, QChartView, QPieSeries, QPieSlice
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.domain_pack import enum_label, enum_weight
from internal_correspondence.core.enum_registry import pack_enum_display
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

# Цвета слоёв диаграммы (зафиксированы, чтобы мантия и легенда читались)
_MANTLE_COLORS = {
    "telegrams": QColor("#9B59B6"),  # телеграммы — фиолетовый
    "materials": QColor("#3498DB"),  # научные материалы — синий
}
# Цвета оценок по коду значения перечисления (Б, И, П, В)
_EVALUATION_COLORS = (
    QColor("#E74C3C"),  # 0 — бесполезно, красный
    QColor("#E67E22"),  # 1 — интересно, оранжевый
    QColor("#F1C40F"),  # 2 — полезно, жёлтый
    QColor("#2ECC71"),  # 3 — важно, зелёный
)
# Цвет сектора «без оценки»
_NO_EVALUATION_COLOR = QColor("#95A5A6")

# Цвет подписей на секторах
_LABEL_COLOR = Qt.black


def _evaluation_color(value: int) -> QColor:
    """Возвращает цвет оценки по коду значения перечисления."""
    known = (0, 1, 2, 3)
    if value in known:
        return _EVALUATION_COLORS[value]
    return QColor("#BDC3C7")


def _evaluation_sort_key(value: int) -> Tuple[int, int]:
    """Сортировка оценок: по убыванию веса (В, П, И, Б)."""
    code = pack_enum_display("evaluation_value", value)
    weight = enum_weight("evaluation_value", code)
    return (-weight if weight is not None else 0, value)


class _DonutView(QChartView):
    """Вид диаграммы с надписью в центре кольца."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(QChart())
        self.setRenderHint(QPainter.Antialiasing)
        self._center = QLabel(self)
        self._center.setAlignment(Qt.AlignCenter)
        self._center.setStyleSheet(
            "font-size: 16pt; font-weight: bold; color: black;"
            " background: transparent;"
        )
        self._center.hide()

    def set_center_text(self, text: str) -> None:
        self._center.setText(text)
        self._center.show()
        self._center.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        side = min(self.width(), self.height())
        inner = int(side * 0.34)
        self._center.setGeometry(
            (self.width() - inner) // 2,
            (self.height() - inner) // 2,
            inner,
            inner,
        )


class ElementDonutWidget(QWidget):
    """Диаграмма показателей элемента за период.

    В центре — общее количество материалов и телеграмм; «мантия» из двух
    пропорциональных секторов (телеграммы и материалы) с подписями;
    внешнее кольцо — сектора оценок внутри каждого класса документов
    (числа на секторах), названия оценок — цветная легенда внизу.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._view = _DonutView()
        self._view.setMinimumSize(230, 230)
        layout.addWidget(self._view)
        self._legend_row = QHBoxLayout()
        self._legend_row.addStretch()
        layout.addLayout(self._legend_row)

    def set_data(
        self,
        title: str,
        materials: int,
        telegrams: int,
        material_evaluations: Dict[int, int],
        telegram_evaluations: Dict[int, int],
    ) -> None:
        """Строит диаграмму: количества документов и оценки по классам."""
        chart = QChart()
        chart.setTheme(
            QChart.ChartThemeDark
            if current_theme().key == "dark"
            else QChart.ChartThemeLight
        )
        chart.setTitle(title)
        chart.legend().setVisible(False)
        total = materials + telegrams
        if total == 0:
            chart.setTitle(f"{title} — {STRINGS.chart_no_data}")
            self._view.setChart(chart)
            self._view.set_center_text("0")
            self._clear_legend()
            return

        # «Мантия»: телеграммы и материалы, пропорционально количествам.
        # Порядок секторов (телеграммы, затем материалы) совпадает с порядком
        # секторов оценок во внешнем кольце — дуги согласованы.
        mantle = QPieSeries()
        mantle.setPieSize(0.62)
        mantle.setHoleSize(0.34)
        if telegrams > 0:
            slice_ = mantle.append(f"{STRINGS.oshm_chart_telegrams} — {telegrams}", telegrams)
            slice_.setColor(_MANTLE_COLORS["telegrams"])
            slice_.setLabelVisible(True)
            slice_.setLabelPosition(QPieSlice.LabelInsideHorizontal)
            slice_.setLabelColor(_LABEL_COLOR)
        if materials > 0:
            slice_ = mantle.append(f"{STRINGS.oshm_chart_materials} — {materials}", materials)
            slice_.setColor(_MANTLE_COLORS["materials"])
            slice_.setLabelVisible(True)
            slice_.setLabelPosition(QPieSlice.LabelInsideHorizontal)
            slice_.setLabelColor(_LABEL_COLOR)
        chart.addSeries(mantle)

        # Внешнее кольцо: оценки телеграмм, затем оценки материалов.
        # Каждая группа секторов занимает ровно дугу своего сектора мантии:
        # неоценённые документы закрываются сектором «без оценки».
        outer = QPieSeries()
        outer.setPieSize(0.95)
        outer.setHoleSize(0.64)
        legend_values: List[int] = []
        legend_no_evaluation = False
        for evaluations, class_total in (
            (telegram_evaluations, telegrams),
            (material_evaluations, materials),
        ):
            for value in sorted(evaluations, key=_evaluation_sort_key):
                count = evaluations[value]
                if count <= 0:
                    continue
                slice_ = outer.append(str(count), count)
                slice_.setColor(_evaluation_color(value))
                slice_.setLabelVisible(True)
                slice_.setLabelPosition(QPieSlice.LabelInsideHorizontal)
                slice_.setLabelColor(_LABEL_COLOR)
                if value not in legend_values:
                    legend_values.append(value)
            unevaluated = class_total - sum(evaluations.values())
            if unevaluated > 0:
                slice_ = outer.append(str(unevaluated), unevaluated)
                slice_.setColor(_NO_EVALUATION_COLOR)
                slice_.setLabelVisible(True)
                slice_.setLabelPosition(QPieSlice.LabelInsideHorizontal)
                slice_.setLabelColor(_LABEL_COLOR)
                legend_no_evaluation = True
        if outer.count() > 0:
            chart.addSeries(outer)

        self._view.setChart(chart)
        self._view.set_center_text(str(total))
        self._build_legend(legend_values, legend_no_evaluation)

    def _clear_legend(self) -> None:
        while self._legend_row.count():
            item = self._legend_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_legend(self, values: List[int], no_evaluation: bool) -> None:
        """Строит цветную легенду оценок внизу диаграммы."""
        self._clear_legend()
        first = True
        for value in sorted(values, key=_evaluation_sort_key):
            if not first:
                spacer = QLabel("  ")
                self._legend_row.addWidget(spacer)
            first = False
            marker = QLabel()
            marker.setFixedSize(12, 12)
            color = _evaluation_color(value)
            marker.setStyleSheet(
                f"background-color: {color.name()}; border: 1px solid #888;"
            )
            self._legend_row.addWidget(marker)
            short = pack_enum_display("evaluation_value", value)
            self._legend_row.addWidget(QLabel(enum_label("evaluation_value", short)))
        if no_evaluation:
            if not first:
                self._legend_row.addWidget(QLabel("  "))
            marker = QLabel()
            marker.setFixedSize(12, 12)
            marker.setStyleSheet(
                f"background-color: {_NO_EVALUATION_COLOR.name()};"
                " border: 1px solid #888;"
            )
            self._legend_row.addWidget(marker)
            self._legend_row.addWidget(QLabel(STRINGS.oshm_chart_no_evaluation))
        self._legend_row.addStretch()


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
