"""Дымовые тесты GUI импорта оценок."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QDialog

from internal_correspondence.gui.evaluation_import_dialog import (
    EvaluationImportDialog,
    RowEditDialog,
    RulesViewerDialog,
    SchemeEditorDialog,
)
from internal_correspondence.orm.base import Base
from internal_correspondence.text_import import ImporterConfig
from internal_correspondence.text_import.models import (
    FieldSpec,
    ImportCounts,
    ImportResult,
    LayoutScheme,
    MatchPreview,
    MatchResult,
    ParsedRow,
)
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
        assert len(dialog.schemes) >= 1
        assert dialog.next_button.isEnabled() is False
    finally:
        dialog.importer.close()
        dialog.close()


def test_dialog_auto_detects_project_scheme_by_length(app, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    dialog = EvaluationImportDialog(_config(tmp_path), engine)
    try:
        row = list(" " * 139)
        for start, value in (
            (1, "11"), (4, "1"), (6, "11"), (21, "0000012345678"),
            (86, "П"), (90, "1"), (97, "21.12.2025"), (108, "122025"),
        ):
            row[start - 1 : start - 1 + len(value)] = value
        path = tmp_path / "data.txt"
        path.write_text("".join(row) + "\n", encoding="utf-8")
        dialog.file_edit.setText(str(path))
        dialog.doc_no_edit.setText("DOC-1")
        assert dialog._load_selected_file()
        assert dialog.importer.scheme is not None
        assert dialog.importer.scheme.name == "Оценочные данные"
        dialog._go_next()
        assert dialog.stack.currentIndex() == 1
        assert dialog.importer.report is not None
        assert dialog.importer.report.problem_count == 0
        dialog._go_next()
        assert dialog.stack.currentIndex() == 2
        assert dialog.matches_table.rowCount() == 1
    finally:
        dialog.importer.close()
        dialog.close()


def test_choose_file_updates_scheme_label(app, tmp_path: Path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    dialog = EvaluationImportDialog(_config(tmp_path), engine)
    try:
        row = list(" " * 139)
        for start, value in (
            (1, "11"), (4, "1"), (6, "11"), (21, "0000012345678"),
            (86, "П"), (90, "1"), (97, "21.12.2025"), (108, "122025"),
        ):
            row[start - 1 : start - 1 + len(value)] = value
        path = tmp_path / "data.txt"
        path.write_text("".join(row) + "\n", encoding="utf-8")
        monkeypatch.setattr(
            "internal_correspondence.gui.evaluation_import_dialog.QFileDialog.getOpenFileName",
            lambda *args, **kwargs: (str(path), ""),
        )
        dialog._choose_file()
        assert dialog.importer.scheme is not None
        assert "Оценочные данные" in dialog.scheme_label.text()
        assert dialog.next_button.isEnabled() is True
    finally:
        dialog.importer.close()
        dialog.close()


def test_dialog_geometry_is_40_percent_and_centered(app, tmp_path: Path) -> None:
    from PyQt5.QtWidgets import QApplication

    screen = QApplication.primaryScreen()
    if screen is None:
        pytest.skip("нет экрана")
    available = screen.availableGeometry()
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    dialog = EvaluationImportDialog(_config(tmp_path), engine)
    try:
        assert abs(dialog.width() - int(available.width() * 0.4)) <= 5
        assert abs(dialog.height() - int(available.height() * 0.4)) <= 5
        assert abs(dialog.frameGeometry().center().x() - available.center().x()) <= 5
        assert abs(dialog.frameGeometry().center().y() - available.center().y()) <= 5
    finally:
        dialog.importer.close()
        dialog.close()


def test_match_table_shows_existing_evaluation_code(app, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    dialog = EvaluationImportDialog(_config(tmp_path), engine)
    try:
        row = ParsedRow(row_no=2, raw="line", data={"outgoing_no": "154/23"})
        result = MatchResult(
            row=row,
            matched=True,
            entity_type="material",
            entity_id="00000000-0000-0000-0000-000000000001",
            value_code="В",
            duplicate=True,
            existing_value="П",
        )
        dialog._fill_matches(MatchPreview(results=[result], total=1))
        header = dialog.matches_table.horizontalHeaderItem(4).text()
        assert header == STRINGS.import_evaluation_presence
        assert dialog.matches_table.item(0, 4).text() == "П"
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
            button.text() == "Загрузить"
            for button in dialog.findChildren(type(dialog.next_button))
        )
        dialog.file_edit.setText(str(path))
        assert dialog.next_button.isEnabled()
        assert dialog._load_selected_file()
        dialog.importer.set_scheme(scheme)
        dialog.doc_no_edit.setText("123")
        dialog._validate()

        assert dialog.preview_table.columnCount() == len(scheme.fields)
        assert dialog.preview_table.horizontalHeaderItem(0).text() == "branch_part_1"
        assert dialog.preview_table.rowCount() == 2
        assert dialog.preview_table.item(0, 6).text() == "99.99.2026"

        corrected = _fixed_line(scheme, values)

        class _FakeRowEditDialog:
            """Подменяет широкий редактор строки: сразу возвращает исправленный текст."""

            def __init__(self, text, scheme, row_no, parent=None, problem="") -> None:
                self.text = corrected

            def exec_(self) -> int:
                return QDialog.Accepted

            def line_text(self) -> str:
                return self.text

            def deleteLater(self) -> None:
                pass

        monkeypatch.setattr(
            "internal_correspondence.gui.evaluation_import_dialog.RowEditDialog",
            _FakeRowEditDialog,
        )
        dialog.problems_table.setCurrentCell(0, 0)
        dialog._correct_row()
        assert dialog.preview_table.item(0, 6).text() == "01.02.2026"
    finally:
        dialog.importer.close()
        dialog.close()


def _success_result(dry_run: bool = False) -> ImportResult:
    return ImportResult(
        log_id=0 if dry_run else 7,
        year=2026,
        counts=ImportCounts(imported=2, matched=2, evaluations_received=2),
        dry_run=dry_run,
    )


def _dialog_at(tmp_path: Path, index: int, result) -> EvaluationImportDialog:
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    Base.metadata.create_all(engine)
    dialog = EvaluationImportDialog(_config(tmp_path), engine)
    dialog._result = result
    dialog.stack.setCurrentIndex(index)
    return dialog


def test_row_edit_dialog_shows_whole_line_and_fields(app) -> None:
    scheme = _wide_scheme()
    line = _long_line()
    dialog = RowEditDialog(line, scheme, 30)
    try:
        assert dialog.windowTitle() == STRINGS.import_correct_title
        assert dialog.line_text() == line
        assert dialog.fields_table.rowCount() == len(scheme.fields)
        assert dialog.fields_table.item(0, 2).text() == "11"
        assert dialog.fields_table.item(len(scheme.fields) - 1, 2).text() == "442501.27"
        assert dialog.length_label.text() == STRINGS.import_correct_length.format(
            actual=len(line), expected=139
        )
        dialog.show()
        app.processEvents()
        # Строка не переносится никогда: её видно целиком либо по ширине окна,
        # либо горизонтальной прокруткой — обрезанного текста не бывает.
        assert dialog.editor.lineWrapMode() == dialog.editor.NoWrap
        metrics = dialog.editor.fontMetrics()
        needed = metrics.horizontalAdvance("0") * len(line) + 120
        screen = app.primaryScreen()
        limit = screen.availableGeometry().width() - 80
        assert dialog.width() == max(760, min(needed, limit))
        reachable = dialog.editor.viewport().width() + dialog.editor.horizontalScrollBar().maximum()
        assert reachable >= min(needed - 60, limit - 60)
        assert dialog.line_text() == line
    finally:
        dialog.close()


def test_row_edit_dialog_marks_length_mismatch(app) -> None:
    scheme = _wide_scheme()
    short = _long_line()[:120]
    dialog = RowEditDialog(short, scheme, 7)
    try:
        dialog.show()
        app.processEvents()
        assert "120" in dialog.length_label.text() and "139" in dialog.length_label.text()
        assert "#C2414D" in dialog.length_label.styleSheet()
        statuses = [
            dialog.fields_table.item(row, 3).text()
            for row in range(dialog.fields_table.rowCount())
        ]
        assert any(status == STRINGS.import_problem_line_length for status in statuses)
        dialog.editor.setPlainText(short + " " * 19)
        app.processEvents()
        assert "139" in dialog.length_label.text()
        assert dialog.line_text() == short + " " * 19
    finally:
        dialog.close()


def test_row_edit_dialog_splits_delimited_scheme(app) -> None:
    scheme = LayoutScheme(
        name="delimited",
        mode="delimited",
        delimiter=";",
        fields=[FieldSpec("a"), FieldSpec("b"), FieldSpec("c")],
    )
    dialog = RowEditDialog("1;2;3", scheme, 2)
    try:
        dialog.show()
        app.processEvents()
        assert dialog.fields_table.rowCount() == 3
        assert [dialog.fields_table.item(row, 2).text() for row in range(3)] == ["1", "2", "3"]
        assert [dialog.fields_table.item(row, 1).text() for row in range(3)] == ["1", "2", "3"]
        assert not dialog._ruler.isVisible()
        dialog.editor.setPlainText("1;2")
        app.processEvents()
        assert dialog.fields_table.item(2, 2).text() == ""
    finally:
        dialog.close()


def test_row_edit_dialog_keeps_first_line_only(app) -> None:
    scheme = _wide_scheme()
    dialog = RowEditDialog(_long_line(), scheme, 3)
    try:
        dialog.editor.setPlainText(_long_line() + "\nвторая")
        assert "\n" not in dialog.line_text()
        assert dialog.line_text() == _long_line()
    finally:
        dialog.close()


def _wide_scheme() -> LayoutScheme:
    return LayoutScheme(
        name="evaluation_fixed",
        mode="fixed",
        header_mode="none",
        record_length=139,
        fields=[
            FieldSpec("branch_part_1", "string", start=1, length=2),
            FieldSpec("branch_part_2", "string", start=4, length=1),
            FieldSpec("branch_part_3", "string", start=6, length=2),
            FieldSpec("source_type", "string", start=17, length=1),
            FieldSpec("material_type", "string", start=19, length=1),
            FieldSpec("outgoing_no", "string", start=21, length=13),
            FieldSpec("task_code", "string", start=69, length=12),
            FieldSpec("country", "string", start=82, length=3),
            FieldSpec("value", "string", start=86, length=3),
            FieldSpec("quantity", "integer", start=90, length=1),
            FieldSpec("evaluation_date", "date", start=97, length=10, date_format="DD.MM.YYYY"),
            FieldSpec("year_month", "string", start=108, length=6),
            FieldSpec("group", "string", start=115, length=1),
            FieldSpec("collection", "string", start=117, length=3),
            FieldSpec("costs", "number", start=131, length=9),
        ],
    )


def _long_line() -> str:
    return (
        "11 1 12         Н С ИСХ-00070                                       "
        "TASK-0002        И   9      23.02.2026 202602 1               442501.27"
    )


def test_close_after_successful_import_requests_lists(app, tmp_path: Path) -> None:
    dialog = _dialog_at(tmp_path, 3, _success_result())
    try:
        assert dialog.shows_evaluation_lists() is False
        dialog._on_close()
        assert dialog.result() == QDialog.Accepted
        assert dialog.shows_evaluation_lists() is True
    finally:
        dialog.importer.close()
        dialog.close()


def test_close_without_import_stays_rejected(app, tmp_path: Path) -> None:
    dialog = _dialog_at(tmp_path, 0, None)
    try:
        dialog._on_close()
        assert dialog.result() == QDialog.Rejected
        assert dialog.shows_evaluation_lists() is False
    finally:
        dialog.importer.close()
        dialog.close()


def test_close_after_dry_run_stays_rejected(app, tmp_path: Path) -> None:
    dialog = _dialog_at(tmp_path, 3, _success_result(dry_run=True))
    try:
        dialog._on_close()
        assert dialog.result() == QDialog.Rejected
        assert dialog.shows_evaluation_lists() is False
    finally:
        dialog.importer.close()
        dialog.close()


def test_close_on_earlier_step_stays_rejected(app, tmp_path: Path) -> None:
    dialog = _dialog_at(tmp_path, 2, _success_result())
    try:
        dialog._on_close()
        assert dialog.result() == QDialog.Rejected
        assert dialog.shows_evaluation_lists() is False
    finally:
        dialog.importer.close()
        dialog.close()
