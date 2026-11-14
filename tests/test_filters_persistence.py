"""Тесты сохранения фильтров и обеспечения видимости записи."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.constants import MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.filter_model import (
    FilterCondition,
    deserialize_filters,
    serialize_filters,
)
from internal_correspondence.gui.table_model import ColumnDef, DocumentsTableModel
from internal_correspondence.orm.models import Branch, ScientificMaterial, TerritorialUnit


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'filters.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="function")
def documents(db_manager):
    with db_manager.get_session() as session:
        session.add(TerritorialUnit(id="TU", name="Единица"))
        session.add(Branch(id="F1", name="Филиал 1", short_name="Ф1", territorial_unit_id="TU"))
        for index in range(1, 6):
            session.add(
                ScientificMaterial(
                    type=MaterialType.MESSAGE,
                    outgoing_number=f"М-{index}",
                    outgoing_date=date(2026, 1, index),
                    name=f"Материал {index}",
                    branch_id="F1",
                )
            )
        session.commit()
    return db_manager


COLUMNS = [ColumnDef("outgoing_number"), ColumnDef("name")]


def test_filters_serialize_roundtrip(documents) -> None:
    """Список условий сохраняется и восстанавливается без потерь."""
    filters = [
        FilterCondition("outgoing_number", "contains", "М-1"),
        FilterCondition("outgoing_date", "ge", "2026-01-03"),
    ]
    raw = serialize_filters(filters)
    restored = deserialize_filters(raw, ScientificMaterial)
    assert restored == filters


def test_deserialize_tolerates_garbage(documents) -> None:
    """Битые и устаревшие сохранённые фильтры отбрасываются без ошибок."""
    assert deserialize_filters("", ScientificMaterial) == []
    assert deserialize_filters("не-json", ScientificMaterial) == []
    assert deserialize_filters('{"a": 1}', ScientificMaterial) == []
    assert deserialize_filters(
        '[{"column": "unknown_column", "operator": "eq", "value": "x"},'
        ' {"column": "name", "operator": "bad-op", "value": "x"},'
        ' {"column": "name", "operator": "contains", "value": "x"}]',
        ScientificMaterial,
    ) == [FilterCondition("name", "contains", "x")]


def test_page_of_finds_record_page(documents, qapp) -> None:
    """Страница записи вычисляется с учётом пагинации и сортировки."""
    with documents.get_session() as session:
        model = DocumentsTableModel(session, ScientificMaterial, COLUMNS, branch_id="F1")
        model._page_size = 2
        keys = {item.outgoing_number: model.pk_of(item) for item in model._items}
        # Все записи: переходим на страницу с «М-4» (сортировка по умолчанию БД)
        all_model = DocumentsTableModel(session, ScientificMaterial, COLUMNS, branch_id="F1")
        all_model._page_size = 2
        material = (
            session.query(ScientificMaterial)
            .filter_by(outgoing_number="М-4")
            .one()
        )
        page = all_model.page_of(all_model.pk_of(material))
        assert page is not None
        assert all_model.set_page(page) is None
        assert all_model.row_of(all_model.pk_of(material)) is not None


def test_page_of_none_when_filtered_out(documents, qapp) -> None:
    """Запись вне выборки по фильтру не имеет страницы."""
    with documents.get_session() as session:
        model = DocumentsTableModel(session, ScientificMaterial, COLUMNS, branch_id="F1")
        model.set_filters([FilterCondition("outgoing_number", "contains", "М-1")])
        other = (
            session.query(ScientificMaterial)
            .filter_by(outgoing_number="М-3")
            .one()
        )
        assert model.page_of(model.pk_of(other)) is None
        target = (
            session.query(ScientificMaterial)
            .filter_by(outgoing_number="М-1")
            .one()
        )
        assert model.page_of(model.pk_of(target)) is not None
