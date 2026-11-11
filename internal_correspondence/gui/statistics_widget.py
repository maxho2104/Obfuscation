"""Вкладка статистических подсчётов."""

from typing import Optional

from PyQt5.QtChart import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.theme import current_theme
from internal_correspondence.orm.labels import entity_label
from internal_correspondence.orm.models import ScientificMaterial, Telegram
from internal_correspondence.reports.statistics_service import (
    CRITERION_LABELS,
    PERIOD_HALF,
    PERIOD_LABELS,
    PERIOD_MONTH,
    PERIOD_QUARTER,
    PERIOD_YEAR,
    StatisticsQuery,
    StatisticsResult,
    StatisticsService,
)
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("statistics_widget")

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

# Цвета столбцов диаграммы для параметров расчёта
_CHART_COLORS = (
    QColor(31, 119, 180),
    QColor(255, 127, 14),
    QColor(44, 160, 44),
    QColor(214, 39, 40),
    QColor(148, 103, 189),
    QColor(140, 86, 75),
    QColor(227, 119, 194),
    QColor(127, 127, 127),
    QColor(188, 189, 34),
    QColor(23, 190, 207),
)


def _chart_color(index: int) -> QColor:
    """Возвращает цвет столбца для параметра с указанным индексом."""
    return _CHART_COLORS[index % len(_CHART_COLORS)]


