"""Вкладка «Дашборд»: сводные показатели и адаптивные диаграммы."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from PyQt5.QtChart import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QStackedBarSeries,
    QValueAxis,
)
from PyQt5.QtCore import QMargins, QPointF, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import Role
from internal_correspondence.reports.dashboard_service import (
    DashboardData,
    DashboardFilter,
    DashboardService,
    KpiValue,
)
from internal_correspondence.reports.statistics_service import (
    PERIOD_HALF,
    PERIOD_LABELS,
    PERIOD_MONTH,
    PERIOD_QUARTER,
    PERIOD_YEAR,
)
from internal_correspondence.utils.string_resources import STRINGS

_MONTH_NAMES = (
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
)

_CHART_COLORS = (
    "#3569D4",
    "#E8710A",
    "#2E8B57",
    "#C0392B",
    "#8E44AD",
    "#16A085",
    "#D4A017",
    "#5D6D7E",
)

_EVALUATION_COLORS = {
    "Б": "#C0392B",
    "И": "#E67E22",
    "П": "#A9C43A",
    "В": "#2E8B57",
}

_RANKING_CHILD_COLORS = (
    "#123B5C",
    "#1F6F8B",
    "#2E7D5B",
    "#6A4C93",
    "#9C6B1E",
)

_RANKING_CHILD_COLORS_DARK = (
    "#7FB2FF",
    "#4FD1C5",
    "#8BD17C",
    "#C4A7F5",
    "#F2B880",
)

_WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


class KpiCard(QFrame):
    """Карточка одного сводного показателя."""

    def __init__(self, kpi: KpiValue, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._scale = 1.0
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 5, 14, 5)
        self._layout.setSpacing(3)

        self.title_label = QLabel(kpi.label)
        self.title_label.setWordWrap(True)

        self.value_label = QLabel(kpi.value)

        self.detail_label = QLabel(kpi.detail)
        self.detail_label.setWordWrap(True)

        self.attention_label = QLabel("")
        self.attention_label.setWordWrap(True)
        self.attention_label.setVisible(False)

        self._layout.addWidget(self.title_label)
        self._layout.addWidget(self.value_label)
        self._layout.addWidget(self.detail_label)
        self._layout.addWidget(self.attention_label)
        self._apply_fonts(1.0)
        self.set_theme()

    def _apply_fonts(self, scale: float) -> None:
        """Подбирает размеры шрифтов под масштаб окна."""
        title_font = QFont(self.title_label.font())
        title_font.setPointSize(max(9, round(12 * scale)))
        self.title_label.setFont(title_font)

        value_font = QFont(self.value_label.font())
        value_font.setPointSize(max(14, round(24 * scale)))
        value_font.setBold(True)
        self.value_label.setFont(value_font)

        detail_font = QFont(self.detail_label.font())
        detail_font.setPointSize(max(8, round(11 * scale)))
        self.detail_label.setFont(detail_font)

        attention_font = QFont(self.attention_label.font())
        attention_font.setPointSize(max(8, round(11 * scale)))
        attention_font.setBold(True)
        self.attention_label.setFont(attention_font)

    def set_scale(self, scale: float) -> None:
        """Масштабирует отступы, шрифты и высоту плитки."""
        self._scale = scale
        self._layout.setContentsMargins(
            round(14 * scale), round(5 * scale),
            round(14 * scale), round(5 * scale),
        )
        self._layout.setSpacing(max(1, round(3 * scale)))
        self._apply_fonts(scale)
        self.setMinimumHeight(round(96 * scale))
        self.setMaximumHeight(round(150 * scale))

    def update_kpi(self, kpi: KpiValue) -> None:
        """Обновляет значения карточки без пересоздания виджета."""
        self.title_label.setText(kpi.label)
        self.value_label.setText(kpi.value)
        self.detail_label.setText(kpi.detail)
        self.attention_label.setText(
            f"⚠ {kpi.attention}" if kpi.attention else ""
        )
        self.attention_label.setVisible(bool(kpi.attention))

    def set_theme(self) -> None:
        """Подстраивает цвета карточки под текущую тему."""
        from internal_correspondence.gui.theme import current_theme

        theme = current_theme()
        colors = theme.qss_colors
        self.setStyleSheet(
            "QFrame#dashboardCard {"
            f" background: {colors['SURFACE']};"
            f" border: 1px solid {colors['BORDER']};"
            " border-radius: 8px;"
            "}"
            "QFrame#dashboardCard QLabel { background: transparent; }"
        )
        self.title_label.setStyleSheet(f"color: {colors['TEXT_MUTED']};")
        self.value_label.setStyleSheet(f"color: {colors['TEXT']};")
        self.detail_label.setStyleSheet(f"color: {colors['TEXT_MUTED']};")
        attention_color = "#F6C177" if theme.key == "dark" else "#C2410C"
        self.attention_label.setStyleSheet(
            f"color: {attention_color}; font-weight: 600;"
        )


class DashboardWidget(QWidget):
    """Сводная вкладка с KPI, диаграммами и списками документов."""

    def __init__(
        self,
        session,
        role: str,
        branch_id: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.role = role
        self.branch_id = branch_id
        self.service = DashboardService(session, role, branch_id)
        self.data: Optional[DashboardData] = None
        self._updating = False
        self._types_kind = "material"
        self._scale = 1.0
        self._scale_timer = QTimer(self)
        self._scale_timer.setSingleShot(True)
        self._scale_timer.timeout.connect(self._apply_scale)

        self._build_ui()
        self._reload_filters()
        self.refresh()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(4)

        controls = QHBoxLayout()
        controls.setSpacing(2)
        self.refresh_button = QPushButton(STRINGS.dashboard_refresh)
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)

        controls.addWidget(QLabel(f"{STRINGS.dashboard_period}:"))
        self.period_combo = QComboBox()
        for key in (PERIOD_YEAR, PERIOD_HALF, PERIOD_QUARTER, PERIOD_MONTH):
            self.period_combo.addItem(PERIOD_LABELS[key], key)
        controls.addWidget(self.period_combo)

        self.year_combo = QComboBox()
        controls.addWidget(self.year_combo)

        self.index_combo = QComboBox()
        controls.addWidget(self.index_combo)

        self.financial_check = QPushButton(STRINGS.dashboard_financial)
        self.financial_check.setCheckable(True)
        self.financial_check.setChecked(True)
        self.financial_check.setFlat(False)
        controls.addWidget(self.financial_check)

        self.branch_label = QLabel(f"{STRINGS.dashboard_branch}:")
        controls.addWidget(self.branch_label)
        self.branch_combo = QComboBox()
        controls.addWidget(self.branch_combo)
        if self.role != Role.HEAD_OFFICE.value:
            self.branch_label.hide()
            self.branch_combo.hide()

        self.types_combo = QComboBox()
        self.types_combo.addItem(STRINGS.dashboard_type_materials, "material")
        self.types_combo.addItem(STRINGS.dashboard_type_telegrams, "telegram")
        controls.addWidget(self.types_combo)

        controls.addStretch(1)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #C0392B;")
        controls.addWidget(self.status_label)

        today = date.today()
        self.date_label = QLabel(
            f"{today.strftime('%d.%m.%Y')}\n{_WEEKDAYS[today.weekday()]}"
        )
        self.date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.date_label.setWordWrap(True)
        self.date_label.setMinimumWidth(200)
        self.date_label.setContentsMargins(0, 0, 8, 0)
        date_font = QFont(self.date_label.font())
        base_size = date_font.pointSize() if date_font.pointSize() > 0 else 9
        date_font.setPointSize(base_size + 10)
        date_font.setBold(True)
        self.date_label.setFont(date_font)
        controls.addWidget(self.date_label)
        root.addLayout(controls)

        self.period_combo.currentIndexChanged.connect(self._period_type_changed)
        self.year_combo.currentIndexChanged.connect(self._filters_changed)
        self.index_combo.currentIndexChanged.connect(self._filters_changed)
        self.financial_check.toggled.connect(self._financial_toggled)
        self.branch_combo.currentIndexChanged.connect(self._filters_changed)
        self.types_combo.currentIndexChanged.connect(self._types_changed)
        self._style_financial_button()
        from internal_correspondence.gui.theme import current_theme

        self.date_label.setStyleSheet(
            f"color: {current_theme().qss_colors['TEXT_MUTED']};"
        )

        self.period_label = QLabel("")
        period_font = QFont(self.period_label.font())
        period_font.setBold(True)
        self.period_label.setFont(period_font)
        root.addWidget(self.period_label)

        self.kpi_layout = QHBoxLayout()
        self.kpi_layout.setSpacing(8)
        root.addLayout(self.kpi_layout)

        charts = QGridLayout()
        charts.setSpacing(8)
        self.monthly_view = self._chart_view()
        self.types_view = self._chart_view()
        self.evaluations_view = self._chart_view()
        self.ranking_view = self._chart_view()
        charts.addWidget(self.monthly_view, 0, 0)
        charts.addWidget(self.types_view, 0, 1)
        charts.addWidget(self.evaluations_view, 1, 0)
        charts.addWidget(self.ranking_view, 1, 1)
        charts.setColumnStretch(0, 1)
        charts.setColumnStretch(1, 1)
        charts.setRowStretch(0, 1)
        charts.setRowStretch(1, 1)
        root.addLayout(charts, 1)

    @staticmethod
    def _chart_view() -> QChartView:
        view = QChartView()
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(150)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return view

    # ------------------------------------------------------------------
    # Фильтры
    # ------------------------------------------------------------------
    def _reload_filters(self) -> None:
        self._updating = True
        try:
            current_year = self.year_combo.currentData() or date.today().year
            self.year_combo.clear()
            years = self.service.available_years()
            today = date.today().year
            if today not in years:
                years.append(today)
            for year in sorted(set(years), reverse=True):
                self.year_combo.addItem(str(year), year)
            index = self.year_combo.findData(current_year)
            if index >= 0:
                self.year_combo.setCurrentIndex(index)

            self.branch_combo.clear()
            self.branch_combo.addItem(STRINGS.dashboard_all_branches, None)
            for branch in self.service.available_branches():
                self.branch_combo.addItem(
                    f"{branch.short_name or branch.name} ({branch.id})", branch.id
                )
        finally:
            self._updating = False
        self._period_type_changed()

    def _financial_toggled(self, _checked: bool) -> None:
        """Обновляет подсветку кнопки финансового года и данные."""
        self._style_financial_button()
        self._filters_changed()

    def _style_financial_button(self) -> None:
        """Подсвечивает кнопку, когда выбран финансовый год."""
        from internal_correspondence.gui.theme import current_theme

        colors = current_theme().qss_colors
        accent = colors["ACCENT"]
        self.financial_check.setStyleSheet(
            "QPushButton {"
            " border: 1px solid transparent;"
            " border-radius: 4px;"
            " padding: 3px 10px;"
            "}"
            "QPushButton:checked {"
            f" background: {accent};"
            " color: #FFFFFF;"
            f" border-color: {accent};"
            "}"
        )

    def _period_type_changed(self) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            period_type = self.period_combo.currentData()
            self.index_combo.clear()
            if period_type == PERIOD_HALF:
                self.index_combo.addItem("I", 1)
                self.index_combo.addItem("II", 2)
            elif period_type == PERIOD_QUARTER:
                for quarter in range(1, 5):
                    self.index_combo.addItem(str(quarter), quarter)
            elif period_type == PERIOD_MONTH:
                for month in range(1, 13):
                    self.index_combo.addItem(_MONTH_NAMES[month - 1], month)
                self.index_combo.setCurrentIndex(date.today().month - 1)
            self.index_combo.setEnabled(bool(self.index_combo.count()))
        finally:
            self._updating = False
        self._filters_changed()

    def _filters_changed(self) -> None:
        if not self._updating:
            self.refresh()

    def _current_filter(self) -> DashboardFilter:
        period_type = self.period_combo.currentData() or PERIOD_YEAR
        return DashboardFilter(
            period_type=period_type,
            year=int(self.year_combo.currentData() or date.today().year),
            half=int(self.index_combo.currentData() or 1),
            quarter=int(self.index_combo.currentData() or 1),
            month=int(self.index_combo.currentData() or 1),
            financial=self.financial_check.isChecked(),
            branch_id=self.branch_combo.currentData(),
        )

    # ------------------------------------------------------------------
    # Загрузка и отрисовка
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Перечитывает данные и перерисовывает все блоки."""
        try:
            filter_ = self._current_filter()
            self.data = self.service.load(filter_)
            self.status_label.setText("")
        except Exception as error:  # pragma: no cover - защита интерфейса
            self.status_label.setText(str(error))
            return
        self.period_label.setText(self.data.period_label)
        self._render_kpi()
        self._render_charts()

    def _render_kpi(self) -> None:
        if self.data is None:
            return
        visible = [kpi for kpi in self.data.kpi if kpi.key != "import"]
        cards: List[KpiCard] = []
        for index in range(self.kpi_layout.count()):
            widget = self.kpi_layout.itemAt(index).widget()
            if isinstance(widget, KpiCard):
                cards.append(widget)
        if len(cards) != len(visible):
            while self.kpi_layout.count():
                item = self.kpi_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            cards = []
            for _kpi in visible:
                card = KpiCard(_kpi)
                card.set_scale(self._scale)
                self.kpi_layout.addWidget(card)
                cards.append(card)
        for card, kpi in zip(cards, visible):
            card.update_kpi(kpi)

    def _render_charts(self) -> None:
        if self.data is None:
            return
        self._render_monthly(self.data)
        self._render_types(self.data)
        self._render_evaluations(self.data)
        self._render_ranking(self.data)

    def _new_chart(self, title: str) -> QChart:
        from internal_correspondence.gui.theme import current_theme

        chart = QChart()
        chart.setTitle(title)
        title_font = QFont()
        title_font.setPointSize(max(8, round(12 * self._scale)))
        title_font.setBold(True)
        chart.setTitleFont(title_font)
        chart.legend().setAlignment(Qt.AlignBottom)
        chart.setAnimationOptions(QChart.NoAnimation)
        chart.setBackgroundRoundness(0)
        chart.setMargins(QMargins(8, 8, 8, 8))
        if chart.layout() is not None:
            chart.layout().setContentsMargins(0, 0, 0, 0)
        colors = current_theme().qss_colors
        chart.setBackgroundBrush(QBrush(QColor(colors["SURFACE"])))
        chart.setTitleBrush(QBrush(QColor(colors["TEXT"])))
        chart.legend().setLabelColor(QColor(colors["TEXT_MUTED"]))
        return chart

    def _set_chart(self, view: QChartView, chart: QChart) -> None:
        old = view.chart()
        view.setChart(chart)
        if old is not None:
            old.deleteLater()

    def _style_axis(self, axis, color: QColor, font_size: float = 10) -> None:
        axis.setLabelsColor(color)
        axis.setLinePenColor(color)
        axis.setGridLineColor(QColor(color.red(), color.green(), color.blue(), 50))
        font = QFont()
        font.setPointSize(max(6, round(font_size * self._scale)))
        axis.setLabelsFont(font)

    def _render_monthly(self, data: DashboardData) -> None:
        from internal_correspondence.gui.theme import current_theme

        colors = current_theme().qss_colors
        chart = self._new_chart(STRINGS.dashboard_chart_monthly)
        if not data.monthly_labels:
            chart.setTitle(f"{STRINGS.dashboard_chart_monthly} — {STRINGS.dashboard_no_data}")
            self._set_chart(self.monthly_view, chart)
            return
        series = QBarSeries()
        materials = QBarSet(STRINGS.dashboard_type_materials)
        telegrams = QBarSet(STRINGS.dashboard_type_telegrams)
        materials.append(data.monthly_materials)
        telegrams.append(data.monthly_telegrams)
        materials.setColor(QColor(colors["ACCENT"]))
        telegrams.setColor(QColor(_CHART_COLORS[1]))
        series.append(materials)
        series.append(telegrams)
        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(data.monthly_labels)
        axis_x.setLabelsAngle(-30)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        maximum = max(data.monthly_materials + data.monthly_telegrams + [1])
        axis_y.setRange(0, maximum * 1.15)
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(min(6, maximum + 2))
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
        self._style_axis(axis_x, QColor(colors["TEXT_MUTED"]), 9)
        self._style_axis(axis_y, QColor(colors["TEXT_MUTED"]))
        self._set_chart(self.monthly_view, chart)

    def _render_types(self, data: DashboardData) -> None:
        from internal_correspondence.gui.theme import current_theme

        colors = current_theme().qss_colors
        chart = self._new_chart(STRINGS.dashboard_chart_types)
        values = data.material_types if self._types_kind == "material" else data.telegram_types
        if not values:
            chart.setTitle(f"{STRINGS.dashboard_chart_types} — {STRINGS.dashboard_no_data}")
            self._set_chart(self.types_view, chart)
            return
        series = QPieSeries()
        for index, (label, count) in enumerate(values):
            slice_ = series.append(f"{label} — {count}", count)
            slice_.setColor(QColor(_CHART_COLORS[index % len(_CHART_COLORS)]))
            slice_.setLabelVisible(False)
        series.setHoleSize(0.32)
        series.setPieSize(0.68)
        chart.addSeries(series)
        chart.legend().setAlignment(Qt.AlignRight)
        legend_font = QFont()
        legend_font.setPointSize(max(6, round(7 * self._scale)))
        chart.legend().setFont(legend_font)
        chart.legend().setLabelColor(QColor(colors["TEXT_MUTED"]))
        self._set_chart(self.types_view, chart)

    def _render_evaluations(self, data: DashboardData) -> None:
        from internal_correspondence.gui.theme import current_theme

        colors = current_theme().qss_colors
        chart = self._new_chart(STRINGS.dashboard_chart_evaluations)
        if not data.evaluation_counts:
            chart.setTitle(
                f"{STRINGS.dashboard_chart_evaluations} — {STRINGS.dashboard_no_evaluations}"
            )
            self._set_chart(self.evaluations_view, chart)
            return

        total = sum(count for _, count in data.evaluation_counts)
        labels = [label for label, _count in data.evaluation_counts]
        series = QStackedBarSeries()
        for index, (label, count) in enumerate(data.evaluation_counts):
            bar_set = QBarSet(label)
            values = [0] * len(data.evaluation_counts)
            values[index] = count
            bar_set.append(values)
            bar_set.setColor(
                QColor(_EVALUATION_COLORS.get(label, _CHART_COLORS[index]))
            )
            series.append(bar_set)
        series.setBarWidth(0.72)
        chart.addSeries(series)
        chart.legend().setVisible(False)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_x.setLabelsAngle(0)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        maximum = max([count for _, count in data.evaluation_counts] + [1])
        axis_y.setRange(0, maximum * 1.35)
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(5)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
        self._style_axis(axis_x, QColor(colors["TEXT_MUTED"]))
        self._style_axis(axis_y, QColor(colors["TEXT_MUTED"]))

        text_color = QColor(colors["TEXT"])
        label_font = QFont()
        label_font.setPointSize(max(6, round(8 * self._scale)))
        label_font.setBold(True)
        items = []
        for index, (_label, count) in enumerate(data.evaluation_counts):
            percent = count * 100.0 / total if total else 0.0
            item = QGraphicsSimpleTextItem(f"{count} ({percent:.0f}%)", chart)
            item.setBrush(QBrush(text_color))
            item.setFont(label_font)
            item.setZValue(20)
            items.append((index, count, item))

        def place_labels() -> None:
            plot = chart.plotArea()
            for index, count, item in items:
                point = chart.mapToPosition(QPointF(index, count), series)
                rect = item.boundingRect()
                x = point.x() - rect.width() / 2.0
                x = max(plot.left() + 2.0, min(x, plot.right() - rect.width() - 2.0))
                y = max(plot.top() + 2.0, point.y() - rect.height() - 2.0)
                item.setPos(x, y)

        chart.plotAreaChanged.connect(lambda *_: place_labels())
        place_labels()
        self._set_chart(self.evaluations_view, chart)

    def _render_ranking(self, data: DashboardData) -> None:
        from internal_correspondence.gui.theme import current_theme

        colors = current_theme().qss_colors
        is_dark = current_theme().key == "dark"
        chart = self._new_chart(data.ranking_title)
        if not data.ranking:
            chart.setTitle(f"{data.ranking_title} — {STRINGS.dashboard_no_data}")
            self._set_chart(self.ranking_view, chart)
            return
        series = QBarSeries()
        series.setBarWidth(0.86)
        bar_set = QBarSet("")
        bar_set.setColor(QColor("#4F6B92" if is_dark else colors["ACCENT_SOFT"]))
        bar_set.setBorderColor(
            QColor("#8FB6E8" if is_dark else colors["BORDER_STRONG"])
        )
        labels: List[str] = []
        for label, count in data.ranking:
            labels.append("—" if label == STRINGS.dashboard_no_branch else label)
            bar_set.append(count)
        series.append(bar_set)
        chart.addSeries(series)
        chart.legend().setVisible(False)
        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_x.setLabelsAngle(0)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)
        axis_y = QValueAxis()
        axis_y.setRange(0, max([count for _, count in data.ranking] + [1]) * 1.35)
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(5)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
        self._style_axis(axis_x, QColor(colors["TEXT_MUTED"]), 9)
        self._style_axis(axis_y, QColor(colors["TEXT_MUTED"]))

        text_color = QColor(colors["TEXT"])
        coefficient_font = QFont()
        coefficient_font.setPointSize(max(7, round(9 * self._scale)))
        coefficient_font.setBold(True)
        child_font = QFont()
        child_font.setPointSize(max(9, round(10 * self._scale)))

        child_items: List[tuple] = []
        coefficient_items: List[tuple] = []
        ranking_children = data.ranking_children or [[] for _ in data.ranking]
        for index, ((_label, count), children) in enumerate(
            zip(data.ranking, ranking_children)
        ):
            coefficient = QGraphicsSimpleTextItem(str(count), chart)
            coefficient.setBrush(QBrush(text_color))
            coefficient.setFont(coefficient_font)
            coefficient.setZValue(30)
            coefficient_items.append((index, count, coefficient))

            for child_index, (child_label, child_count) in enumerate(children[:5]):
                rect_item = QGraphicsRectItem(chart)
                rect_item.setPen(QPen(Qt.NoPen))
                rect_item.setBrush(
                    QBrush(
                        QColor(
                            (_RANKING_CHILD_COLORS_DARK if is_dark else _RANKING_CHILD_COLORS)[
                                child_index % len(_RANKING_CHILD_COLORS)
                            ]
                        )
                    )
                )
                rect_item.setZValue(10)
                path = QPainterPath()
                path.addText(0, 0, child_font, child_label)
                label_item = QGraphicsPathItem(path, chart)
                label_item.setPen(QPen(QColor("#000000"), 1.2))
                label_item.setBrush(QBrush(QColor("#FFFFFF")))
                label_item.setRotation(-90)
                label_item.setZValue(20)
                child_items.append(
                    (index, count, child_index, child_count, len(children), rect_item, label_item)
                )

        def place_ranking() -> None:
            plot = chart.plotArea()
            if not data.ranking:
                return
            slot = plot.width() / len(data.ranking)
            bar_width = slot * 0.86
            for index, count, item in coefficient_items:
                point = chart.mapToPosition(QPointF(index, count), series)
                rect = item.boundingRect()
                item.setPos(
                    point.x() - rect.width() / 2.0,
                    max(plot.top() + 2.0, point.y() - rect.height() - 4.0),
                )

            for (
                index,
                parent_count,
                child_index,
                child_count,
                children_count,
                rect_item,
                label_item,
            ) in child_items:
                base = chart.mapToPosition(QPointF(index, 0), series)
                top = chart.mapToPosition(QPointF(index, parent_count), series)
                height = max(0.0, base.y() - top.y())
                inner_width = bar_width / max(1, children_count) * 0.78
                left = base.x() - bar_width / 2.0 + inner_width * 0.12
                x = left + child_index * (bar_width / max(1, children_count))
                child_height = height * min(1.0, child_count / max(1, parent_count))
                rect_item.setRect(x, base.y() - child_height, inner_width, child_height)
                if child_height < 16.0 or inner_width < 4.0:
                    label_item.setVisible(False)
                    continue
                label_item.setVisible(True)
                # После поворота на -90° подпись занимает высоту строки;
                # сдвигаем её так, чтобы центр глифов совпал с центром столбца.
                metrics = QFontMetricsF(child_font)
                label_item.setPos(
                    x
                    + inner_width / 2.0
                    + (metrics.ascent() - metrics.descent()) / 2.0,
                    base.y() - 2.0,
                )

        chart.plotAreaChanged.connect(lambda *_: place_ranking())
        place_ranking()
        self._set_chart(self.ranking_view, chart)

    def _types_changed(self) -> None:
        self._types_kind = self.types_combo.currentData() or "material"
        if self.data is not None:
            self._render_types(self.data)

    # ------------------------------------------------------------------
    # Адаптивность
    # ------------------------------------------------------------------
    def resizeEvent(self, event) -> None:
        """Планирует пересчёт масштаба после изменения размера окна."""
        super().resizeEvent(event)
        if hasattr(self, "_scale_timer"):
            self._scale_timer.start(120)

    def _apply_scale(self) -> None:
        """Подгоняет шрифты и плитки под текущий размер вкладки."""
        if not hasattr(self, "kpi_layout"):
            return
        width = max(self.width(), 640)
        height = max(self.height(), 480)
        scale = min(width / 1280.0, height / 800.0)
        scale = max(0.72, min(1.35, scale))
        if abs(scale - self._scale) < 0.03:
            return
        self._scale = scale
        for index in range(self.kpi_layout.count()):
            widget = self.kpi_layout.itemAt(index).widget()
            if isinstance(widget, KpiCard):
                widget.set_scale(scale)
        period_font = QFont(self.period_label.font())
        period_font.setPointSize(max(8, round(11 * scale)))
        period_font.setBold(True)
        self.period_label.setFont(period_font)
        if self.data is not None:
            self._render_charts()

    # ------------------------------------------------------------------
    # Тема
    # ------------------------------------------------------------------
    def apply_theme(self) -> None:
        """Перерисовывает карточки и диаграммы после смены темы."""
        from internal_correspondence.gui.theme import current_theme

        colors = current_theme().qss_colors
        if hasattr(self, "date_label"):
            self.date_label.setStyleSheet(f"color: {colors['TEXT_MUTED']};")
        if hasattr(self, "financial_check"):
            self._style_financial_button()
        for index in range(self.kpi_layout.count()):
            widget = self.kpi_layout.itemAt(index).widget()
            if isinstance(widget, KpiCard):
                widget.set_theme()
                widget.set_scale(self._scale)
        self._render_charts()
