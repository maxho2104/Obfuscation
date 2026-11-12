"""Тесты диалога настроек: видимость полей БД и филиала."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.constants import Role
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.settings import AppSettings
from internal_correspondence.gui.settings_dialog import SettingsDialog
from internal_correspondence.orm.models import Branch, TerritorialUnit


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def env(tmp_path: Path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'settings.db'}")
    db.create_tables()
    with db.get_session() as session:
        session.add(TerritorialUnit(id="TU", name="Единица"))
        session.add(Branch(id="F1", name="Первый филиал", short_name="Ф1", territorial_unit_id="TU"))
        session.add(Branch(id="F2", name="Второй филиал", short_name="Ф2", territorial_unit_id="TU"))
        session.commit()
    settings = AppSettings(
        db_url=f"sqlite:///{(tmp_path / 'settings.db').as_posix()}",
        role=Role.BRANCH.value,
        branch_id="F2",
    )
    yield db, settings
    db.close()


def test_db_fields_visibility_by_db_type(qapp, env) -> None:
    """Поля PostgreSQL скрыты при SQLite (и наоборот); «Файл» — наоборот."""
    db, settings = env
    dialog = SettingsDialog(settings, db)

    assert dialog.sqlite_radio.isChecked()
    assert not dialog.sqlite_path.isHidden()
    assert not dialog.sqlite_browse.isHidden()
    for row in dialog._pg_rows:
        for widget in row:
            assert widget.isHidden()

    dialog.postgresql_radio.setChecked(True)
    assert dialog.sqlite_path.isHidden()
    assert dialog.sqlite_browse.isHidden()
    for row in dialog._pg_rows:
        for widget in row:
            assert not widget.isHidden()


def test_branch_combo_from_branches_table(qapp, env) -> None:
    """Комбобокс филиалов заполняется наименованиями из таблицы «Филиалы»."""
    db, settings = env
    dialog = SettingsDialog(settings, db)

    assert dialog.branch_combo.count() == 2
    texts = [
        dialog.branch_combo.itemText(index)
        for index in range(dialog.branch_combo.count())
    ]
    assert texts == ["F2 — Второй филиал", "F1 — Первый филиал"]
    # Текущее значение настройки подхвачено по данным (идентификатору)
    assert dialog.branch_combo.currentData() == "F2"


def test_branch_rows_visibility_by_role(qapp, env) -> None:
    """Поле «Филиал» скрыто для головного офиса и показано для филиала."""
    db, settings = env
    dialog = SettingsDialog(settings, db)

    index = dialog.role_combo.findData(Role.BRANCH.value)
    dialog.role_combo.setCurrentIndex(index)
    assert not dialog.branch_label.isHidden()
    assert not dialog.branch_combo.isHidden()

    index = dialog.role_combo.findData(Role.HEAD_OFFICE.value)
    dialog.role_combo.setCurrentIndex(index)
    assert dialog.branch_label.isHidden()
    assert dialog.branch_combo.isHidden()


def test_save_takes_branch_from_combo(qapp, env) -> None:
    """Сохранение забирает идентификатор филиала из комбобокса."""
    db, settings = env
    dialog = SettingsDialog(settings, db)
    index = dialog.branch_combo.findData("F1")
    dialog.branch_combo.setCurrentIndex(index)

    dialog._on_save()
    assert settings.branch_id == "F1"

    index = dialog.role_combo.findData(Role.HEAD_OFFICE.value)
    dialog.role_combo.setCurrentIndex(index)
    dialog._on_save()
    assert settings.role == Role.HEAD_OFFICE.value


def test_settings_dialog_opens_from_main_window(qapp, env) -> None:
    """Диалог настроек создаётся из главного окна без ошибок (регрессия)."""
    from internal_correspondence.gui.application import MainWindow

    db, settings = env
    window = MainWindow(settings, db)
    dialog = SettingsDialog(window.settings, window.db_manager, window)
    assert dialog.branch_combo.count() == 2
    assert dialog.sqlite_radio.isChecked()
