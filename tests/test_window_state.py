"""Тесты сохранения геометрии окна и ширин колонок между запусками."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.settings import AppSettings, SettingsManager
from internal_correspondence.gui.application import MainWindow, _parse_column_widths
from internal_correspondence.utils.string_resources import STRINGS


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


# ---------------------------------------------------------------------------
# Док-виджет прикреплённых файлов: меню «Вид» и сохранение положения
# ---------------------------------------------------------------------------


def test_files_dock_menu_action_toggles_visibility(window_env, qt_app: QApplication) -> None:
    """Пункт меню «Вид» → «Прикреплённые файлы» показывает/скрывает док."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    action = window.files_dock_action
    assert action.isCheckable()
    assert action.text() == STRINGS.menu_attached_files

    window.show()
    qt_app.processEvents()
    assert action.isChecked()

    # Снятие галочки скрывает док
    action.trigger()
    qt_app.processEvents()
    assert window.files_dock.isHidden()
    assert not action.isChecked()

    # Показ дока вновь отмечает пункт меню
    window.files_dock.setVisible(True)
    qt_app.processEvents()
    assert action.isChecked()
    window.close()


def test_files_dock_dock_area_saved_on_close(window_env, qt_app: QApplication) -> None:
    """Закрытие окна сохраняет область стыковки и геометрию дока."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.show()
    window.addDockWidget(Qt.LeftDockWidgetArea, window.files_dock)
    window._save_ui_state()

    saved = manager.load()
    assert saved.files_dock_visible == "true"
    assert saved.files_dock_area == str(int(Qt.LeftDockWidgetArea))
    assert saved.files_dock_floating == "false"
    assert saved.files_dock_geometry
    window.close()


def test_files_dock_hidden_state_saved_on_close(window_env, qt_app: QApplication) -> None:
    """Скрытый через меню док запоминается как скрытый."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.show()
    window.files_dock_action.trigger()
    window._save_ui_state()

    saved = manager.load()
    assert saved.files_dock_visible == "false"
    window.close()


def test_files_changed_signal_updates_document_row_highlight(window_env, qt_app: QApplication, tmp_path: Path) -> None:
    """Прикрепление файла через док-виджет сразу даёт подсветку изменённой строки."""
    from datetime import date

    from internal_correspondence.core.constants import MaterialType, Role
    from internal_correspondence.core.domain_pack import dir_name
    from internal_correspondence.gui.theme import current_theme
    from internal_correspondence.importexport.export_service import ExportService
    from internal_correspondence.orm.models import (
        Branch,
        ScientificMaterial,
        TerritorialUnit,
    )
    from internal_correspondence.services.change_tracking import register_change_tracking

    register_change_tracking()
    settings, db, manager = window_env
    settings.role = Role.BRANCH.value
    settings.branch_id = "F1"
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()

    with db.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK"))
        material = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-1",
            outgoing_date=date(2026, 1, 1),
            name="Материал",
            branch_id="F1",
        )
        session.add(material)
        session.commit()
        material_id = material.id

    # Экспортируем начальные изменения: строка без подсветки «изменено»
    storage = settings.storage_path_obj()
    storage.mkdir(parents=True, exist_ok=True)
    with db.get_session() as session:
        ExportService(session, storage).export()
        session.commit()

    window.materials_tab.refresh()
    assert window.materials_tab.reveal_record(material_id)
    row = window.materials_tab.table_model.row_of(material_id)
    theme = current_theme()
    assert (
        window.materials_tab.table_model.index(row, 0).data(Qt.BackgroundRole)
        != theme.modified_row
    )

    # Файл внутри хранилища: привязка без копирования (синхронный путь дока)
    inside = (
        storage
        / dir_name("files")
        / dir_name("material_files")
        / "old"
        / "report.txt"
    )
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text("x", encoding="utf-8")

    window.files_dock.set_document(
        window.files_dock.session.get(ScientificMaterial, material_id)
    )
    window.files_dock._add_paths([inside])  # pylint: disable=protected-access

    color = window.materials_tab.table_model.index(row, 0).data(Qt.BackgroundRole)
    assert color == theme.modified_row
    window.close()


def test_files_dock_state_restored_from_settings(window_env, qt_app: QApplication) -> None:
    """При запуске док восстанавливает область стыковки и видимость из настроек."""
    settings, db, manager = window_env
    settings.files_dock_area = str(int(Qt.LeftDockWidgetArea))
    settings.files_dock_visible = "false"
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()

    assert window.dockWidgetArea(window.files_dock) == Qt.LeftDockWidgetArea
    assert window.files_dock.isHidden()
    assert not window.files_dock_action.isChecked()
    window.close()


def test_files_dock_floating_geometry_roundtrip(window_env, qt_app: QApplication) -> None:
    """Откреплённый отдельным окном док восстанавливается с той же геометрией."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.show()
    window.files_dock.setFloating(True)
    window.files_dock.setGeometry(40, 60, 420, 300)
    window._save_ui_state()

    saved = manager.load()
    assert saved.files_dock_floating == "true"
    assert saved.files_dock_geometry
    window.close()

    restored = MainWindow(saved, db, manager)
    restored.show()
    qt_app.processEvents()
    assert restored.files_dock.isFloating()
    assert (
        restored.files_dock.saveGeometry().toBase64().data().decode("ascii")
        == saved.files_dock_geometry
    )
    restored.close()
