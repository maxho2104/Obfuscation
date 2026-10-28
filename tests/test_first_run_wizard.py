"""Тесты мастера первого запуска."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.settings import AppSettings
from internal_correspondence.gui.first_run_wizard import (
    DatabasePage,
    RolePage,
    load_branches,
)
from internal_correspondence.orm.models import Branch, TerritorialUnit


@pytest.fixture(scope="module")
def qt_app():
    """Создаёт единственный QApplication для тестов виджетов."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_with_branches(tmp_path: Path):
    """Создаёт БД с двумя филиалами."""
    db = DatabaseManager(f"sqlite:///{tmp_path / 'wizard.db'}")
    db.create_tables()
    with db.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(Branch(id="FIL001", name="Филиал 1", short_name="Ф-1", territorial_unit_id="MSK"))
        session.add(Branch(id="FIL002", name="Филиал 2", short_name="Ф-2", territorial_unit_id="MSK"))
        session.commit()
    yield db
    db.close()


def test_load_branches_from_existing_database(db_with_branches: DatabaseManager) -> None:
    """Список филиалов читается из существующей базы данных."""
    branches = load_branches(db_with_branches.db_url)
    assert branches == [("FIL001", "Филиал 1"), ("FIL002", "Филиал 2")]


def test_load_branches_returns_empty_for_missing_database(tmp_path: Path) -> None:
    """Для отсутствующего файла БД список филиалов пуст."""
    assert load_branches(f"sqlite:///{tmp_path / 'missing.db'}") == []


def test_role_page_uses_branch_identifier(qt_app, db_with_branches: DatabaseManager) -> None:
    """Выбранный филиал сохраняется в настройки по идентификатору, а не по подписи."""
    settings = AppSettings()
    page = RolePage(settings)
    page.set_branches(load_branches(db_with_branches.db_url))
    page.branch_radio.setChecked(True)
    page.branch_combo.setCurrentIndex(1)

    assert page.branch_combo.currentText() == "FIL002 — Филиал 2"
    assert page.validatePage() is True
    assert settings.role == "branch"
    assert settings.branch_id == "FIL002"


def test_role_page_selects_first_branch_by_default(
    qt_app,
    db_with_branches: DatabaseManager,
) -> None:
    """При заполнении списка автоматически выбирается первый филиал."""
    settings = AppSettings()
    page = RolePage(settings)
    page.set_branches(load_branches(db_with_branches.db_url))
    page.branch_radio.setChecked(True)

    assert page.branch_combo.currentIndex() == 0
    assert page.validatePage() is True
    assert settings.branch_id == "FIL001"


def test_role_page_accepts_typed_branch_identifier(qt_app) -> None:
    """Введённый вручную идентификатор филиала принимается, если список пуст."""
    settings = AppSettings()
    page = RolePage(settings)
    page.set_branches([])
    page.branch_radio.setChecked(True)
    page.branch_combo.setEditText("MANUAL-1")

    assert page.validatePage() is True
    assert settings.branch_id == "MANUAL-1"


def test_browse_existing_database_asks_to_use_file(qt_app, monkeypatch, tmp_path: Path) -> None:
    """При выборе существующего файла БД предлагается использовать его, а не заменить."""
    existing = tmp_path / "existing.db"
    existing.write_bytes(b"")
    captured = {}

    def fake_save_dialog(*_args, **_kwargs):
        return (str(existing), "")

    def fake_question(_parent, title, text, *_args, **_kwargs):
        captured["title"] = title
        captured["text"] = text
        return QMessageBox.Yes

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_save_dialog))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    page = DatabasePage(AppSettings())
    page._browse_sqlite()

    assert "Использовать этот файл?" in captured["text"]
    assert "заменить" not in captured["text"].lower()
    assert page.sqlite_path.text() == str(existing)


def test_browse_existing_database_rejected(qt_app, monkeypatch, tmp_path: Path) -> None:
    """При отказе использовать существующий файл путь не подставляется."""
    existing = tmp_path / "existing.db"
    existing.write_bytes(b"")

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *_args, **_kwargs: (str(existing), "")),
    )
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *_args, **_kwargs: QMessageBox.No))

    page = DatabasePage(AppSettings())
    page._browse_sqlite()

    assert page.sqlite_path.text() == ""
