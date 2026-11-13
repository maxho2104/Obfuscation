"""Диалог импорта оценок из текстового файла."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.text_import import Importer, ImporterConfig
from internal_correspondence.text_import.errors import ImporterError
from internal_correspondence.text_import.models import LayoutScheme, MatchRule
from internal_correspondence.text_import.scheme import load_schemes
from internal_correspondence.utils.string_resources import STRINGS


class EvaluationImportDialog(QDialog):
    """Мастер: файл → проверка строк → сопоставление → результат."""

    def __init__(self, config: ImporterConfig, engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.dialog_import_evaluations_title)
        self.resize(1000, 720)
        self.setAcceptDrops(True)
        self.config = config
        self.importer = Importer(config, engine)
        self._duplicate_actions: Dict[int, str] = {}
        self._result = None
        self._build_ui()
        self._load_lists()
        self._update_nav()

    # -- построение ---------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.step_label = QLabel()
        layout.addWidget(self.step_label)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_file_page())
        self.stack.addWidget(self._build_check_page())
        self.stack.addWidget(self._build_match_page())
        self.stack.addWidget(self._build_result_page())

        nav = QHBoxLayout()
        self.back_button = QPushButton(STRINGS.import_back)
        self.back_button.clicked.connect(self._go_back)
        self.next_button = QPushButton(STRINGS.import_next)
        self.next_button.clicked.connect(self._go_next)
        close_button = QPushButton(STRINGS.import_close)
        close_button.clicked.connect(self.reject)
        nav.addWidget(self.back_button)
        nav.addStretch(1)
        nav.addWidget(close_button)
        nav.addWidget(self.next_button)
        layout.addLayout(nav)

    def _build_file_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        browse = QPushButton(STRINGS.import_choose_file)
        browse.clicked.connect(self._choose_file)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(browse)
        form.addRow(STRINGS.import_file_label, file_row)
        hint = QLabel(STRINGS.import_drop_hint)
        hint.setWordWrap(True)
        form.addRow("", hint)
        self.doc_no_edit = QLineEdit()
        form.addRow(STRINGS.import_doc_no, self.doc_no_edit)
        self.doc_date_edit = QDateEdit(QDate.currentDate())
        self.doc_date_edit.setCalendarPopup(True)
        self.doc_date_edit.setDisplayFormat("dd.MM.yyyy")
        form.addRow(STRINGS.import_doc_date, self.doc_date_edit)
        scheme_row = QHBoxLayout()
        self.scheme_combo = QComboBox()
        self.scheme_combo.currentIndexChanged.connect(lambda _: self._on_scheme_changed())
        edit_scheme = QPushButton(STRINGS.import_scheme_editor)
        edit_scheme.clicked.connect(self._edit_scheme)
        scheme_row.addWidget(self.scheme_combo, 1)
        scheme_row.addWidget(edit_scheme)
        form.addRow(STRINGS.import_scheme, scheme_row)
        self.rule_combo = QComboBox()
        form.addRow(STRINGS.import_rule, self.rule_combo)
        load = QPushButton(STRINGS.import_load)
        load.clicked.connect(self._load_selected_file)
        form.addRow("", load)
        return page

    def _build_check_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        top = QHBoxLayout()
        top.addWidget(QLabel(STRINGS.import_encoding))
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItem(STRINGS.import_encoding_auto, None)
        for name in ("utf-8", "utf-8-sig", "cp1251", "cp866", "utf-16"):
            self.encoding_combo.addItem(name, name)
        self.encoding_combo.currentIndexChanged.connect(lambda _: self._reload_encoding())
        top.addWidget(self.encoding_combo)
        top.addStretch(1)
        validate = QPushButton(STRINGS.import_validate)
        validate.clicked.connect(self._validate)
        top.addWidget(validate)
        layout.addLayout(top)
        layout.addWidget(QLabel(STRINGS.import_preview))
        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setMaximumHeight(180)
        layout.addWidget(self.preview_edit)
        layout.addWidget(QLabel(STRINGS.import_problems))
        self.problems_table = QTableWidget(0, 3)
        self.problems_table.setHorizontalHeaderLabels(
            ["№", STRINGS.import_match_status, STRINGS.import_match_reason]
        )
        self.problems_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.problems_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.problems_table, 1)
        buttons = QHBoxLayout()
        correct = QPushButton(STRINGS.import_correct)
        correct.clicked.connect(self._correct_row)
        reject = QPushButton(STRINGS.import_reject)
        reject.clicked.connect(self._reject_row)
        unreject = QPushButton(STRINGS.import_unreject)
        unreject.clicked.connect(self._unreject_row)
        buttons.addWidget(correct)
        buttons.addWidget(reject)
        buttons.addWidget(unreject)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _build_match_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.match_counts = QLabel()
        layout.addWidget(self.match_counts)
        self.matches_table = QTableWidget(0, 5)
        self.matches_table.setHorizontalHeaderLabels(
            [
                "№",
                STRINGS.import_match_status,
                STRINGS.import_match_reason,
                STRINGS.label_evaluation_value,
                STRINGS.import_duplicate_eval,
            ]
        )
        self.matches_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.matches_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.matches_table, 1)
        buttons = QHBoxLayout()
        preview = QPushButton(STRINGS.import_validate)
        preview.clicked.connect(self._preview)
        dry = QPushButton(STRINGS.import_dry_run)
        dry.clicked.connect(lambda: self._do_import(dry_run=True))
        run = QPushButton(STRINGS.import_import)
        run.clicked.connect(lambda: self._do_import(dry_run=False))
        buttons.addWidget(preview)
        buttons.addStretch(1)
        buttons.addWidget(dry)
        buttons.addWidget(run)
        layout.addLayout(buttons)
        return page

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        self.result_details = QPlainTextEdit()
        self.result_details.setReadOnly(True)
        layout.addWidget(self.result_details, 1)
        buttons = QHBoxLayout()
        open_log = QPushButton(STRINGS.import_open_log)
        open_log.clicked.connect(self._open_log)
        buttons.addWidget(open_log)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    # -- списки схем/правил -------------------------------------------------
    def _load_lists(self) -> None:
        self.scheme_combo.clear()
        try:
            schemes = load_schemes(self.config.schemes_dir)
        except Exception as exc:  # noqa: BLE001
            schemes = []
            self._show_error(exc)
        for scheme in schemes:
            self.scheme_combo.addItem(scheme.name, scheme)
        if not schemes:
            self.scheme_combo.addItem(STRINGS.import_no_schemes, None)
        self.rule_combo.clear()
        try:
            rules = self.importer.load_rules()
        except Exception as exc:  # noqa: BLE001
            self.rule_combo.addItem(STRINGS.import_no_rules, None)
            self._show_error(exc)
            return
        for rule in rules.rules:
            self.rule_combo.addItem(rule.name, rule)

    def _on_scheme_changed(self) -> None:
        self._update_nav()

    # -- файл ---------------------------------------------------------------
    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            STRINGS.import_choose_file,
            "",
            STRINGS.import_file_filter,
        )
        if path:
            self.file_edit.setText(path)
            self._load_selected_file()

    def _load_selected_file(self) -> None:
        path = self.file_edit.text().strip()
        if not path:
            self._choose_file()
            return
        try:
            info = self.importer.load_file(path, self.encoding_combo.currentData())
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return
        self.file_edit.setText(str(info.path))
        self.preview_edit.setPlainText("\n".join(info.lines[: self.config.preview_lines]))
        matches = self.importer.detect_schemes()
        matched = [item for item in matches if item.matched]
        if matched:
            index = self.scheme_combo.findText(matched[0].scheme.name)
            if index >= 0:
                self.scheme_combo.setCurrentIndex(index)
        self._update_nav()

    def _reload_encoding(self) -> None:
        if self.file_edit.text().strip():
            self._load_selected_file()

    # -- проверка -----------------------------------------------------------
    def _current_scheme(self) -> Optional[LayoutScheme]:
        data = self.scheme_combo.currentData()
        return data if isinstance(data, LayoutScheme) else None

    def _current_rule(self) -> Optional[MatchRule]:
        data = self.rule_combo.currentData()
        return data if isinstance(data, MatchRule) else None

    def _validate(self) -> None:
        scheme = self._current_scheme()
        if scheme is None:
            self._show_error(ImporterError("scheme_not_selected", STRINGS.import_select_scheme))
            return
        if not self.doc_no_edit.text().strip():
            self._show_error(ImporterError("document_not_set", STRINGS.import_doc_no))
            return
        try:
            self.importer.set_scheme(scheme)
            self.importer.set_document(
                self.doc_no_edit.text().strip(), self.doc_date_edit.date().toPyDate()
            )
            report = self.importer.validate()
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return
        self._fill_problems()
        self.match_counts.setText(
            STRINGS.import_counts.format(
                total=report.total_lines,
                matched=0,
                unmatched=0,
                skipped=0,
                rejected=report.problem_count,
            )
        )
        self._update_nav()

    def _fill_problems(self) -> None:
        report = self.importer.report
        self.problems_table.setRowCount(0)
        if report is None:
            return
        shown = 0
        for row in report.rows:
            if row.problem is not None:
                self._add_problem_row(row.row_no, STRINGS.import_status_error, row.problem.code)
                shown += 1
            elif row.row_no in self.importer.rejected_rows():
                self._add_problem_row(row.row_no, STRINGS.import_status_rejected, "")
                shown += 1
        if shown == 0:
            self.problems_table.setRowCount(1)
            item = QTableWidgetItem("—")
            self.problems_table.setItem(0, 0, item)
            item = QTableWidgetItem(STRINGS.import_no_errors)
            self.problems_table.setItem(0, 1, item)

    def _add_problem_row(self, row_no: int, status: str, reason: str) -> None:
        row = self.problems_table.rowCount()
        self.problems_table.insertRow(row)
        number = QTableWidgetItem(str(row_no))
        number.setData(Qt.UserRole, row_no)
        self.problems_table.setItem(row, 0, number)
        self.problems_table.setItem(row, 1, QTableWidgetItem(status))
        self.problems_table.setItem(row, 2, QTableWidgetItem(reason))

    def _selected_problem_row(self) -> Optional[int]:
        item = self.problems_table.currentItem()
        if item is None:
            return None
        number = self.problems_table.item(item.row(), 0)
        if number is None:
            return None
        value = number.data(Qt.UserRole)
        return int(value) if value is not None else None

    def _correct_row(self) -> None:
        row_no = self._selected_problem_row()
        if row_no is None:
            return
        report = self.importer.report
        if report is None:
            return
        current = next((row.raw for row in report.rows if row.row_no == row_no), "")
        text, ok = QInputDialog.getText(
            self,
            STRINGS.import_correct_title,
            STRINGS.import_correct_prompt.format(row=row_no),
            text=current,
        )
        if not ok:
            return
        try:
            self.importer.correct_row(row_no, text)
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return
        self._fill_problems()

    def _reject_row(self) -> None:
        row_no = self._selected_problem_row()
        if row_no is None:
            return
        self.importer.reject_row(row_no)
        self._fill_problems()

    def _unreject_row(self) -> None:
        row_no = self._selected_problem_row()
        if row_no is None:
            return
        self.importer.unreject_row(row_no)
        try:
            self.importer.validate()
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
        self._fill_problems()

    # -- сопоставление ------------------------------------------------------
    def _preview(self) -> None:
        rule = self._current_rule()
        if rule is None:
            self._show_error(ImporterError("rule_not_selected", STRINGS.import_select_rule))
            return
        if self.importer.report is None:
            self._validate()
            if self.importer.report is None:
                return
        try:
            self.importer.set_rule(rule)
            preview = self.importer.preview_matches()
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return
        self._fill_matches(preview)

    def _fill_matches(self, preview) -> None:
        self.matches_table.setRowCount(0)
        for result in preview.results:
            row = self.matches_table.rowCount()
            self.matches_table.insertRow(row)
            number = QTableWidgetItem(str(result.row.row_no))
            number.setData(Qt.UserRole, result.row.row_no)
            self.matches_table.setItem(row, 0, number)
            status = (
                STRINGS.import_status_matched
                if result.matched
                else STRINGS.import_status_unmatched
            )
            self.matches_table.setItem(row, 1, QTableWidgetItem(status))
            self.matches_table.setItem(row, 2, QTableWidgetItem(result.reason))
            self.matches_table.setItem(row, 3, QTableWidgetItem(result.value_code or ""))
            if result.duplicate:
                combo = QComboBox()
                combo.addItem(STRINGS.import_action_skip, "skip")
                combo.addItem(STRINGS.import_action_update, "update")
                combo.currentIndexChanged.connect(
                    lambda _, r=result.row.row_no, c=combo: self._duplicate_actions.__setitem__(
                        r, str(c.currentData())
                    )
                )
                self._duplicate_actions[result.row.row_no] = "skip"
                self.matches_table.setCellWidget(row, 4, combo)
        self.match_counts.setText(
            STRINGS.import_counts.format(
                total=preview.total,
                matched=preview.matched_count,
                unmatched=preview.unmatched_count,
                skipped=0,
                rejected=len(self.importer.rejected_rows()),
            )
        )

    # -- импорт -------------------------------------------------------------
    def _do_import(self, dry_run: bool) -> None:
        if self.importer.preview is None:
            self._preview()
        duplicate = self.importer.check_duplicate_file()
        force = False
        if duplicate is not None:
            answer = QMessageBox.question(
                self,
                STRINGS.dialog_import_evaluations_title,
                STRINGS.import_duplicate_file.format(
                    started_at=duplicate.started_at, import_id=duplicate.import_id
                )
                + "\n"
                + STRINGS.import_duplicate_question,
            )
            if answer != QMessageBox.Yes:
                return
            force = True
        try:
            result = self.importer.import_to_db(
                dry_run=dry_run,
                duplicate_actions=self._duplicate_actions,
                force_duplicate=force,
            )
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return
        self._result = result
        self._show_result(result)
        self.stack.setCurrentIndex(3)
        self._update_nav()

    def _show_result(self, result) -> None:
        self.result_label.setText(
            STRINGS.import_done.format(
                matched=result.counts.matched,
                unmatched=result.counts.unmatched,
                skipped=result.counts.skipped,
                rejected=result.counts.rejected,
                stored_path=result.stored_path or "—",
            )
        )
        lines = [
            STRINGS.import_rows_total.format(count=result.counts.imported),
            STRINGS.import_log_saved.format(log_id=result.log_id)
            if result.log_id
            else "",
        ]
        lines.extend(result.warnings)
        self.result_details.setPlainText("\n".join(item for item in lines if item))

    def _open_log(self) -> None:
        if self._result and self._result.log_id:
            QMessageBox.information(
                self,
                STRINGS.import_open_log,
                STRINGS.import_log_saved.format(log_id=self._result.log_id),
            )

    # -- навигация ----------------------------------------------------------
    def _go_back(self) -> None:
        index = self.stack.currentIndex()
        if index > 0:
            self.stack.setCurrentIndex(index - 1)
        self._update_nav()

    def _go_next(self) -> None:
        index = self.stack.currentIndex()
        if index == 0:
            if self.importer.info is None:
                self._load_selected_file()
            if self.importer.info is None:
                return
            self.stack.setCurrentIndex(1)
        elif index == 1:
            self._validate()
            if self.importer.report is None:
                return
            self.stack.setCurrentIndex(2)
            self._preview()
        self._update_nav()

    def _update_nav(self) -> None:
        index = self.stack.currentIndex()
        pages = [
            STRINGS.import_step_file,
            STRINGS.import_step_check,
            STRINGS.import_step_match,
            STRINGS.import_step_result,
        ]
        self.step_label.setText(
            f"{pages[index]} — {STRINGS.import_page_of.format(page=index + 1, pages=len(pages))}"
        )
        self.back_button.setEnabled(index > 0)
        self.next_button.setVisible(index < 2)
        self.next_button.setEnabled(
            (index == 0 and self.importer.info is not None)
            or (index == 1 and self.importer.report is not None)
        )

    # -- ошибки/файлы -------------------------------------------------------
    def _show_error(self, exc: Exception) -> None:
        code = getattr(exc, "code", "")
        detail = str(exc)
        text = STRINGS.import_error_generic.format(error=detail)
        if code:
            text = f"{code}: {detail}"
        QMessageBox.critical(self, STRINGS.import_error_title, text)

    def _edit_scheme(self) -> None:
        scheme = self._current_scheme()
        dialog = SchemeEditorDialog(self.config.schemes_dir, scheme, self)
        if dialog.exec_() == QDialog.Accepted:
            self._load_lists()
            if dialog.saved_path:
                index = self.scheme_combo.findText(dialog.saved_scheme.name if dialog.saved_scheme else "")
                if index >= 0:
                    self.scheme_combo.setCurrentIndex(index)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.is_file():
            self.file_edit.setText(str(path))
            self._load_selected_file()
            event.acceptProposedAction()


class SchemeEditorDialog(QDialog):
    """Редактор JSON-схемы разметки."""

    def __init__(
        self,
        directory: Path,
        scheme: Optional[LayoutScheme] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.directory = Path(directory)
        self.saved_path: Optional[Path] = None
        self.saved_scheme: Optional[LayoutScheme] = None
        self.setWindowTitle(STRINGS.import_scheme_editor)
        self.resize(900, 600)
        self._build_ui()
        if scheme is not None:
            self._fill(scheme)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        form.addRow(STRINGS.import_scheme_name, self.name_edit)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(STRINGS.import_scheme_mode_fixed, "fixed")
        self.mode_combo.addItem(STRINGS.import_scheme_mode_delimited, "delimited")
        form.addRow(STRINGS.import_scheme_mode, self.mode_combo)
        self.delimiter_edit = QLineEdit(";")
        form.addRow(STRINGS.import_scheme_delimiter, self.delimiter_edit)
        self.header_combo = QComboBox()
        self.header_combo.addItem(STRINGS.import_scheme_header_skip, "skip")
        self.header_combo.addItem(STRINGS.import_scheme_header_names, "names")
        self.header_combo.addItem(STRINGS.import_scheme_header_none, "none")
        form.addRow(STRINGS.import_scheme_header, self.header_combo)
        layout.addLayout(form)
        layout.addWidget(QLabel(STRINGS.import_scheme_fields))
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                STRINGS.import_field_name,
                STRINGS.import_field_type,
                STRINGS.import_field_start,
                STRINGS.import_field_length,
                STRINGS.import_field_required,
                STRINGS.import_field_date_format,
                STRINGS.import_field_regex,
                STRINGS.import_field_default,
            ]
        )
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        add = QPushButton(STRINGS.import_scheme_add_field)
        add.clicked.connect(self._add_field)
        remove = QPushButton(STRINGS.import_scheme_remove_field)
        remove.clicked.connect(self._remove_field)
        save = QPushButton(STRINGS.import_scheme_save)
        save.clicked.connect(self._save)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _add_field(self, name: str = "", values: Optional[List[str]] = None) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        type_combo = QComboBox()
        type_combo.addItems(["string", "integer", "date"])
        if values and values[0]:
            type_combo.setCurrentText(values[0])
        self.table.setCellWidget(row, 1, type_combo)
        for column, value in enumerate(values[1:] if values else [], start=2):
            self.table.setItem(row, column, QTableWidgetItem(value))
        check = QCheckBox()
        if values and len(values) > 3 and values[3] == "1":
            check.setChecked(True)
        self.table.setCellWidget(row, 4, check)

    def _remove_field(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _fill(self, scheme: LayoutScheme) -> None:
        self.name_edit.setText(scheme.name)
        index = self.mode_combo.findData(scheme.mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self.delimiter_edit.setText(scheme.delimiter)
        index = self.header_combo.findData(scheme.header_mode)
        if index >= 0:
            self.header_combo.setCurrentIndex(index)
        for field in scheme.fields:
            values = [
                field.type,
                "" if field.start is None else str(field.start),
                "" if field.length is None else str(field.length),
                "1" if field.required else "0",
                field.date_format or "",
                field.regex or "",
                field.default or "",
            ]
            self._add_field(field.name, values)

    def _build_scheme(self) -> LayoutScheme:
        from internal_correspondence.text_import.models import FieldSpec

        fields: List[FieldSpec] = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            name = name_item.text().strip() if name_item else ""
            type_widget = self.table.cellWidget(row, 1)
            field_type = type_widget.currentText() if isinstance(type_widget, QComboBox) else "string"
            start = self._int_value(row, 2)
            length = self._int_value(row, 3)
            check = self.table.cellWidget(row, 4)
            required = check.isChecked() if isinstance(check, QCheckBox) else False
            fields.append(
                FieldSpec(
                    name=name,
                    type=field_type,
                    start=start,
                    length=length,
                    required=required,
                    date_format=self._text(row, 5) or None,
                    regex=self._text(row, 6) or None,
                    default=self._text(row, 7) or None,
                )
            )
        return LayoutScheme(
            name=self.name_edit.text().strip(),
            mode=str(self.mode_combo.currentData()),
            delimiter=self.delimiter_edit.text(),
            header_mode=str(self.header_combo.currentData()),
            fields=fields,
        )

    def _text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item else ""

    def _int_value(self, row: int, column: int) -> Optional[int]:
        value = self._text(row, column)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _save(self) -> None:
        from internal_correspondence.text_import.scheme import save_scheme

        scheme = self._build_scheme()
        errors = scheme.validate()
        if errors:
            QMessageBox.warning(
                self,
                STRINGS.import_scheme_editor,
                STRINGS.import_scheme_invalid.format(errors="; ".join(errors)),
            )
            return
        try:
            self.saved_path = save_scheme(scheme, self.directory)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, STRINGS.import_error_title, str(exc))
            return
        self.saved_scheme = scheme
        QMessageBox.information(
            self,
            STRINGS.import_scheme_editor,
            STRINGS.import_scheme_saved.format(path=self.saved_path),
        )
        self.accept()


class RulesViewerDialog(QDialog):
    """Просмотр декларативных правил сопоставления."""

    def __init__(self, rules_path: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.rules_path = Path(rules_path)
        self.setWindowTitle(STRINGS.import_rules_viewer)
        self.resize(800, 400)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [
                STRINGS.import_rule_column,
                STRINGS.import_entity_column,
                STRINGS.import_table_column,
                STRINGS.import_conditions_column,
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table, 1)
        open_button = QPushButton(STRINGS.import_rules_viewer)
        open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(self.rules_path.as_uri())
            if self.rules_path.exists()
            else None
        )
        layout.addWidget(open_button)
        self._load()

    def _load(self) -> None:
        from internal_correspondence.text_import.matcher import load_rules

        try:
            rules = load_rules(self.rules_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, STRINGS.import_error_title, str(exc))
            return
        for rule in rules.rules:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(rule.name))
            self.table.setItem(row, 1, QTableWidgetItem(rule.entity))
            self.table.setItem(row, 2, QTableWidgetItem(str((rule.raw.get("lookup") or {}).get("table", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(", ".join(rule.conditions)))
