"""Тесты тем оформления приложения."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.settings import AppSettings, SettingsManager
from internal_correspondence.gui.theme import THEMES, apply_theme, current_theme


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    """Единственный QApplication для тестов тем."""
    return QApplication.instance() or QApplication([])


def test_themes_defined() -> None:
    """Зарегистрированы обе темы с непустыми названиями."""
    assert set(THEMES) == {"light", "dark"}
    assert THEMES["light"].label
    assert THEMES["dark"].label


def test_apply_theme_switches_palette(qt_app: QApplication) -> None:
    """Смена темы меняет базовый и чередующийся цвета палитры."""
    light = apply_theme(qt_app, "light")
    base_light = qt_app.palette().color(QPalette.Base)
    stripe_light = qt_app.palette().color(QPalette.AlternateBase)

    dark = apply_theme(qt_app, "dark")
    base_dark = qt_app.palette().color(QPalette.Base)
    stripe_dark = qt_app.palette().color(QPalette.AlternateBase)

    assert base_light != base_dark
    assert stripe_light == light.stripe
    assert stripe_dark == dark.stripe
    assert current_theme().key == "dark"

    apply_theme(qt_app, "light")


def test_unknown_theme_falls_back_to_light(qt_app: QApplication) -> None:
    """Неизвестный ключ темы применяет светлую тему."""
    theme = apply_theme(qt_app, "unknown-key")
    assert theme.key == "light"
    assert current_theme().key == "light"


def test_modified_row_color_differs() -> None:
    """Цвет выделения изменений различается между темами."""
    assert THEMES["light"].modified_row != THEMES["dark"].modified_row
    assert THEMES["light"].stripe != THEMES["dark"].stripe


def test_both_themes_load_external_stylesheet(qt_app: QApplication) -> None:
    """Обе темы применяют общий QSS-шаблон со своей палитрой."""
    apply_theme(qt_app, "dark")
    dark_stylesheet = qt_app.styleSheet()
    assert dark_stylesheet
    assert "{{" not in dark_stylesheet

    apply_theme(qt_app, "light")
    light_stylesheet = qt_app.styleSheet()
    assert light_stylesheet
    assert "{{" not in light_stylesheet
    assert light_stylesheet != dark_stylesheet


def test_custom_title_bar_is_styled_by_both_themes() -> None:
    """Шапка и её кнопки оформлены общим QSS обеих тем."""
    for theme in THEMES.values():
        stylesheet = theme.stylesheet
        assert "QMenuBar#mainMenuBar" in stylesheet
        assert "QLabel#windowTitle" in stylesheet
        assert "QWidget#dialogTitleBar" in stylesheet
        assert "QLabel#dialogWindowTitle" in stylesheet
        assert "QToolButton#windowMinimizeButton" in stylesheet
        assert "QToolButton#windowMaximizeButton" in stylesheet
        assert "QToolButton#windowCloseButton" in stylesheet
        assert theme.qss_colors["TITLE_TEXT"] in stylesheet

    assert THEMES["light"].qss_colors["TITLE_TEXT"] == "#9A6B00"
    assert THEMES["dark"].qss_colors["TITLE_TEXT"] == "#D8B45A"


def test_all_combo_boxes_use_themed_down_arrow() -> None:
    """Общая стрелка раскрытия применяется ко всем выпадающим спискам."""
    for theme in THEMES.values():
        stylesheet = theme.stylesheet
        assert "QComboBox::down-arrow" in stylesheet
        assert "QComboBox[role=\"statistics\"]::down-arrow" not in stylesheet
        assert theme.qss_colors["COMBO_ARROW"] in stylesheet


def test_dark_theme_styles_scroll_area_corner() -> None:
    """Тёмная тема красит уголок пересечения полос прокрутки таблицы.

    Без правила QAbstractScrollArea::corner стиль Windows рисует его
    дефолтным светлым фоном — белый прямоугольник в тёмном интерфейсе.
    Стиль Windows игнорирует и это правило, поэтому дополнительно есть
    виджет-уголок с именем объекта (правило QWidget#scroll_area_corner)
    и установщик таких виджетов (см. test_dark_theme_installs_corner_widget).
    """
    stylesheet = THEMES["dark"].stylesheet
    assert "QAbstractScrollArea::corner" in stylesheet
    corner_rule = stylesheet.split("QAbstractScrollArea::corner", 1)[1].split("}", 1)[0]
    assert "#1E1E21" in corner_rule
    named_rule = stylesheet.split("#scroll_area_corner", 1)[1].split("}", 1)[0]
    assert "#1E1E21" in named_rule


def test_dark_theme_installs_corner_widget(qt_app: QApplication) -> None:
    """Тёмная тема ставит виджет-уголок каждой scroll-area (обход дефекта стиля Windows)."""
    from PyQt5.QtWidgets import QTableView

    from internal_correspondence.gui.theme import CORNER_WIDGET_NAME

    apply_theme(qt_app, "dark")
    view = QTableView()
    view.show()
    qt_app.processEvents()
    corner = view.cornerWidget()
    assert corner is not None
    assert corner.objectName() == CORNER_WIDGET_NAME
    view.close()

    apply_theme(qt_app, "light")


def test_item_background_role_visible_in_both_themes(qt_app: QApplication) -> None:
    """QSS-шаблон не глушит фон строк из модели (BackgroundRole).

    Базовое правило «QTableView::item { padding; border }» заставляет
    QStyleSheetStyle рисовать фон элементов самостоятельно, и подсветка
    неэкспортированных / без входящего номера строк пропадает в обеих
    темах. Проверка пикселями: цвета темы реально присутствуют
    в отрисованной таблице.
    """
    from PyQt5.QtGui import QStandardItem, QStandardItemModel
    from PyQt5.QtWidgets import QTableView

    for key in ("dark", "light"):
        theme = apply_theme(qt_app, key)
        model = QStandardItemModel(4, 2)
        for row in range(4):
            for column in range(2):
                item = QStandardItem(f"{row},{column}")
                item.setBackground(
                    theme.modified_row if row < 2 else theme.no_incoming_row
                )
                model.setItem(row, column, item)
        view = QTableView()
        view.setAlternatingRowColors(True)
        view.setModel(model)
        view.resize(300, 220)
        view.show()
        qt_app.processEvents()
        image = view.grab().toImage()
        rendered = {image.pixelColor(60, y).name() for y in range(40, 200)}
        view.close()
        assert theme.modified_row.name() in rendered, key
        assert theme.no_incoming_row.name() in rendered, key

    apply_theme(qt_app, "light")


def test_row_highlight_colors_contrast_with_table() -> None:
    """Цвета подсветки строк отличны от фона и чередования таблицы."""
    for theme in THEMES.values():
        assert theme.modified_row != theme.stripe
        assert theme.no_incoming_row != theme.stripe
        assert theme.modified_row != theme.colors["Base"]
        assert theme.no_incoming_row != theme.colors["Base"]


def test_theme_setting_roundtrip(tmp_path) -> None:
    """Выбор темы сохраняется в INI и читается обратно."""
    manager = SettingsManager(tmp_path)
    manager.save(AppSettings(theme="dark"))
    assert SettingsManager(tmp_path).load().theme == "dark"

    # Отсутствие ключа в INI — значение по умолчанию
    (tmp_path / "settings.ini").write_text(
        "[Application]\nlanguage = ru\n", encoding="utf-8"
    )
    assert SettingsManager(tmp_path).load().theme == "light"


def test_duplicate_option_is_tolerated(tmp_path) -> None:
    """Продублированный ключ в INI не роняет загрузку (последнее значение)."""
    (tmp_path / "settings.ini").write_text(
        "[Application]\ntheme = light\ntheme = dark\n", encoding="utf-8"
    )
    assert SettingsManager(tmp_path).load().theme == "dark"
