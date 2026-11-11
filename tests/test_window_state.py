"""Тесты сохранения геометрии окна и ширин колонок между запусками."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PyQt5.QtCore import QByteArray
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.settings import AppSettings, SettingsManager
from internal_correspondence.gui.application import MainWindow, _parse_column_widths


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    """Единственный QApplication для тестов окон."""
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window_env(tmp_path: Path):
    """База данных и настройки во временном каталоге."""
    db = DatabaseManager(f"sqlite:///{tmp_path / 'ui.db'}")
    db.create_tables()
    manager = SettingsManager(tmp_path)
    settings = AppSettings(
        db_url=f"sqlite:///{tmp_path / 'ui.db'}",
        storage_path=str(tmp_path / "storage"),
        branch_id="BR-001",
    )
    yield settings, db, manager
    db.close()


def test_parse_column_widths() -> None:
    """Разбор строки ширин: числа через запятую, мусор игнорируется."""
    assert _parse_column_widths("80,100, 250,") == [80, 100, 250]
    assert _parse_column_widths("") == []
    assert _parse_column_widths("abc,10,-5") == [10]


def test_main_window_saves_ui_state(window_env, qt_app: QApplication) -> None:
    """Закрытие окна сохраняет геометрию и ширины колонок в настройки."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.resize(1100, 700)
    window.materials_tab.table.setColumnWidth(0, 177)
    window.telegram_tab.table.setColumnWidth(1, 210)
    window._save_ui_state()

    saved = manager.load()
    assert saved.window_geometry
    assert saved.material_column_widths.split(",")[0] == "177"
    assert saved.telegram_column_widths.split(",")[1] == "210"

    # Повторное сохранение при закрытии не должно падать
    window.close()


def test_main_window_restores_column_widths(window_env, qt_app: QApplication) -> None:
    """При создании окно применяет сохранённые ширины колонок."""
    settings, db, manager = window_env
    settings.material_column_widths = "177,210,300"
    settings.telegram_column_widths = "90,140"
    window = MainWindow(settings, db, manager)
    assert window.materials_tab.column_widths()[:3] == [177, 210, 300]
    assert window.telegram_tab.column_widths()[:2] == [90, 140]
    window.close()


def test_geometry_roundtrip(window_env, qt_app: QApplication) -> None:
    """Геометрия окна сохраняется и восстанавливается без искажений."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.resize(1200, 900)
    window._save_ui_state()

    saved_geometry = manager.load().window_geometry
    assert saved_geometry

    restored = window.restoreGeometry(
        QByteArray.fromBase64(saved_geometry.encode("ascii"))
    )
    assert restored
    assert window.width() == 1200
    assert window.height() == 900
    window.close()


def test_empty_geometry_is_tolerated(window_env, qt_app: QApplication) -> None:
    """Отсутствие сохранённого состояния (первый запуск) не мешает старту."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    assert window.settings.window_geometry == ""
    window.close()
