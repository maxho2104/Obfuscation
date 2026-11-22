"""Светлая и тёмная темы приложения на основе внешнего QSS-шаблона."""

from functools import lru_cache
from pathlib import Path
import re
from typing import Dict, Mapping, Optional

from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QAbstractScrollArea, QApplication, QWidget

_QSS_PATH = Path(__file__).with_name("application.qss")
_ICON_PATH = Path(__file__).with_name("icons")
_QSS_TOKEN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

# Имя виджета-уголка пересечения полос прокрутки.
CORNER_WIDGET_NAME = "scroll_area_corner"


@lru_cache(maxsize=1)
def _qss_template() -> str:
    """Читает общий QSS-шаблон один раз за время работы приложения."""
    return _QSS_PATH.read_text(encoding="utf-8")


class _ScrollCornerInstaller(QObject):
    """Ставит стилизуемый виджет-уголок каждой области прокрутки."""

    def eventFilter(self, watched: QObject, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Polish and isinstance(
            watched, QAbstractScrollArea
        ):
            if watched.cornerWidget() is None:
                corner = QWidget(watched)
                corner.setObjectName(CORNER_WIDGET_NAME)
                watched.setCornerWidget(corner)
        return False


def _ensure_corner_installer(app: QApplication) -> None:
    """Подключает установщик уголков к приложению один раз."""
    if getattr(app, "_scroll_corner_installer", None) is None:
        installer = _ScrollCornerInstaller(app)
        app.installEventFilter(installer)
        app._scroll_corner_installer = installer


class Theme:
    """Цвета темы для внешнего QSS, палитры, таблиц и диаграмм."""

    def __init__(
        self,
        key: str,
        label: str,
        stripe: QColor,
        modified_row: QColor,
        qss_colors: Mapping[str, str],
        no_incoming_row: Optional[QColor] = None,
        colors: Optional[Dict[str, QColor]] = None,
        disabled: Optional[Dict[str, QColor]] = None,
        unassigned_row: Optional[QColor] = None,
        chart_selection: Optional[QColor] = None,
    ) -> None:
        self.key = key
        self.label = label
        self.stripe = stripe
        self.modified_row = modified_row
        self.unassigned_row = unassigned_row or QColor("#F7C6D9")
        self.no_incoming_row = no_incoming_row or modified_row
        self.chart_selection = chart_selection or QColor("#E8710A")
        self.qss_colors = dict(qss_colors)
        self.colors = colors or {}
        self.disabled = disabled or {}

    @property
    def stylesheet(self) -> str:
        """Подставляет цвета выбранной темы во внешний QSS-шаблон."""
        template = _qss_template()
        required = set(_QSS_TOKEN.findall(template))
        missing = required.difference(self.qss_colors)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"Для темы {self.key!r} отсутствуют цвета: {names}")
        return _QSS_TOKEN.sub(
            lambda match: self.qss_colors[match.group(1)],
            template,
        )

    def apply(self, app: QApplication) -> None:
        """Применяет согласованные палитру и внешний QSS ко всему приложению."""
        app.setPalette(self._build_palette(app))
        app.setStyleSheet(self.stylesheet)
        _ensure_corner_installer(app)

    def _build_palette(self, app: QApplication) -> QPalette:
        """Создаёт палитру Qt из цветов темы."""
        palette = app.style().standardPalette()
        for role_name, color in self.colors.items():
            palette.setColor(getattr(QPalette, role_name), color)
        for role_name, color in self.disabled.items():
            palette.setColor(QPalette.Disabled, getattr(QPalette, role_name), color)
        palette.setColor(QPalette.AlternateBase, self.stripe)
        return palette


LIGHT_COLORS = {
    "COMBO_ARROW": _ICON_PATH.joinpath("combo-arrow-light.svg").as_posix(),
    "WINDOW": "#F3F6FA",
    "SURFACE": "#FFFFFF",
    "SURFACE_ALT": "#F7F9FC",
    "SURFACE_HOVER": "#EDF2F8",
    "BORDER": "#D9E1EC",
    "BORDER_STRONG": "#B8C5D6",
    "TEXT": "#1B2638",
    "TEXT_MUTED": "#66758A",
    "TEXT_DISABLED": "#9CA8B8",
    "TITLE_TEXT": "#9A6B00",
    "ACCENT": "#3569D4",
    "ACCENT_HOVER": "#2958B9",
    "ACCENT_PRESSED": "#214794",
    "ACCENT_SOFT": "#E7EFFF",
    "ON_ACCENT": "#FFFFFF",
    "DANGER": "#C2414D",
    "DANGER_HOVER": "#A93440",
    "DANGER_SOFT": "#FFF0F2",
    "SUCCESS": "#2F805C",
    "SUCCESS_HOVER": "#276C4D",
    "SCROLL": "#B9C4D2",
    "SCROLL_HOVER": "#909EB1",
    "SCROLL_CORNER": "#FFFFFF",
}

