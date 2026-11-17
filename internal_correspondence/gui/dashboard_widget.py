"""Вкладка «Дашборд»: сводные показатели, диаграммы и последние документы."""

from __future__ import annotations

import calendar
from datetime import date
from typing import List, Optional

from PyQt5.QtChart import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QPieSeries,
    QValueAxis,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
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


class KpiCard(QFrame):
    """Карточка одного сводного показателя."""

    def __init__(self, kpi: KpiValue, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(3)

        self.title_label = QLabel(kpi.label)
        self.title_label.setWordWrap(True)
        title_font = self.title_label.font()
        title_font.setPointSize(max(8, title_font.pointSize() - 1))
        self.title_label.setFont(title_font)

        self.value_label = QLabel(kpi.value)
        value_font = QFont(self.value_label.font())
        value_font.setPointSize(max(16, value_font.pointSize() + 8))
        value_font.setBold(True)
        self.value_label.setFont(value_font)

        self.detail_label = QLabel(kpi.detail)
        self.detail_label.setWordWrap(True)
        detail_font = self.detail_label.font()
        detail_font.setPointSize(max(8, detail_font.pointSize() - 1))
        self.detail_label.setFont(detail_font)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)
        self.set_theme()

    def update_kpi(self, kpi: KpiValue) -> None:
        """Обновляет значения карточки без пересоздания виджета."""
        self.title_label.setText(kpi.label)
        self.value_label.setText(kpi.value)
        self.detail_label.setText(kpi.detail)

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

        self._build_ui()
        self._reload_filters()
        self.refresh()

    # ------------------------------------------------------------------
    # Построение интерфейса
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel(f"{STRINGS.dashboard_period}:"))
        self.period_combo = QComboBox()
        for key in (PERIOD_YEAR, PERIOD_HALF, PERIOD_QUARTER, PERIOD_MONTH):
            self.period_combo.addItem(PERIOD_LABELS[key], key)
        controls.addWidget(self.period_combo)

        controls.addWidget(QLabel(f"{STRINGS.dashboard_year}:"))
        self.year_combo = QComboBox()
        controls.addWidget(self.year_combo)

        self.index_combo = QComboBox()
        controls.addWidget(self.index_combo)

        self.financial_check = QPushButton(STRINGS.dashboard_financial)
        self.financial_check.setCheckable(True)
        self.financial_check.setFlat(True)
        controls.addWidget(self.financial_check)

        self.branch_label = QLabel(f"{STRINGS.dashboard_branch}:")
        controls.addWidget(self.branch_label)
        self.branch_combo = QComboBox()
        controls.addWidget(self.branch_combo)
        if self.role != Role.HEAD_OFFICE.value:
            self.branch_label.hide()
            self.branch_combo.hide()

        controls.addStretch(1)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #C0392B;")
        controls.addWidget(self.status_label)
        self.refresh_button = QPushButton(STRINGS.dashboard_refresh)
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_button)
        root.addLayout(controls)

        self.period_label = QLabel("")
        period_font = QFont(self.period_label.font())
        period_font.setBold(True)
        self.period_label.setFont(period_font)
        root.addWidget(self.period_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)

        self.kpi_layout = QHBoxLayout()
        self.kpi_layout.setSpacing(8)
        self.content_layout.addLayout(self.kpi_layout)

        charts = QGridLayout()
        charts.setSpacing(8)
        self.monthly_view = self._chart_view()
        self.types_view = self._chart_view()
        self.evaluations_view = self._chart_view()
        self.ranking_view = self._chart_view()

        self.types_header = QWidget()
        types_header_layout = QHBoxLayout(self.types_header)
        types_header_layout.setContentsMargins(0, 0, 0, 0)
        self.types_combo = QComboBox()
        self.types_combo.addItem(STRINGS.dashboard_type_materials, "material")
        self.types_combo.addItem(STRINGS.dashboard_type_telegrams, "telegram")
        self.types_combo.currentIndexChanged.connect(self._types_changed)
        types_header_layout.addStretch(1)
        types_header_layout.addWidget(self.types_combo)

        types_box = QWidget()
        types_box_layout = QVBoxLayout(types_box)
        types_box_layout.setContentsMargins(0, 0, 0, 0)
        types_box_layout.setSpacing(2)
        types_box_layout.addWidget(self.types_header)
        types_box_layout.addWidget(self.types_view)

        charts.addWidget(self.monthly_view, 0, 0)
        charts.addWidget(types_box, 0, 1)
        charts.addWidget(self.evaluations_view, 1, 0)
        charts.addWidget(self.ranking_view, 1, 1)
        charts.setColumnStretch(0, 1)
        charts.setColumnStretch(1, 1)
        self.content_layout.addLayout(charts)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        recent_box = QWidget()
        recent_layout = QVBoxLayout(recent_box)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(4)
        recent_title = QLabel(STRINGS.dashboard_recent)
        recent_font = QFont(recent_title.font())
        recent_font.setBold(True)
        recent_title.setFont(recent_font)
        self.recent_table = QTableWidget(0, 6)
        self.recent_table.setHorizontalHeaderLabels(
            [
                STRINGS.dashboard_col_kind,
                STRINGS.dashboard_col_number,
                STRINGS.dashboard_col_date,
                STRINGS.dashboard_col_name,
                STRINGS.dashboard_col_branch,
                STRINGS.dashboard_col_evaluation,
            ]
        )
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.recent_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.recent_table.setSelectionMode(QTableWidget.SingleSelection)
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        self.recent_table.setMinimumHeight(170)
        recent_layout.addWidget(recent_title)
        recent_layout.addWidget(self.recent_table)

        attention_box = QWidget()
        attention_layout = QVBoxLayout(attention_box)
        attention_layout.setContentsMargins(0, 0, 0, 0)
        attention_layout.setSpacing(4)
        attention_title = QLabel(STRINGS.dashboard_attention)
        attention_title.setFont(recent_font)
        self.attention_list = QListWidget()
        self.attention_list.setMinimumHeight(170)
        attention_layout.addWidget(attention_title)
        attention_layout.addWidget(self.attention_list)

        bottom.addWidget(recent_box, 2)
        bottom.addWidget(attention_box, 1)
        self.content_layout.addLayout(bottom)
        self.content_layout.addStretch(1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self.period_combo.currentIndexChanged.connect(self._period_type_changed)
        self.year_combo.currentIndexChanged.connect(self._filters_changed)
        self.index_combo.currentIndexChanged.connect(self._filters_changed)
        self.financial_check.toggled.connect(self._filters_changed)
        self.branch_combo.currentIndexChanged.connect(self._filters_changed)

    @staticmethod
    def _chart_view() -> QChartView:
        view = QChartView()
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(250)
        view.setMaximumHeight(320)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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
        self._render_recent()
        self._render_attention()

    def _render_kpi(self) -> None:
        if self.data is None:
            return
        cards: List[KpiCard] = []
        for index in range(self.kpi_layout.count()):
            widget = self.kpi_layout.itemAt(index).widget()
            if isinstance(widget, KpiCard):
                cards.append(widget)
        if len(cards) != len(self.data.kpi):
            while self.kpi_layout.count():
                item = self.kpi_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
            cards = []
            for _kpi in self.data.kpi:
                card = KpiCard(_kpi)
                self.kpi_layout.addWidget(card)
                cards.append(card)
        for card, kpi in zip(cards, self.data.kpi):
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
        chart.legend().setAlignment(Qt.AlignBottom)
        chart.setAnimationOptions(QChart.NoAnimation)
        chart.setBackgroundRoundness(0)
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

    def _style_axis(self, axis, color: QColor, font_size: int = 8) -> None:
        axis.setLabelsColor(color)
        axis.setLinePenColor(color)
        axis.setGridLineColor(QColor(color.red(), color.green(), color.blue(), 50))
        font = QFont()
        font.setPointSize(font_size)
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
        axis_x.setLabelsAngle(0)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        maximum = max(data.monthly_materials + data.monthly_telegrams + [1])
        axis_y.setRange(0, maximum * 1.15)
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(min(6, maximum + 2))
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
        self._style_axis(axis_x, QColor(colors["TEXT_MUTED"]), 7)
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
        legend_font.setPointSize(7)
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
        series = QBarSeries()
        bar_set = QBarSet(STRINGS.dashboard_chart_evaluations)
        labels: List[str] = []
        for index, (label, count) in enumerate(data.evaluation_counts):
            labels.append(label)
            bar_set.append(count)
        series.append(bar_set)
        chart.addSeries(series)
        chart.legend().setVisible(False)
        axis_x = QBarCategoryAxis()
        axis_x.append(labels)
        axis_x.setLabelsAngle(-20)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)
        axis_y = QValueAxis()
        axis_y.setRange(0, max([count for _, count in data.evaluation_counts] + [1]) * 1.15)
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(5)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
        self._style_axis(axis_x, QColor(colors["TEXT_MUTED"]))
        self._style_axis(axis_y, QColor(colors["TEXT_MUTED"]))
        self._set_chart(self.evaluations_view, chart)

    def _render_ranking(self, data: DashboardData) -> None:
        from internal_correspondence.gui.theme import current_theme

        colors = current_theme().qss_colors
        chart = self._new_chart(data.ranking_title)
        if not data.ranking:
            chart.setTitle(f"{data.ranking_title} — {STRINGS.dashboard_no_data}")
            self._set_chart(self.ranking_view, chart)
            return
        series = QBarSeries()
        bar_set = QBarSet("")
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
        axis_y.setRange(0, max([count for _, count in data.ranking] + [1]) * 1.15)
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(5)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)
        self._style_axis(axis_x, QColor(colors["TEXT_MUTED"]), 7)
        self._style_axis(axis_y, QColor(colors["TEXT_MUTED"]))
        self._set_chart(self.ranking_view, chart)

    def _render_recent(self) -> None:
        if self.data is None:
            return
        rows = self.data.recent
        self.recent_table.setRowCount(len(rows))
        for row, document in enumerate(rows):
            values = [
                document.kind,
                document.number,
                document.document_date.strftime("%d.%m.%Y")
                if document.document_date
                else "",
                document.name,
                document.branch,
                document.evaluation,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.recent_table.setItem(row, column, item)
        self.recent_table.resizeColumnsToContents()
        self.recent_table.setColumnWidth(3, max(180, self.recent_table.columnWidth(3)))

    def _render_attention(self) -> None:
        self.attention_list.clear()
        if self.data is None or not self.data.attention:
            self.attention_list.addItem(STRINGS.dashboard_no_data)
            return
        for label, count in self.data.attention:
            self.attention_list.addItem(f"{label} — {count}")

    def _types_changed(self) -> None:
        self._types_kind = self.types_combo.currentData() or "material"
        if self.data is not None:
            self._render_types(self.data)

    # ------------------------------------------------------------------
    # Тема
    # ------------------------------------------------------------------
    def apply_theme(self) -> None:
        """Перерисовывает карточки и диаграммы после смены темы."""
        for index in range(self.kpi_layout.count()):
            widget = self.kpi_layout.itemAt(index).widget()
            if isinstance(widget, KpiCard):
                widget.set_theme()
        self._render_charts()
