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
