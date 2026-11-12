"""Тесты модели таблиц документов: фильтр филиала и выделение строк."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.constants import MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.table_model import ColumnDef, DocumentsTableModel
from internal_correspondence.gui.theme import current_theme
from internal_correspondence.orm.models import Branch, ScientificMaterial, TerritorialUnit


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'documents_model.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="function")
def documents(db_manager):
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="TU", name="Единица"))
        session.add(Branch(id="F1", name="Филиал 1", short_name="Ф1", territorial_unit_id="TU"))
        session.add(Branch(id="F2", name="Филиал 2", short_name="Ф2", territorial_unit_id="TU"))
        first = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-1",
            outgoing_date=date(2026, 1, 1),
            name="С входящим",
            branch_id="F1",
            incoming_number="В-1",
            incoming_date=date(2026, 2, 1),
        )
        second = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-2",
            outgoing_date=date(2026, 1, 2),
            name="Без входящего",
            branch_id="F1",
        )
        third = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-3",
            outgoing_date=date(2026, 1, 3),
            name="Другой филиал",
            branch_id="F2",
        )
        session.add_all([first, second, third])
        session.commit()
    return db_manager


COLUMNS = [ColumnDef("outgoing_number"), ColumnDef("name")]


def test_branch_filter_limits_rows(documents, qapp) -> None:
    """Для роли «филиал» модель показывает только строки этого филиала."""
    with documents.get_session() as session:
        model = DocumentsTableModel(session, ScientificMaterial, COLUMNS, branch_id="F1")
        assert model.total() == 2
        assert {item.branch_id for item in model._items} == {"F1"}

        model_all = DocumentsTableModel(session, ScientificMaterial, COLUMNS)
        assert model_all.total() == 3


def test_rows_without_incoming_number_highlighted(documents, qapp) -> None:
    """Записи без входящего номера выделяются цветом темы (мягче изменённых)."""
    with documents.get_session() as session:
        # Сбрасываем неэкспортированные изменения (пакетно, без ORM-событий) —
        # иначе сработает глобальный change-tracking и цвет будет «изменённый»
        session.query(ScientificMaterial).update(
            {ScientificMaterial.change_id: None}, synchronize_session=False
        )
        session.commit()

        model = DocumentsTableModel(session, ScientificMaterial, COLUMNS, branch_id="F1")
        theme = current_theme()

        without_incoming_row = next(
            row
            for row in range(model.rowCount())
            if model.item_at(row).incoming_number is None
        )
        with_incoming_row = next(
            row
            for row in range(model.rowCount())
            if model.item_at(row).incoming_number is not None
        )

        color = model.index(without_incoming_row, 0).data(Qt.BackgroundRole)
        assert color is not None
        assert color == theme.no_incoming_row
        assert theme.no_incoming_row != theme.modified_row

        assert model.index(with_incoming_row, 0).data(Qt.BackgroundRole) is None


def test_modified_row_highlight_takes_priority(documents, qapp) -> None:
    """Неэкспортированные изменения выделяются ярче, чем отсутствие входящего."""
    from internal_correspondence.orm.models import Change

    with documents.get_session() as session:
        # Запись без входящего номера и с неэкспортированным изменением
        material = (
            session.query(ScientificMaterial)
            .filter_by(outgoing_number="М-2")
            .one()
        )
        change = Change(
            entity_name="ScientificMaterial",
            entity_pk=str(material.id),
            changed_fields=["comment"],
            operation_type=1,
        )
        session.add(change)
        session.flush()
        material.change_id = change.id
        session.commit()

        model = DocumentsTableModel(session, ScientificMaterial, COLUMNS, branch_id="F1")
        theme = current_theme()
        changed_row = next(
            row
            for row in range(model.rowCount())
            if model.item_at(row).change_id is not None
        )
        color = model.index(changed_row, 0).data(Qt.BackgroundRole)
        assert color == theme.modified_row
