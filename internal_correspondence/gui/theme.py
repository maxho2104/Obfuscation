"""Темы оформления приложения (светлая и тёмная).

Палитра применяется к ``QApplication``; для тёмной темы дополнительно
задаётся глобальная таблица стилей — стиль Windows игнорирует палитру
для ряда виджетов (кнопки, поля ввода, вкладки, меню), и только QSS
гарантирует их перекраску. Таблицы и модели читают актуальную тему
через ``current_theme()`` (цвета чередования строк и выделения
неэкспортированных изменений).
"""

from typing import Dict, Optional

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication

# Таблица стилей тёмной темы: принудительная перекраска виджетов,
# игнорирующих палитру (стиль Windows).
_DARK_STYLESHEET = """
QWidget {
    background-color: #2D2D30;
    color: #E8E8E8;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
QComboBox, QDateEdit, QDateTimeEdit, QTimeEdit {
    background-color: #1E1E21;
    color: #E8E8E8;
    border: 1px solid #3A3A3E;
    padding: 2px;
}
QComboBox QAbstractItemView {
    background-color: #1E1E21;
    color: #E8E8E8;
    selection-background-color: #3A6EA5;
    selection-color: #FFFFFF;
}
QPushButton {
    background-color: #3A3A3E;
    color: #E8E8E8;
    border: 1px solid #4A4A4F;
    border-radius: 2px;
    padding: 4px 14px;
}
QPushButton:hover { background-color: #4A4A4F; }
QPushButton:pressed { background-color: #2A2A2E; }
QPushButton:default { border-color: #3A6EA5; }
QPushButton:disabled { color: #6E6E72; }
QTabWidget::pane {
    background-color: #2D2D30;
    border: 1px solid #3A3A3E;
}
QTabBar::tab {
    background-color: #3A3A3E;
    color: #E8E8E8;
    padding: 6px 14px;
}
QTabBar::tab:selected { background-color: #1E1E21; }
QTabBar::tab:disabled { color: #6E6E72; }
QTableView, QTableWidget, QTreeWidget, QListWidget {
    background-color: #1E1E21;
    alternate-background-color: #3A3A3C;
    color: #E8E8E8;
    gridline-color: #3A3A3E;
    border: 1px solid #3A3A3E;
}
QTableView::item:selected, QTableWidget::item:selected,
QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #3A6EA5;
    color: #FFFFFF;
}
QHeaderView::section {
    background-color: #2D2D30;
    color: #E8E8E8;
    border: 1px solid #3A3A3E;
    padding: 4px;
}
QMenuBar {
    background-color: #2D2D30;
    color: #E8E8E8;
    border-bottom: 1px solid #3A3A3E;
}
QMenuBar::item { padding: 4px 10px; }
QMenuBar::item:selected { background-color: #3A6EA5; }
QMenu {
    background-color: #2D2D30;
    color: #E8E8E8;
    border: 1px solid #3A3A3E;
}
QMenu::item { padding: 4px 24px; }
QMenu::item:selected { background-color: #3A6EA5; }
QMenu::item:disabled { color: #6E6E72; }
QGroupBox {
    color: #E8E8E8;
    border: 1px solid #3A3A3E;
    margin-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 2px;
}
QCheckBox, QRadioButton, QLabel { background: transparent; color: #E8E8E8; }
QToolTip {
    background-color: #2D2D30;
    color: #E8E8E8;
    border: 1px solid #3A3A3E;
}
QScrollBar:vertical {
    background: #1E1E21;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #4A4A4F;
    min-height: 24px;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover { background: #5A5A5F; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #1E1E21;
    height: 12px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #4A4A4F;
    min-width: 24px;
    border-radius: 6px;
}
QScrollBar::handle:horizontal:hover { background: #5A5A5F; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QDialog { background-color: #2D2D30; }
"""


class Theme:
    """Набор цветов темы оформления."""

    def __init__(
        self,
        key: str,
        label: str,
        stripe: QColor,
        modified_row: QColor,
        no_incoming_row: Optional[QColor] = None,
        colors: Optional[Dict[str, QColor]] = None,
        disabled: Optional[Dict[str, QColor]] = None,
        stylesheet: str = "",
        unassigned_row: Optional[QColor] = None,
    ) -> None:
        self.key = key
        self.label = label
        # Цвет чередования строк таблиц (AlternateBase)
        self.stripe = stripe
        # Фон записей с неэкспортированными изменениями
        self.modified_row = modified_row
        # Фон нераспределённых задач в модуле «Задачи»
        self.unassigned_row = unassigned_row or QColor("#F7C6D9")
        # Фон документов без входящего номера (менее яркий, чем modified_row)
        self.no_incoming_row = no_incoming_row or modified_row
        # Переопределения палитры: имя роли QPalette -> цвет
        self.colors = colors or {}
        # Цвета неактивных элементов: имя роли -> цвет
        self.disabled = disabled or {}
        # Глобальная таблица стилей (для тёмной темы)
        self.stylesheet = stylesheet

    def apply(self, app: QApplication) -> None:
        """Применяет тему к приложению."""
        palette = self._build_palette(app)
        app.setPalette(palette)
        app.setStyleSheet(self.stylesheet)

    def _build_palette(self, app: QApplication) -> QPalette:
        """Формирует палитру на основе стандартной стиля."""
        palette = app.style().standardPalette()
        for role_name, color in self.colors.items():
            palette.setColor(getattr(QPalette, role_name), color)
        for role_name, color in self.disabled.items():
            palette.setColor(QPalette.Disabled, getattr(QPalette, role_name), color)
        palette.setColor(QPalette.AlternateBase, self.stripe)
        return palette


LIGHT_THEME = Theme(
    key="light",
    label="Светлая тема",
    stripe=QColor("#EFF2F6"),
    modified_row=QColor("#FFE6B4"),
    no_incoming_row=QColor("#E3EDF7"),
)

DARK_THEME = Theme(
    key="dark",
    label="Тёмная тема",
    stripe=QColor("#3A3A3C"),
    modified_row=QColor("#7E6434"),
    unassigned_row=QColor("#5A2A3A"),
    no_incoming_row=QColor("#2F3B4C"),
    colors={
        "Window": QColor("#2D2D30"),
        "Base": QColor("#1E1E21"),
        "Text": QColor("#E8E8E8"),
        "WindowText": QColor("#E8E8E8"),
        "Button": QColor("#3A3A3E"),
        "ButtonText": QColor("#E8E8E8"),
        "Highlight": QColor("#3A6EA5"),
        "HighlightedText": QColor("#FFFFFF"),
        "ToolTipBase": QColor("#2D2D30"),
        "ToolTipText": QColor("#E8E8E8"),
        "Link": QColor("#569CD6"),
        "BrightText": QColor("#FF5555"),
    },
    disabled={
        "Text": QColor("#6E6E72"),
        "WindowText": QColor("#6E6E72"),
        "ButtonText": QColor("#6E6E72"),
    },
    stylesheet=_DARK_STYLESHEET,
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
    """Применяет тему по ключу; неизвестный ключ — светлая тема."""
    theme = THEMES.get(key, LIGHT_THEME)
    theme.apply(app)
    _current_theme["theme"] = theme
    return theme
