"""Вкладка статистических подсчётов."""

import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtChart import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QCategoryAxis,
    QChart,
    QChartView,
    QLineSeries,
    QPieSeries,
    QValueAxis,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.gui.theme import current_theme
from internal_correspondence.orm.labels import entity_label
from internal_correspondence.orm.models import ScientificMaterial, Telegram
from internal_correspondence.reports.statistics_export import export_statistics
from internal_correspondence.reports.statistics_service import (
    CRITERION_BRANCH,
    CRITERION_LABELS,
    PERIOD_HALF,
    PERIOD_LABELS,
    PERIOD_MONTH,
    PERIOD_QUARTER,
    PERIOD_YEAR,
    SUBCRITERIA,
    StatisticsQuery,
    StatisticsResult,
    StatisticsRow,
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

# Подсветка лучшего и худшего значений критерия (полупрозрачные)
_BEST_COLOR = QBrush(QColor(102, 187, 106, 90))
_WORST_COLOR = QBrush(QColor(229, 115, 115, 90))

# Типы диаграмм
_CHART_BARS = "bars"
_CHART_LINES = "lines"
_CHART_PIE = "pie"

# Соответствие типа узла ОШС критерию статистики
NODE_TO_CRITERION = {
    "employee": "employee",
    "department": "department",
    "workgroup": "workgroup",
    "branch": "branch",
}


def _chart_color(index: int) -> QColor:
    """Возвращает цвет столбца для параметра с указанным индексом."""
    return _CHART_COLORS[index % len(_CHART_COLORS)]


def _member_color(base: QColor, member_index: int) -> QColor:
    """Возвращает оттенок цвета группы для её элемента на диаграмме.

    Оттенки чередуются светлее/темнее базового цвета с нарастающим шагом.
    """
    step = member_index // 2 + 1
    factor = 100 + 20 * step
    if member_index % 2 == 0:
        return base.lighter(factor)
    return base.darker(factor)


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
        layout.setSpacing(4)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(STRINGS.label_object))
        self.object_combo = QComboBox()
        self.object_combo.addItem(entity_label(ScientificMaterial, plural=True), ScientificMaterial)
        self.object_combo.addItem(entity_label(Telegram, plural=True), Telegram)
        controls.addWidget(self.object_combo)

        controls.addWidget(QLabel(STRINGS.label_criterion))
        self.criterion_combo = QComboBox()
        for key, label in CRITERION_LABELS.items():
            # Сравнение филиалов доступно только головному офису
            if key == CRITERION_BRANCH and self.service.branch_id is not None:
                continue
            self.criterion_combo.addItem(label, key)
        controls.addWidget(self.criterion_combo)

        self.subcategory_label = QLabel(STRINGS.label_subcategory)
        controls.addWidget(self.subcategory_label)
        self.subcategory_combo = QComboBox()
        controls.addWidget(self.subcategory_combo)

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

        self.financial_check = QCheckBox(STRINGS.check_financial_year)
        controls.addWidget(self.financial_check)
        controls.addStretch()
        layout.addLayout(controls)

        actions = QHBoxLayout()
        self.export_btn = QPushButton(STRINGS.button_export_excel)
        self.export_btn.clicked.connect(self._export_excel)
        actions.addWidget(self.export_btn)
        actions.addStretch()
        self.calculate_btn = QPushButton(STRINGS.button_calculate)
        self.calculate_btn.clicked.connect(self.refresh)
        actions.addWidget(self.calculate_btn)
        layout.addLayout(actions)

        # Заголовок, период и сводка — одной компактной строкой
        header_row = QHBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(self.title_label)
        self.period_label = QLabel()
        header_row.addWidget(self.period_label)
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(self.summary_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Таблица и график с привычным разделителем (splitter)
        self.content_splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.content_splitter.addWidget(self.table)

        # Правая часть: выбор типа графика над самим графиком
        chart_container = QWidget()
        chart_layout = QVBoxLayout(chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_controls = QHBoxLayout()
        chart_controls.addWidget(QLabel(STRINGS.label_chart_type))
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.addItem(STRINGS.chart_type_bars, _CHART_BARS)
        self.chart_type_combo.addItem(STRINGS.chart_type_lines, _CHART_LINES)
        self.chart_type_combo.addItem(STRINGS.chart_type_pie, _CHART_PIE)
        self.chart_type_combo.currentIndexChanged.connect(self._on_chart_type_changed)
        chart_controls.addWidget(self.chart_type_combo)
        chart_controls.addStretch()
        chart_layout.addLayout(chart_controls)

        self.chart_view = QChartView(QChart())
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setMinimumSize(320, 240)
        chart_layout.addWidget(self.chart_view)
        self.content_splitter.addWidget(chart_container)
        self.content_splitter.setSizes([500, 500])

        layout.addWidget(self.content_splitter)

        self.period_combo.currentIndexChanged.connect(self._update_index_combo)
        self.object_combo.currentIndexChanged.connect(self._update_year_combo)
        self.criterion_combo.currentIndexChanged.connect(self._update_subcategory_combo)
        self.financial_check.toggled.connect(self._update_year_combo)
        self._update_index_combo()
        self._update_subcategory_combo()
        self._update_year_combo()

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

    def _update_subcategory_combo(self) -> None:
        """Обновляет список подкатегорий для выбранного критерия."""
        criterion = self.criterion_combo.currentData()
        options = SUBCRITERIA.get(criterion, ())
        self.subcategory_combo.blockSignals(True)
        self.subcategory_combo.clear()
        if options:
            self.subcategory_combo.addItem(STRINGS.subcategory_none, None)
            for option in options:
                self.subcategory_combo.addItem(CRITERION_LABELS[option], option)
        self.subcategory_combo.blockSignals(False)
        self.subcategory_label.setVisible(bool(options))
        self.subcategory_combo.setVisible(bool(options))

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
            subcriterion=self.subcategory_combo.currentData(),
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

    def _first_column_header(self) -> str:
        """Заголовок первой колонки таблицы: критерий и подкатегория."""
        header = self.criterion_combo.currentText()
        if self.subcategory_combo.currentData():
            header = f"{header} / {self.subcategory_combo.currentText()}"
        return header

    def _export_excel(self) -> None:
        """Сохраняет последний результат подсчёта в файл Excel с графиком."""
        result = getattr(self, "_last_result", None)
        if result is None:
            return
        path_str, _selected_filter = QFileDialog.getSaveFileName(
            self,
            STRINGS.dialog_save_excel,
            "statistics.xlsx",
            STRINGS.file_filter_excel,
        )
        if not path_str:
            return
        path = Path(path_str)
        image_dir = Path(tempfile.mkdtemp(prefix="statistics_chart_"))
        image_path = image_dir / "chart.png"
        try:
            self.chart_view.grab().save(str(image_path), "PNG")
            export_statistics(
                result,
                self._first_column_header(),
                path,
                chart_image_path=image_path,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка выгрузки статистики в Excel")
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_export_error.format(error=exc)
            )
            return
        QMessageBox.information(
            self, STRINGS.title_export, STRINGS.msg_export_done.format(output=path)
        )

    def show_element(self, node: Tuple[str, str]) -> None:
        """Показывает статистику по элементу ОШС (узел дерева).

        Устанавливает подходящий критерий и выделяет строку элемента.
        """
        node_type, node_id = node
        criterion = NODE_TO_CRITERION.get(node_type)
        if criterion is None:
            return
        combo_index = self.criterion_combo.findData(criterion)
        if combo_index < 0:
            return
        self.criterion_combo.setCurrentIndex(combo_index)
        self.refresh()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            key = item.data(Qt.UserRole)
            if key is not None and str(key) == str(node_id):
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                break

    def _display(self, result: StatisticsResult) -> None:
        """Отображает результат подсчёта в таблице."""
        self._last_result = result
        self.title_label.setText(result.title)
        self.period_label.setText(
            STRINGS.stats_period_prefix.format(label=result.period_label)
        )
        self.summary_label.setText(result.summary or "")
        self.summary_label.setVisible(bool(result.summary))

        headers = [self._first_column_header()] + result.columns + [STRINGS.header_total]
        self.table.clear()
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(result.rows) + 1)

        for row_index, row in enumerate(result.rows):
            label = row.label if row.is_group else f"    {row.label}"
            label_item = self._text_item(label, bold=row.is_group)
            label_item.setData(Qt.UserRole, row.key)
            self.table.setItem(row_index, 0, label_item)
            for column_index, value in enumerate(row.values, start=1):
                self.table.setItem(
                    row_index, column_index, self._number_item(value, bold=row.is_group)
                )
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

        self._highlight_extremes(result)
        self._update_chart(result)

    def _highlight_extremes(self, result: StatisticsResult) -> None:
        """Подсвечивает лучшее и худшее значения критерия.

        При выбранной подкатегории сравниваются итоги групп, иначе — строки.
        """
        compared = (
            [row for row in result.rows if row.is_group]
            if any(row.is_group for row in result.rows)
            else list(result.rows)
        )
        if len(compared) < 2:
            return
        totals = [row.total for row in compared]
        best, worst = max(totals), min(totals)
        if best == worst:
            return
        compared_ids = {id(row) for row in compared}
        for row_index, row in enumerate(result.rows):
            if id(row) not in compared_ids or row.total not in (best, worst):
                continue
            color = _BEST_COLOR if row.total == best else _WORST_COLOR
            for column in range(self.table.columnCount()):
                item = self.table.item(row_index, column)
                if item is not None:
                    item.setBackground(color)

    # ------------------------------------------------------------------
    # Диаграмма
    # ------------------------------------------------------------------

    @staticmethod
    def _chart_series(result: StatisticsResult) -> List[Tuple[str, StatisticsRow, QColor]]:
        """Серии диаграммы: (подпись, строка, цвет).

        При выбранной подкатегории на график выводятся элементы групп
        оттенками цвета своей группы; иначе — строки критерия.
        """
        if not any(row.is_group for row in result.rows):
            return [
                (row.label, row, _chart_color(index))
                for index, row in enumerate(result.rows)
            ]
        series: List[Tuple[str, StatisticsRow, QColor]] = []
        group_index = -1
        member_index = 0
        for row in result.rows:
            if row.is_group:
                group_index += 1
                member_index = 0
            else:
                color = _member_color(_chart_color(group_index), member_index)
                series.append((row.label, row, color))
                member_index += 1
        return series

    def _new_chart(self, title: str) -> QChart:
        chart = QChart()
        chart.setTheme(
            QChart.ChartThemeDark
            if current_theme().key == "dark"
            else QChart.ChartThemeLight
        )
        chart.setTitle(title)
        return chart

    def _update_chart(self, result: StatisticsResult) -> None:
        """Строит диаграмму выбранного типа по результату подсчёта."""
        chart_type = self.chart_type_combo.currentData()
        if chart_type == _CHART_PIE:
            chart = self._build_pie(result)
        elif chart_type == _CHART_LINES:
            chart = self._build_lines(result)
        else:
            chart = self._build_bars(result)
        self._chart = chart
        self.chart_view.setChart(chart)

    def _on_chart_type_changed(self) -> None:
        """Перестраивает диаграмму при смене её типа без пересчёта данных."""
        last_result = getattr(self, "_last_result", None)
        if last_result is not None:
            self._update_chart(last_result)

    def _build_bars(self, result: StatisticsResult) -> QChart:
        """Столбчатая диаграмма по месяцам с цветами параметров."""
        chart = self._new_chart(STRINGS.chart_by_months.format(title=result.title))

        month_indices = result.month_indices
        categories = result.month_columns
        series_data = self._chart_series(result)
        if not series_data or not month_indices:
            chart.setTitle(STRINGS.chart_no_data)
            return chart

        series = QBarSeries()
        series.setLabelsVisible(True)
        series.setLabelsFormat("@value")
        max_value = 0
        for label, row, color in series_data:
            bar_set = QBarSet(label)
            bar_set.setColor(color)
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

        chart.addAxis(self._count_axis(max_value), Qt.AlignLeft)
        series.attachAxis(chart.axes(Qt.Vertical)[0])

        chart.legend().setVisible(len(series_data) > 1)
        chart.legend().setAlignment(Qt.AlignBottom)
        return chart

    def _build_lines(self, result: StatisticsResult) -> QChart:
        """Линейная диаграмма динамики по месяцам."""
        chart = self._new_chart(STRINGS.chart_by_months.format(title=result.title))

        month_indices = result.month_indices
        categories = result.month_columns
        series_data = self._chart_series(result)
        if not series_data or not month_indices:
            chart.setTitle(STRINGS.chart_no_data)
            return chart

        max_value = 0
        series_list = []
        for label, row, color in series_data:
            series = QLineSeries()
            series.setName(label)
            series.setColor(color)
            for position, index in enumerate(month_indices):
                value = row.values[index]
                series.append(position, value)
                max_value = max(max_value, value)
            chart.addSeries(series)
            series_list.append(series)

        axis_x = QCategoryAxis()
        axis_x.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)
        for position, category in enumerate(categories):
            axis_x.append(category, position)
        axis_x.setRange(-0.5, len(categories) - 0.5)
        if len(categories) > 6:
            axis_x.setLabelsAngle(-30)
        chart.addAxis(axis_x, Qt.AlignBottom)

        axis_y = self._count_axis(max_value)
        chart.addAxis(axis_y, Qt.AlignLeft)
        for series in series_list:
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)

        chart.legend().setVisible(len(series_data) > 1)
        chart.legend().setAlignment(Qt.AlignBottom)
        return chart

    def _build_pie(self, result: StatisticsResult) -> QChart:
        """Круговая диаграмма долей по итогам периода."""
        chart = self._new_chart(STRINGS.chart_by_totals.format(title=result.title))

        series_data = [entry for entry in self._chart_series(result) if entry[1].total > 0]
        if not series_data:
            chart.setTitle(STRINGS.chart_no_data)
            return chart

        series = QPieSeries()
        for label, row, color in series_data:
            slice_ = series.append(label, row.total)
            slice_.setColor(color)
            slice_.setLabelVisible(True)
        chart.addSeries(series)
        chart.legend().setAlignment(Qt.AlignBottom)
        return chart

    @staticmethod
    def _count_axis(max_value: int) -> QValueAxis:
        """Ось количества документов."""
        axis = QValueAxis()
        axis.setRange(0, max(max_value, 1))
        axis.setLabelFormat("%d")
        axis.setTickCount(min(max(max_value, 1), 10) + 1)
        axis.setTitleText(STRINGS.axis_count)
        return axis

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
