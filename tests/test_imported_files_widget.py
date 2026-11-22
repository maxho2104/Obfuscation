"""Тесты виджета файлов последнего импорта на дашборде."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox


from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.imported_files_widget import ImportedFilesWidget
from internal_correspondence.importexport.import_service import (
    read_import_manifest,
    write_import_manifest,
)
from internal_correspondence.orm.models import FileRecord


@pytest.fixture(scope="module")
def qt_app():
    """Единственный QApplication для тестов виджетов."""
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def env(tmp_path: Path):
    """Хранилище с двумя файлами, манифестом и сессией БД."""
    db = DatabaseManager(f"sqlite:///{tmp_path / 'imported.db'}")
    db.create_tables()
    storage = tmp_path / "storage"
    docs = storage / "Файлы" / "Документы"
    docs.mkdir(parents=True)
    first = docs / "alpha.txt"
    first.write_text("a", encoding="utf-8")
    second = docs / "beta.txt"
    second.write_text("b", encoding="utf-8")
    write_import_manifest(
        storage,
        ["Файлы/Документы/beta.txt", "Файлы/Документы/alpha.txt"],
    )
    yield db, storage, docs
    db.close()


def _texts(widget: ImportedFilesWidget) -> list:
    return [
        widget.list_widget.item(row).text()
        for row in range(widget.list_widget.count())
        if widget.list_widget.item(row).data(Qt.UserRole + 2) is not None
    ]


def test_imported_files_sorted_alphabetically(qt_app, env) -> None:
    """Элементы списка упорядочены по алфавиту имени файла."""
    db, storage, docs = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        assert _texts(widget) == ["alpha.txt", "beta.txt"]


def test_imported_files_regex_filter(qt_app, env) -> None:
    """Фильтр по имени с regex: подходящие видны, мусорный шаблон не ломает список."""
    db, storage, docs = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)

        widget.filter_edit.setText("^b")
        hidden = [
            widget.list_widget.item(row).isHidden()
            for row in range(widget.list_widget.count())
        ]
        assert hidden == [True, False]

        widget.filter_edit.setText("[")
        assert all(
            not widget.list_widget.item(row).isHidden()
            for row in range(widget.list_widget.count())
        )
        assert widget.filter_edit.toolTip()

        widget.filter_edit.setText("")
        assert all(
            not widget.list_widget.item(row).isHidden()
            for row in range(widget.list_widget.count())
        )
        assert not widget.filter_edit.toolTip()


def test_imported_files_missing_file_marked(qt_app, env) -> None:
    """Отсутствующий файл остаётся в списке с зачёркнутым шрифтом."""
    db, storage, docs = env
    (docs / "beta.txt").unlink()
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        item = widget.list_widget.item(1)
        assert item.text() == "beta.txt"
        assert item.font().strikeOut()
    (docs / "beta.txt").write_text("b", encoding="utf-8")


def test_imported_files_drag_mime_contains_file_url(qt_app, env) -> None:
    """Перетаскивание наружу отдаёт URL файла (проводник скопирует файл)."""
    db, storage, docs = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        item = widget.list_widget.item(0)
        mime = widget.list_widget.mimeData([item])
        assert mime.hasUrls()
        assert Path(mime.urls()[0].toLocalFile()) == docs / "alpha.txt"


def test_imported_files_rename_updates_disk_db_and_manifest(
    qt_app, env, monkeypatch
) -> None:
    """Переименование меняет файл на диске, запись БД и манифест."""
    db, storage, docs = env
    with db.get_session() as session:
        session.add(
            FileRecord(
                path="Файлы/Документы",
                name="alpha",
                extension="txt",
            )
        )
        session.commit()
        widget = ImportedFilesWidget(session, storage)
        monkeypatch.setattr(
            QInputDialog,
            "getText",
            staticmethod(lambda *args, **kwargs: ("gamma.txt", True)),
        )
        widget._rename_item(widget.list_widget.item(0))

        assert (docs / "gamma.txt").exists()
        assert not (docs / "alpha.txt").exists()
        assert read_import_manifest(storage) == [
            "Файлы/Документы/beta.txt",
            "Файлы/Документы/gamma.txt",
        ]
        record = (
            session.query(FileRecord)
            .filter_by(path="Файлы/Документы", name="gamma", extension="txt")
            .one()
        )
        assert record is not None
        assert _texts(widget) == ["beta.txt", "gamma.txt"]


def test_imported_files_rename_without_record(qt_app, env, monkeypatch) -> None:
    """Переименование файла без записи БД меняет диск и манифест."""
    db, storage, docs = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        monkeypatch.setattr(
            QInputDialog,
            "getText",
            staticmethod(lambda *args, **kwargs: ("delta.txt", True)),
        )
        widget._rename_item(widget.list_widget.item(1))
        assert (docs / "delta.txt").exists()
        assert read_import_manifest(storage) == [
            "Файлы/Документы/delta.txt",
            "Файлы/Документы/alpha.txt",
        ]


def test_imported_files_delete_removes_disk_and_manifest(
    qt_app, env, monkeypatch
) -> None:
    """Удаление убирает файлы с диска и из манифеста."""
    db, storage, docs = env
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.Yes),
    )
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        widget._delete_items(list(widget.list_widget.selectedItems()) or [
            widget.list_widget.item(0),
            widget.list_widget.item(1),
        ])
        assert not (docs / "alpha.txt").exists()
        assert not (docs / "beta.txt").exists()
        assert read_import_manifest(storage) == []
        assert _texts(widget) == []
