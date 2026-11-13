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