DARK_COLORS = {
    "COMBO_ARROW": _ICON_PATH.joinpath("combo-arrow-dark.svg").as_posix(),
    "WINDOW": "#151A23",
    "SURFACE": "#1D2430",
    "SURFACE_ALT": "#242D3A",
    "SURFACE_HOVER": "#2A3545",
    "BORDER": "#344153",
    "BORDER_STRONG": "#4A5A70",
    "TEXT": "#E9EDF4",
    "TEXT_MUTED": "#A3AFC0",
    "TEXT_DISABLED": "#647084",
    "TITLE_TEXT": "#D8B45A",
    "ACCENT": "#6E98F5",
    "ACCENT_HOVER": "#83A8FA",
    "ACCENT_PRESSED": "#557ED8",
    "ACCENT_SOFT": "#273A60",
    "ON_ACCENT": "#10182A",
    "DANGER": "#F07980",
    "DANGER_HOVER": "#FC9399",
    "DANGER_SOFT": "#472B33",
    "SUCCESS": "#4DB887",
    "SUCCESS_HOVER": "#62CA99",
    "SCROLL": "#4B596D",
    "SCROLL_HOVER": "#66758A",
    "SCROLL_CORNER": "#1E1E21",
}


def _palette(colors: Mapping[str, str]) -> Dict[str, QColor]:
    """Создаёт основные роли палитры Qt из словаря цветов QSS."""
    return {
        "Window": QColor(colors["WINDOW"]),
        "Base": QColor(colors["SURFACE"]),
        "AlternateBase": QColor(colors["SURFACE_ALT"]),
        "Text": QColor(colors["TEXT"]),
        "WindowText": QColor(colors["TEXT"]),
        "Button": QColor(colors["SURFACE"]),
        "ButtonText": QColor(colors["TEXT"]),
        "Highlight": QColor(colors["ACCENT"]),
        "HighlightedText": QColor(colors["ON_ACCENT"]),
        "ToolTipBase": QColor(colors["TEXT"]),
        "ToolTipText": QColor(colors["SURFACE"]),
        "Link": QColor(colors["ACCENT"]),
        "BrightText": QColor(colors["DANGER"]),
    }


def _disabled(colors: Mapping[str, str]) -> Dict[str, QColor]:
    """Создаёт цвета неактивных ролей палитры."""
    disabled = QColor(colors["TEXT_DISABLED"])
    return {
        "Text": disabled,
        "WindowText": disabled,
        "ButtonText": disabled,
    }


LIGHT_THEME = Theme(
    key="light",
    label="Светлая тема",
    stripe=QColor(LIGHT_COLORS["SURFACE_ALT"]),
    modified_row=QColor("#FFF0C2"),
    no_incoming_row=QColor("#E3EDF7"),
    qss_colors=LIGHT_COLORS,
    colors=_palette(LIGHT_COLORS),
    disabled=_disabled(LIGHT_COLORS),
)

DARK_THEME = Theme(
    key="dark",
    label="Тёмная тема",
    stripe=QColor(DARK_COLORS["SURFACE_ALT"]),
    modified_row=QColor("#7E6434"),
    unassigned_row=QColor("#5A2A3A"),
    no_incoming_row=QColor("#35496B"),
    chart_selection=QColor("#FFB74D"),
    qss_colors=DARK_COLORS,
    colors=_palette(DARK_COLORS),
    disabled=_disabled(DARK_COLORS),
)

THEMES: Dict[str, Theme] = {
    LIGHT_THEME.key: LIGHT_THEME,
    DARK_THEME.key: DARK_THEME,
}

_current_theme: Dict[str, Theme] = {"theme": LIGHT_THEME}


def current_theme() -> Theme:
    """Возвращает применённую в данный момент тему."""
    return _current_theme["theme"]


def apply_theme(app: QApplication, key: str) -> Theme:
    """Применяет тему по ключу; неизвестный ключ заменяет светлой темой."""
    theme = THEMES.get(key, LIGHT_THEME)
    theme.apply(app)
    _current_theme["theme"] = theme
    return theme
