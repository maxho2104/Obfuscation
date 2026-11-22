"""Тесты окна просмотра журналов импорта оценок."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QAbstractItemView

from internal_correspondence.gui.evaluation_lists_dialog import EvaluationListsDialog
from internal_correspondence.text_import import repository
from internal_correspondence.utils.string_resources import STRINGS


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _dialog(tmp_path: Path) -> EvaluationListsDialog:
    engine = create_engine(f"sqlite:///{tmp_path / 'lists.sqlite'}")
    repository.ensure_schema(engine)
    session = Session(engine)
    log_id = repository.create_log(
        session,
        {
            "year": 2026,
            "doc_no": "42",
            "doc_date": date(2026, 11, 14),
            "file_name": "data.txt",
            "file_hash": "a" * 64,
            "scheme_name": "Оценочные данные",
            "matched_rule": "auto",
            "status": "committed",
        },
    )
    repository.insert_rows(
        session,
        [
            {
                "year": 2026,
                "import_id": log_id,
                "source_row_no": 1,
                "raw_line": "matched row",
                "data": {},
                "status": "matched",
                "error": None,
                "branch_code": "11-1-11",
                "outgoing_no": "154/23",
                "year_month": "202611",
                "value_code": "П",
                "evaluation_date": date(2026, 11, 14),
                "matched_entity_type": "material",
                "matched_entity_id": None,
                "created_at": datetime(2026, 11, 14, 10, 0),
            },
            {
                "year": 2026,
                "import_id": log_id,
                "source_row_no": 2,
                "raw_line": "unmatched row",
                "data": {},
                "status": "unmatched",
                "error": "document_not_found",
                "branch_code": "11-1-11",
                "outgoing_no": "404/23",
                "year_month": "202611",
                "value_code": "И",
                "evaluation_date": date(2026, 11, 14),
                "matched_entity_type": None,
                "matched_entity_id": None,
                "created_at": datetime(2026, 11, 14, 10, 0),
            },
            {
                "year": 2026,
                "import_id": log_id,
                "source_row_no": 3,
                "raw_line": "rejected row",
                "data": {},
                "status": "rejected",
                "error": "rejected by operator",
                "branch_code": "11-1-11",
                "outgoing_no": "155/23",
                "year_month": "202611",
                "value_code": "Б",
                "evaluation_date": date(2026, 11, 14),
                "matched_entity_type": "material",
                "matched_entity_id": None,
                "created_at": datetime(2026, 11, 14, 10, 0),
            },
        ],
    )
    session.commit()
    session.close()
    return EvaluationListsDialog(engine)


def test_dialog_shows_logs_and_rows(app, tmp_path: Path) -> None:
    dialog = _dialog(tmp_path)
    try:
        assert dialog.logs_table.rowCount() == 1
        assert dialog.logs_table.columnCount() == 3
        assert dialog.logs_table.item(0, 0).text() == "1"
        assert "42 от 14.11.2026" in dialog.logs_table.item(0, 2).text()

        assert dialog.rows_table.rowCount() == 3
        assert dialog.rows_table.item(0, 6).text() == STRINGS.evaluation_lists_status_matched
        assert dialog.rows_table.item(1, 6).text() == STRINGS.evaluation_lists_status_unmatched
        assert dialog.rows_table.item(2, 6).text() == STRINGS.evaluation_lists_status_rejected
        assert dialog.rows_table.item(0, 7).text() == "Научный материал"
        assert dialog.rows_table.item(1, 8).text() == "Документ не найден"
        assert dialog.rows_table.item(0, 4).text() == "П"
        assert dialog.rows_table.item(0, 3).text() == "11.2026"
    finally:
        dialog.close()


def test_dialog_rows_are_read_only_and_colored(app, tmp_path: Path) -> None:
    dialog = _dialog(tmp_path)
    try:
        assert dialog.rows_table.editTriggers() == QAbstractItemView.NoEditTriggers
        assert dialog.logs_table.editTriggers() == QAbstractItemView.NoEditTriggers
        colors = [
            dialog.rows_table.item(row, 0).background().color().name().upper()
            for row in range(3)
        ]
        assert colors[0] == "#D9EAD3"
        assert colors[1] == "#F4CCCC"
        assert colors[2] == "#FCE5CD"
        assert dialog.close_button.text() == STRINGS.import_close
    finally:
        dialog.close()
