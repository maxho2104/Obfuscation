"""Диаграммы и выбор периода панели сведений об элементе ОШС."""

import html
from datetime import date
from typing import Dict, List, Optional, Tuple

from PyQt5.QtChart import QChart, QChartView, QPieSeries, QPieSlice
from PyQt5.QtCore import QMargins, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
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


def _label_color() -> Qt.GlobalColor:
    """Цвет подписей секторов и числа в центре под текущую тему."""
    return Qt.white if current_theme().key == "dark" else Qt.black


def _sector_font() -> QFont:
    """Шрифт подписей секторов (крупнее стандартного, чтобы читались)."""
    font = QFont()
    font.setPointSize(9)
    font.setBold(True)
    return font


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


def _evaluation_short(value: int) -> str:
    """Сокращённое наименование оценки (код перечисления: Б, И, П, В)."""
    return pack_enum_display("evaluation_value", value)


def _evaluation_full(value: int) -> str:
    """Полное наименование оценки (для подсказки легенды)."""
    return enum_label("evaluation_value", _evaluation_short(value))


class _DonutView(QChartView):
    """Вид диаграммы с надписью в центре кольца.

    Область построения всегда квадратная: вид занимает всю доступную
    площадь, а поля диаграммы подбираются так, чтобы круг вписался в
    квадрат со стороной ``min(width, height)`` и был отцентрован.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(QChart())
        self.setRenderHint(QPainter.Antialiasing)
        self._center = QLabel(self)
        self._center.setAlignment(Qt.AlignCenter)
        self._style_center()
        self._center.hide()

    def _style_center(self) -> None:
        """Оформляет надпись в центре под текущую тему."""
        color = "white" if current_theme().key == "dark" else "black"
        self._center.setStyleSheet(
            f"font-size: 16pt; font-weight: bold; color: {color};"
            " background: transparent;"
        )

    def set_center_text(self, text: str) -> None:
        self._center.setText(text)
        # Тема могла смениться после создания вида — цвет подписи обновляем
        self._style_center()
        self._center.show()
        self._center.raise_()
        self.apply_square_area()

    def square_side(self) -> int:
        """Сторона квадратной области построения."""
        return max(0, min(self.width(), self.height()))

    def apply_square_area(self) -> None:
        """Вписывает круг диаграммы в квадрат и центрирует его.

        Поля диаграммы выравнивают область построения по меньшей стороне
        вида, поэтому круг остаётся кругом при любой форме виджета.
        Размеры самого вида не меняются — раскладка не пересчитывается
        заново, поэтому рекурсии при изменении размера не возникает.
        """
        width, height = self.width(), self.height()
        if width <= 0 or height <= 0:
            return
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        chart = self.chart()
        if chart is not None:
            chart.setMargins(
                QMargins(left, top, width - side - left, height - side - top)
            )
        inner = int(side * 0.30)
        self._center.setGeometry(
            left + (side - inner) // 2,
            top + (side - inner) // 2,
            inner,
            inner,
        )
        # Надпись в центре подстраивается под размер кольца
        font = QFont(self._center.font())
        font.setPointSize(max(8, min(16, int(side * 0.055))))
        font.setBold(True)
        self._center.setFont(font)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.apply_square_area()


class ElementDonutWidget(QWidget):
    """Диаграмма показателей элемента за период.

    В центре — общее количество материалов и телеграмм; «мантия» из двух
    пропорциональных секторов (телеграммы и материалы); внешнее кольцо —
    сектора оценок внутри каждого класса документов. На секторах — только
    числа; что означает каждый цвет, расшифровано в описании под диаграммой
    (сокращение и его полное наименование).

    Область построения квадратная и подстраивается под размер виджета:
    с ростом панели диаграмма увеличивается, с уменьшением — сжимается,
    поэтому кольцо не вытягивается и подписи не наезжают друг на друга.
    """

    # Минимальная и максимальная сторона области построения (квадрат)
    MIN_SIDE = 180
    MAX_SIDE = 460

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._title_label = QLabel()
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setWordWrap(True)
        self._title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(self._title_label)
        self._view = _DonutView()
        # Вид растягивается по ширине панели, высота подгоняется под ширину
        # (квадрат области построения выравнивается полями диаграммы):
        # размеры виджета не меняются, поэтому раскладка не зацикливается
        self._view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._view.setMinimumWidth(self.MIN_SIDE)
        self._view.setMinimumHeight(self.MIN_SIDE)
        self._view.setMaximumWidth(self.MAX_SIDE)
        layout.addWidget(self._view, stretch=1)
        # Описание цветов — обычная надпись с переносом по словам: строки
        # пересобираются самой разметкой, а не пересчётом раскладки
        self._legend_label = QLabel()
        self._legend_label.setWordWrap(True)
        self._legend_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._legend_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(self._legend_label)
        # Пары «сокращение — полное наименование — цвет»
        self._legend_items: List[Tuple[str, str, QColor]] = []

    # ------------------------------------------------------------------
    # Квадратная область построения
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        """Держит область построения квадратной при изменении размера."""
        super().resizeEvent(event)
        side = min(max(self.width(), self.MIN_SIDE), self.MAX_SIDE)
        # Высота вида равна его ширине, поэтому область построения — квадрат.
        # Меняется только высота: ширина вида от неё не зависит, поэтому
        # раскладка не пересчитывается рекурсивно.
        if self._view.height() != side:
            self._view.setFixedHeight(side)
        self._update_title_font()

    def _update_title_font(self) -> None:
        """Заголовок периода подстраивается под размер диаграммы."""
        font = QFont(self._title_label.font())
        font.setPointSize(
            max(8, min(12, int(self.chart_side() * 0.035)))
        )
        font.setBold(True)
        self._title_label.setFont(font)

    def chart_side(self) -> int:
        """Сторона квадратной области построения (для проверок и экспорта)."""
        return self._view.square_side()

    def chart_title(self) -> str:
        """Заголовок диаграммы (период, при отсутствии данных — с пометкой)."""
        return self._title_label.text()

    def legend_descriptions(self) -> List[str]:
        """Расшифровка всех цветов диаграммы (для проверок и экспорта)."""
        return [
            STRINGS.oshm_legend_item.format(short=short, full=full)
            for short, full, _color in self._legend_items
        ]

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
        # Заголовок вынесен из диаграммы, поэтому область построения
        # остаётся квадратной и не «съедается» подписью периода
        chart.setTitle("")
        chart.setMargins(QMargins(0, 0, 0, 0))
        chart.setBackgroundRoundness(0)
        chart.legend().setVisible(False)
        self._title_label.setText(title)
        self._update_title_font()
        total = materials + telegrams
        if total == 0:
            self._title_label.setText(f"{title} — {STRINGS.chart_no_data}")
            self._view.setChart(chart)
            self._view.set_center_text("0")
            self._clear_legend()
            return

        # «Мантия»: телеграммы и материалы, пропорционально количествам.
        # Порядок секторов (телеграммы, затем материалы) совпадает с порядком
        # секторов оценок во внешнем кольце — дуги согласованы.
        # На секторах — только числа: расшифровка цветов идёт в описании.
        mantle = QPieSeries()
        mantle.setPieSize(0.54)
        mantle.setHoleSize(0.30)
        if telegrams > 0:
            slice_ = mantle.append(str(telegrams), telegrams)
            slice_.setColor(_MANTLE_COLORS["telegrams"])
            slice_.setLabelVisible(True)
            slice_.setLabelPosition(QPieSlice.LabelInsideHorizontal)
            slice_.setLabelColor(_label_color())
            slice_.setLabelFont(_sector_font())
        if materials > 0:
            slice_ = mantle.append(str(materials), materials)
            slice_.setColor(_MANTLE_COLORS["materials"])
            slice_.setLabelVisible(True)
            slice_.setLabelPosition(QPieSlice.LabelInsideHorizontal)
            slice_.setLabelColor(_label_color())
            slice_.setLabelFont(_sector_font())
        chart.addSeries(mantle)

        # Внешнее кольцо: оценки телеграмм, затем оценки материалов.
        # Каждая группа секторов занимает ровно дугу своего сектора мантии:
        # неоценённые документы закрываются сектором «без оценки».
        # Числа выводятся снаружи кольца: на узких секторах они не обрезаются.
        outer = QPieSeries()
        outer.setPieSize(0.80)
        outer.setHoleSize(0.54)
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
                self._style_outer_slice(slice_)
                if value not in legend_values:
                    legend_values.append(value)
            unevaluated = class_total - sum(evaluations.values())
            if unevaluated > 0:
                slice_ = outer.append(str(unevaluated), unevaluated)
                slice_.setColor(_NO_EVALUATION_COLOR)
                self._style_outer_slice(slice_)
                legend_no_evaluation = True
        if outer.count() > 0:
            chart.addSeries(outer)

        self._view.setChart(chart)
        self._view.set_center_text(str(total))
        self._build_legend(
            legend_values,
            legend_no_evaluation,
            telegrams=telegrams,
            materials=materials,
        )

    @staticmethod
    def _style_outer_slice(slice_: QPieSlice) -> None:
        """Оформляет сектор внешнего кольца: подпись числа снаружи кольца."""
        slice_.setLabelVisible(True)
        slice_.setLabelPosition(QPieSlice.LabelOutside)
        slice_.setLabelArmLengthFactor(0.10)
        slice_.setLabelColor(_label_color())
        slice_.setLabelFont(_sector_font())

    def _clear_legend(self) -> None:
        """Очищает описание цветов."""
        self._legend_items = []
        self._legend_label.clear()

    def _build_legend(
        self,
        values: List[int],
        no_evaluation: bool,
        telegrams: int = 0,
        materials: int = 0,
    ) -> None:
        """Строит описание диаграммы: все цвета с расшифровкой сокращений.

        В описании перечислены все цвета, встречающиеся на диаграмме:
        классы документов мантии (ТГ, НМ) и значения оценок (Б, И, П, В,
        «б/о»). Каждая пара — цветной маркер и текст «сокращение — полное
        наименование», поэтому сокращения на секторах читаются однозначно.
        Надпись переносит пары по строкам в зависимости от ширины панели.
        """
        entries: List[Tuple[str, str, QColor]] = []
        if telegrams > 0:
            entries.append(
                (
                    STRINGS.oshm_chart_telegrams,
                    STRINGS.oshm_chart_telegrams_full,
                    _MANTLE_COLORS["telegrams"],
                )
            )
        if materials > 0:
            entries.append(
                (
                    STRINGS.oshm_chart_materials,
                    STRINGS.oshm_chart_materials_full,
                    _MANTLE_COLORS["materials"],
                )
            )
        for value in sorted(values, key=_evaluation_sort_key):
            entries.append(
                (
                    _evaluation_short(value),
                    _evaluation_full(value),
                    _evaluation_color(value),
                )
            )
        if no_evaluation:
            entries.append(
                (
                    STRINGS.oshm_chart_no_evaluation_short,
                    STRINGS.oshm_chart_no_evaluation_full,
                    _NO_EVALUATION_COLOR,
                )
            )
        self._legend_items = entries
        self._legend_label.setText(self._legend_html())

    def _legend_html(self) -> str:
        """Разметка описания: цветной маркер перед каждой расшифровкой."""
        parts = []
        for short, full, color in self._legend_items:
            text = STRINGS.oshm_legend_item.format(
                short=html.escape(short), full=html.escape(full)
            )
            parts.append(
                f"<span style='color:{color.name()};'>\u25a0</span>&nbsp;{text}"
            )
        # Пары разделены точкой с запятой: одна надпись переносит их сама
        return "; ".join(parts)


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
        # Компактные списки: блок выбора периода не задаёт панели лишней
        # минимальной ширины и не вызывает горизонтальную прокрутку
        self.period_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.period_combo.setMinimumContentsLength(4)
        for key, label in PERIOD_LABELS.items():
            self.period_combo.addItem(label, key)
        layout.addWidget(self.period_combo)
        self.index_combo = QComboBox()
        self.index_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.index_combo.setMinimumContentsLength(4)
        layout.addWidget(self.index_combo)
        layout.addWidget(QLabel(STRINGS.label_year))
        self.year_combo = QComboBox()
        self.year_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.year_combo.setMinimumContentsLength(4)
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
