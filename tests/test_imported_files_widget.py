"""Тесты виджета файлов последнего импорта на дашборде."""

import os
import uuid
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox


from internal_correspondence.core.constants import MaterialType, Role, TelegramType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.imported_files_widget import (
    ImportedFilesWidget,
)
from internal_correspondence.importexport.import_service import (
    read_import_manifest,
    write_import_manifest,
)
from internal_correspondence.orm.models import (
    Branch,
    FileRecord,
    ScientificMaterial,
    Telegram,
    TerritorialUnit,
)


@pytest.fixture(scope="module")
def qt_app():
    """Единственный QApplication для тестов виджетов."""
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def env(tmp_path: Path):
    """Хранилище с двумя файлами, записями БД и манифестом из UUID."""
    db = DatabaseManager(f"sqlite:///{tmp_path / 'imported.db'}")
    db.create_tables()
    storage = tmp_path / "storage"
    docs = storage / "Файлы" / "Документы"
    docs.mkdir(parents=True)
    (docs / "alpha.txt").write_text("a", encoding="utf-8")
    (docs / "beta.txt").write_text("b", encoding="utf-8")
    with db.get_session() as session:
        session.add(TerritorialUnit(id="TU", name="Единица"))
        session.add(
            Branch(
                id="F1", name="Филиал 1", short_name="Ф1",
                territorial_unit_id="TU",
            )
        )
        alpha = FileRecord(path="Файлы/Документы", name="alpha", extension="txt")
        beta = FileRecord(path="Файлы/Документы", name="beta", extension="txt")
        material = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-1",
            outgoing_date=date(2026, 3, 1),
            name="Материал",
            branch_id="F1",
        )
        telegram = Telegram(
            type=TelegramType.THEMATIC,
            outgoing_number="Т-2",
            outgoing_date=date(2026, 4, 15),
            name="Тема",
            branch_id="F1",
        )
        material.files.append(alpha)
        telegram.files.append(beta)
        session.add_all([alpha, beta, material, telegram])
        session.commit()
        ids = {"alpha": str(alpha.id), "beta": str(beta.id)}
    write_import_manifest(storage, [ids["beta"], ids["alpha"]])
    yield db, storage, docs, ids
    db.close()


def _rows(widget: ImportedFilesWidget) -> list:
    """Возвращает строки данных модели в порядке отображения."""
    return [
        widget.table_model.row_at(widget.table_model.index(row, 0))
        for row in range(widget.table_model.rowCount())
    ]


def _visible_count(widget: ImportedFilesWidget) -> int:
    """Возвращает число строк, видимых через прокси-модель фильтра."""
    return widget.proxy_model.rowCount()


def test_imported_files_sorted_alphabetically(qt_app, env) -> None:
    """Строки упорядочены по алфавиту имени файла."""
    db, storage, docs, ids = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        assert [row.filename for row in _rows(widget)] == [
            "alpha.txt",
            "beta.txt",
        ]


def test_imported_files_columns_take_data_from_db(qt_app, env) -> None:
    """Колонки заполнены из базы: филиал, тип документа, номер и дата."""
    db, storage, docs, ids = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        alpha, beta = _rows(widget)
        assert (alpha.branch, alpha.doc_type, alpha.outgoing) == (
            "Филиал 1",
            "Научный материал",
            "М-1 от 01.03.2026",
        )
        assert (beta.branch, beta.doc_type, beta.outgoing) == (
            "Филиал 1",
            "Телеграмма",
            "Т-2 от 15.04.2026",
        )


def test_imported_files_filter_matches_any_column(qt_app, env) -> None:
    """Поиск подстрокой работает по имени, филиалу, типу и реквизитам."""
    db, storage, docs, ids = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)

        widget.filter_edit.setText("beta")
        assert _visible_count(widget) == 1

        widget.filter_edit.setText("телеграмма")
        assert _visible_count(widget) == 1

        widget.filter_edit.setText("М-1")
        assert _visible_count(widget) == 1

        widget.filter_edit.setText("15.04.2026")
        assert _visible_count(widget) == 1

        widget.filter_edit.setText("филиал 1")
        assert _visible_count(widget) == 2

        # Спецсимволы regex воспринимаются буквально и не ломают поиск
        widget.filter_edit.setText("[")
        assert _visible_count(widget) == 0

        widget.filter_edit.setText("")
        assert _visible_count(widget) == 2


