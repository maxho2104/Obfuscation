"""Дымовые тесты GUI импорта оценок."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from internal_correspondence.gui.evaluation_import_dialog import (
    EvaluationImportDialog,
    RulesViewerDialog,
    SchemeEditorDialog,
)
from internal_correspondence.orm.base import Base
from internal_correspondence.text_import import ImporterConfig
from internal_correspondence.text_import.models import FieldSpec, LayoutScheme
from internal_correspondence.utils.string_resources import STRINGS


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _config(tmp_path: Path) -> ImporterConfig:
    storage = tmp_path / "storage"
    storage.mkdir()
    root = Path(__file__).resolve().parent.parent
    return ImporterConfig(
        file_storage_dir=storage,
        schemes_dir=root / "schemes",
        matcher_rules_path=root / "matcher_rules.json",
    )


def test_dialog_opens_with_project_schemes(app, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    dialog = EvaluationImportDialog(_config(tmp_path), engine)
    try:
        assert dialog.stack.count() == 4
        assert dialog.scheme_combo.count() >= 1
        assert dialog.rule_combo.count() >= 1
        assert dialog.next_button.isEnabled() is False
    finally:
        dialog.importer.close()
        dialog.close()


def test_scheme_editor_and_rules_viewer(app, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parent.parent
    editor = SchemeEditorDialog(tmp_path / "schemes")
    editor.close()
    viewer = RulesViewerDialog(root / "matcher_rules.json")
    try:
        assert viewer.table.rowCount() >= 2
    finally:
        viewer.close()


def _fixed_line(scheme, values: dict) -> str:
    length = max(
        (item.start or 1) - 1 + len(values.get(item.name, ""))
        for item in scheme.fields
    )
    chars = [" "] * length
    for item in scheme.fields:
        value = values.get(item.name, "")
        begin = (item.start or 1) - 1
        chars[begin : begin + len(value)] = value
    return "".join(chars)


def test_preview_is_split_and_refreshes_after_correction(
    app, tmp_path: Path, monkeypatch
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    config = _config(tmp_path)
    dialog = EvaluationImportDialog(config, engine)
    try:
        scheme = LayoutScheme(
            name="evaluation_fixed",
            mode="fixed",
            header_mode="none",
            fields=[
                FieldSpec("branch_part_1", "string", start=1, length=2, required=True),
                FieldSpec("branch_part_2", "string", start=4, length=1, required=True),
                FieldSpec("branch_part_3", "string", start=6, length=2, required=True),
                FieldSpec("outgoing_no", "string", start=8, length=10, required=True),
                FieldSpec("year_month", "string", start=18, length=6, required=True),
                FieldSpec("value", "string", start=24, length=1),
                FieldSpec("evaluation_date", "date", start=25, length=10, date_format="DD.MM.YYYY"),
            ],
        )
        values = {
            "branch_part_1": " 1",
            "branch_part_2": "1",
            "branch_part_3": " 1",
            "outgoing_no": "0000000001",
            "year_month": "202601",
            "value": "П",
            "evaluation_date": "01.02.2026",
        }
        bad = dict(values, evaluation_date="99.99.2026")
        path = tmp_path / "rows.txt"
        path.write_text(
            _fixed_line(scheme, bad) + "\n" + _fixed_line(scheme, values) + "\n",
            encoding="utf-8",
        )

        assert not any(
            button.text() == STRINGS.import_load
            for button in dialog.findChildren(type(dialog.next_button))
        )
        dialog.file_edit.setText(str(path))
        assert dialog.next_button.isEnabled()
        assert dialog._load_selected_file()
        dialog.scheme_combo.clear()
        dialog.scheme_combo.addItem(scheme.name, scheme)
        dialog.doc_no_edit.setText("123")
        dialog._validate()

        assert dialog.preview_table.columnCount() == len(scheme.fields)
        assert dialog.preview_table.horizontalHeaderItem(0).text() == "branch_part_1"
        assert dialog.preview_table.rowCount() == 2
        assert dialog.preview_table.item(0, 6).text() == "99.99.2026"

        monkeypatch.setattr(
            "internal_correspondence.gui.evaluation_import_dialog.QInputDialog.getText",
            lambda *args, **kwargs: (_fixed_line(scheme, values), True),
        )
        dialog.problems_table.setCurrentCell(0, 0)
        dialog._correct_row()
        assert dialog.preview_table.item(0, 6).text() == "01.02.2026"
    finally:
        dialog.importer.close()
        dialog.close()