class StatisticsWidget(QWidget):
    """Интерфейс выбора и отображения статистических подсчётов."""

    def __init__(
        self,
        session,
        branch_id: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.service = StatisticsService(session, branch_id)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(STRINGS.label_object))
        self.object_combo = QComboBox()
        self.object_combo.addItem(entity_label(ScientificMaterial, plural=True), ScientificMaterial)
        self.object_combo.addItem(entity_label(Telegram, plural=True), Telegram)
        controls.addWidget(self.object_combo)

        controls.addWidget(QLabel(STRINGS.label_criterion))
        self.criterion_combo = QComboBox()
        for key, label in CRITERION_LABELS.items():
            self.criterion_combo.addItem(label, key)
        controls.addWidget(self.criterion_combo)

        controls.addWidget(QLabel(STRINGS.label_period))
        self.period_combo = QComboBox()
        for key, label in PERIOD_LABELS.items():
            self.period_combo.addItem(label, key)
        controls.addWidget(self.period_combo)

        self.index_combo = QComboBox()
        controls.addWidget(self.index_combo)

        controls.addWidget(QLabel(STRINGS.label_year))
        self.year_combo = QComboBox()
        controls.addWidget(self.year_combo)

        for combo in (
            self.object_combo,
            self.criterion_combo,
            self.period_combo,
            self.index_combo,
            self.year_combo,
        ):
            combo.setProperty("role", "statistics")

        self.financial_check = QCheckBox(STRINGS.check_financial_year)
        controls.addWidget(self.financial_check)
        controls.addStretch()
        layout.addLayout(controls)

        actions = QHBoxLayout()
        actions.addStretch()
        self.calculate_btn = QPushButton(STRINGS.button_calculate)
        self.calculate_btn.clicked.connect(self.refresh)
        actions.addWidget(self.calculate_btn)
        layout.addLayout(actions)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.title_label)

        self.period_label = QLabel()
        layout.addWidget(self.period_label)

        self.content_layout = QHBoxLayout()

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.content_layout.addWidget(self.table, 1)

        self.split_slider = QSlider(Qt.Vertical)
        self.split_slider.setRange(10, 90)
        self.split_slider.setValue(50)
        self.split_slider.setFixedWidth(24)
        self.split_slider.setToolTip(STRINGS.tooltip_split_ratio)
        self.split_slider.valueChanged.connect(self._update_split)
        self.content_layout.addWidget(self.split_slider)

        self.chart_view = QChartView(QChart())
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setMinimumSize(320, 240)
        self.content_layout.addWidget(self.chart_view, 1)

        layout.addLayout(self.content_layout)
        self._update_split(self.split_slider.value())

        self.period_combo.currentIndexChanged.connect(self._update_index_combo)
        self.object_combo.currentIndexChanged.connect(self._update_year_combo)
        self.financial_check.toggled.connect(self._update_year_combo)
        self._update_index_combo()
        self._update_year_combo()

    def _update_split(self, value: int) -> None:
        """Изменяет соотношение ширины таблицы и графика."""
        self.content_layout.setStretch(0, value)
        self.content_layout.setStretch(2, 100 - value)

    def _update_year_combo(self) -> None:
        """Обновляет список лет на основе записей БД."""
        current = self.year_combo.currentData()
        years = self.service.available_period_years(
            self.object_combo.currentData(),
            self.financial_check.isChecked(),
        )

        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for year in years:
            self.year_combo.addItem(str(year), year)
        if current in years:
            self.year_combo.setCurrentText(str(current))
        else:
            self.year_combo.setCurrentIndex(self.year_combo.count() - 1)
        self.year_combo.blockSignals(False)

    def _update_index_combo(self) -> None:
        """Обновляет список подпериодов для выбранного типа периода."""
        period_type = self.period_combo.currentData()
        self.index_combo.clear()

        if period_type == PERIOD_YEAR:
            self.index_combo.setEnabled(False)
            return

        self.index_combo.setEnabled(True)
        if period_type == PERIOD_HALF:
            self.index_combo.addItem(STRINGS.half_year_1, 1)
            self.index_combo.addItem(STRINGS.half_year_2, 2)
        elif period_type == PERIOD_QUARTER:
            for index in range(1, 5):
                self.index_combo.addItem(
                    STRINGS.quarter_label.format(roman=_roman(index)), index
                )
        elif period_type == PERIOD_MONTH:
            for index, name in enumerate(_MONTH_NAMES, start=1):
                self.index_combo.addItem(name, index)

    def _index_value(self) -> int:
        """Возвращает выбранный номер подпериода."""
        value = self.index_combo.currentData()
        return int(value) if value is not None else 1

    def refresh(self) -> None:
        """Пересчитывает статистику по текущим параметрам."""
        self._update_year_combo()
        period_type = self.period_combo.currentData()
        index = self._index_value()

        query = StatisticsQuery(
            model_class=self.object_combo.currentData(),
            criterion=self.criterion_combo.currentData(),
            period_type=period_type,
            year=int(self.year_combo.currentData()),
            half=index if period_type == PERIOD_HALF else 1,
            quarter=index if period_type == PERIOD_QUARTER else 1,
            month=index if period_type == PERIOD_MONTH else 1,
            financial=self.financial_check.isChecked(),
        )

        try:
            result = self.service.calculate(query)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка статистического подсчёта")
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_calc_error.format(error=exc)
            )
            return

        self._display(result)

    def _display(self, result: StatisticsResult) -> None:
        """Отображает результат подсчёта в таблице."""
        self._last_result = result
        self.title_label.setText(result.title)
        self.period_label.setText(
            STRINGS.stats_period_prefix.format(label=result.period_label)
        )

        headers = [self.criterion_combo.currentText()] + result.columns + [STRINGS.header_total]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(result.rows) + 1)

        for row_index, row in enumerate(result.rows):
            self.table.setItem(row_index, 0, self._text_item(row.label))
            for column_index, value in enumerate(row.values, start=1):
                self.table.setItem(row_index, column_index, self._number_item(value))
            self.table.setItem(
                row_index,
                len(headers) - 1,
                self._number_item(row.total, bold=True),
            )

        totals_row = len(result.rows)
        self.table.setItem(totals_row, 0, self._text_item(STRINGS.row_grand_total, bold=True))
        for column_index, value in enumerate(result.totals, start=1):
            self.table.setItem(
                totals_row,
                column_index,
                self._number_item(value, bold=True),
            )
        self.table.setItem(
            totals_row,
            len(headers) - 1,
            self._number_item(result.grand_total, bold=True),
        )

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        self._update_chart(result)

    def _update_chart(self, result: StatisticsResult) -> None:
        """Строит столбчатую диаграмму по месяцам с цветами параметров."""
        chart = QChart()
        chart.setTheme(
            QChart.ChartThemeDark
            if current_theme().key == "dark"
            else QChart.ChartThemeLight
        )
        chart.setTitle(STRINGS.chart_by_months.format(title=result.title))

        month_indices = result.month_indices
        categories = result.month_columns
        if not result.rows or not month_indices:
            chart.setTitle(STRINGS.chart_no_data)
            self._chart = chart
            self.chart_view.setChart(chart)
            return

        series = QBarSeries()
        max_value = 0
        for row_index, row in enumerate(result.rows):
            bar_set = QBarSet(row.label)
            bar_set.setColor(_chart_color(row_index))
            for index in month_indices:
                value = row.values[index]
                bar_set.append(value)
                max_value = max(max_value, value)
            series.append(bar_set)

        chart.addSeries(series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        if len(categories) > 6:
            axis_x.setLabelsAngle(-30)
        chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        axis_y = QValueAxis()
        axis_y.setRange(0, max(max_value, 1))
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(min(max(max_value, 1), 10) + 1)
        axis_y.setTitleText(STRINGS.axis_count)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        chart.legend().setVisible(len(result.rows) > 1)
        chart.legend().setAlignment(Qt.AlignBottom)

        self._chart = chart
        self.chart_view.setChart(chart)

    def apply_theme(self) -> None:
        """Перестраивает график с учётом текущей темы оформления."""
        last_result = getattr(self, "_last_result", None)
        if last_result is not None:
            self._update_chart(last_result)

    @staticmethod
    def _text_item(text: str, bold: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        return item

    @staticmethod
    def _number_item(value: int, bold: bool = False) -> QTableWidgetItem:
        item = QTableWidgetItem(str(value))
        item.setTextAlignment(Qt.AlignCenter)
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        return item


def _roman(value: int) -> str:
    """Возвращает римское обозначение числа от 1 до 4."""
    return ("I", "II", "III", "IV")[min(max(value, 1), 4) - 1]