def test_imported_files_missing_file_marked(qt_app, env) -> None:
    """Отсутствующий файл остаётся в таблице с зачёркнутым шрифтом."""
    db, storage, docs, ids = env
    (docs / "beta.txt").unlink()
    try:
        with db.get_session() as session:
            widget = ImportedFilesWidget(session, storage)
            row = _rows(widget)[1]
            assert row.filename == "beta.txt"
            assert row.missing
            index = widget.table_model.index(1, 0)
            assert widget.table_model.data(index, Qt.FontRole).strikeOut()
            assert widget.table_model.data(index, Qt.ForegroundRole) is not None
    finally:
        (docs / "beta.txt").write_text("b", encoding="utf-8")


def test_imported_files_drag_mime_contains_file_url(qt_app, env) -> None:
    """Перетаскивание наружу отдаёт URL файла (проводник скопирует файл)."""
    db, storage, docs, ids = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        mime = widget.table_model.mimeData(
            [widget.table_model.index(0, 0), widget.table_model.index(0, 1)]
        )
        assert mime.hasUrls()
        assert len(mime.urls()) == 1  # колонки одной строки не дублируются
        assert Path(mime.urls()[0].toLocalFile()) == docs / "alpha.txt"


def test_imported_files_rename_updates_disk_and_db(qt_app, env, monkeypatch) -> None:
    """Переименование меняет файл на диске и запись БД; манифест не меняется."""
    db, storage, docs, ids = env
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        monkeypatch.setattr(
            QInputDialog,
            "getText",
            staticmethod(lambda *args, **kwargs: ("gamma.txt", True)),
        )
        widget._rename_row(_rows(widget)[0])

        assert (docs / "gamma.txt").exists()
        assert not (docs / "alpha.txt").exists()
        # Манифест по-прежнему хранит те же первичные ключи
        assert read_import_manifest(storage) == [ids["beta"], ids["alpha"]]
        record = session.get(FileRecord, uuid.UUID(ids["alpha"]))
        assert (record.name, record.extension) == ("gamma", "txt")
        assert [row.filename for row in _rows(widget)] == [
            "beta.txt",
            "gamma.txt",
        ]


def test_imported_files_delete_removes_disk_and_manifest(
    qt_app, env, monkeypatch
) -> None:
    """Удаление убирает файлы с диска и записи из манифеста."""
    db, storage, docs, ids = env
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.Yes),
    )
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        widget._delete_rows(_rows(widget))
        assert not (docs / "alpha.txt").exists()
        assert not (docs / "beta.txt").exists()
        assert read_import_manifest(storage) == []
        assert _rows(widget) == []
        assert widget.stack.currentWidget() is widget.empty_label


def test_imported_files_empty_manifest_shows_placeholder(qt_app, env) -> None:
    """Пустой манифест показывает заглушку вместо таблицы."""
    db, storage, docs, ids = env
    write_import_manifest(storage, [])
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        assert _rows(widget) == []
        assert widget.stack.currentWidget() is widget.empty_label


def test_imported_files_legacy_manifest_paths_ignored(qt_app, env) -> None:
    """Записи манифеста старого формата (пути) не отображаются."""
    db, storage, docs, ids = env
    write_import_manifest(storage, ["Файлы/Документы/beta.txt"])
    with db.get_session() as session:
        widget = ImportedFilesWidget(session, storage)
        assert _rows(widget) == []
        assert widget.stack.currentWidget() is widget.empty_label


def test_dashboard_includes_imported_files_only_for_head_office(qt_app, env) -> None:
    """Блок файлов импорта есть только у дашборда головного офиса."""
    from internal_correspondence.gui.dashboard_widget import DashboardWidget

    db, storage, docs, ids = env
    with db.get_session() as session:
        dashboard = DashboardWidget(
            session,
            Role.HEAD_OFFICE.value,
            None,
            storage_root=storage,
        )
        assert dashboard.imported_files is not None
        assert _rows(dashboard.imported_files) != []

        branch_dashboard = DashboardWidget(
            session,
            Role.BRANCH.value,
            "F1",
            storage_root=storage,
        )
        assert branch_dashboard.imported_files is None
