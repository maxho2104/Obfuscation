"""Диалог импорта оценок из текстового файла."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QBrush, QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
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

from internal_correspondence.core.domain_pack import enum_label
from internal_correspondence.text_import import Importer, ImporterConfig
from internal_correspondence.text_import.errors import ImporterError
from internal_correspondence.text_import.models import LayoutScheme
from internal_correspondence.text_import.parsing import parse_rows, split_fields
from internal_correspondence.text_import.scheme import load_schemes
from internal_correspondence.utils.string_resources import STRINGS


class EvaluationImportDialog(QDialog):
    """Мастер: файл → проверка строк → сопоставление → результат."""

    def __init__(self, config: ImporterConfig, engine, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.dialog_import_evaluations_title)
        self.setAcceptDrops(True)
        self.config = config
        self.importer = Importer(config, engine)
        self._duplicate_actions: Dict[int, str] = {}
        self._result = None
        self._lists_requested = False
        self._build_ui()
        self._apply_initial_geometry()
        self._reload_schemes()
        self._update_nav()

    # -- построение ---------------------------------------------------------
    def shows_evaluation_lists(self) -> bool:
        """Нужно ли после закрытия мастера открыть журналы оценочных листов."""
        return self._lists_requested

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
        self.close_button = QPushButton(STRINGS.import_close)
        self.close_button.clicked.connect(self._on_close)
        nav.addWidget(self.back_button)
        nav.addStretch(1)
        nav.addWidget(self.close_button)
        nav.addWidget(self.next_button)
        layout.addLayout(nav)

    def _on_close(self) -> None:
        """Закрывает мастер; после успешного импорта запрашивает журналы.

        На шаге результата (индекс 3) успешно завершённый импорт (не пробный)
        открывает после закрытия окно оценочных листов — для этого диалог
        завершается кодом ``QDialog.Accepted``; во всех остальных случаях
        поведение прежнее (``reject``).
        """
        if self._import_completed():
            self._lists_requested = True
            self.accept()
            return
        self.reject()

    def _import_completed(self) -> bool:
        """Успешный (не пробный) импорт показан на шаге результата."""
        return (
            self._result is not None
            and not self._result.dry_run
            and self.stack.currentIndex() == 3
        )

    def _apply_initial_geometry(self) -> None:
        """Размещает окно по центру экрана размером 40% x 40%."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1000, 720)
            return
        available = screen.availableGeometry()
        self.resize(int(available.width() * 0.4), int(available.height() * 0.4))
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _build_file_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.textChanged.connect(lambda _: self._update_nav())
        browse = QPushButton(STRINGS.import_choose_file)
        browse.clicked.connect(self._choose_file)
        clear = QPushButton(STRINGS.import_clear)
        clear.clicked.connect(self._clear_file)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(browse)
        file_row.addWidget(clear)
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
        self.scheme_label = QLabel(STRINGS.import_scheme_not_detected)
        self.scheme_label.setWordWrap(True)
        create_scheme = QPushButton(STRINGS.import_create_scheme)
        create_scheme.clicked.connect(self._create_scheme)
        scheme_row.addWidget(self.scheme_label, 1)
        scheme_row.addWidget(create_scheme)
        form.addRow(STRINGS.import_scheme, scheme_row)
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
        self.preview_table = QTableWidget(0, 0)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setMaximumHeight(180)
        layout.addWidget(self.preview_table)
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
        self.matches_table = QTableWidget(0, 6)
        self.matches_table.setHorizontalHeaderLabels(
            [
                "№",
                STRINGS.import_match_status,
                STRINGS.import_match_reason,
                STRINGS.label_evaluation_value,
                STRINGS.import_evaluation_presence,
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
        return page

    # -- схемы --------------------------------------------------------------
    def _reload_schemes(self) -> None:
        try:
            self.schemes = load_schemes(self.config.schemes_dir)
        except Exception as exc:  # noqa: BLE001
            self.schemes = []
            self._show_error(exc)

    def _scheme_title(self, scheme: LayoutScheme) -> str:
        length = scheme.line_length
        suffix = STRINGS.import_scheme_length.format(length=length) if length else ""
        return f"{scheme.name}{suffix}"

    def _update_scheme_label(self) -> None:
        scheme = self.importer.scheme
        if scheme is not None:
            self.scheme_label.setText(
                STRINGS.import_scheme_detected.format(title=self._scheme_title(scheme))
            )
            return
        length = self.importer.scheme_length()
        if length is None:
            self.scheme_label.setText(STRINGS.import_scheme_not_detected)
        else:
            self.scheme_label.setText(
                STRINGS.import_scheme_not_found_for_length.format(length=length)
            )

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

    def _load_selected_file(self) -> bool:
        path = self.file_edit.text().strip()
        if not path:
            self._choose_file()
            return False
        try:
            info = self.importer.load_file(path, self.encoding_combo.currentData())
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return False
        self.file_edit.setText(str(info.path))
        self._update_scheme_label()
        self._refresh_preview()
        self._update_nav()
        return True

    def _clear_file(self) -> None:
        self.importer.reset()
        self.file_edit.clear()
        self.scheme_label.setText(STRINGS.import_scheme_not_detected)
        self.preview_table.clear()
        self.preview_table.setRowCount(0)
        self.preview_table.setColumnCount(0)
        self.problems_table.setRowCount(0)
        self.matches_table.setRowCount(0)
        self.match_counts.clear()
        self._duplicate_actions.clear()
        self.stack.setCurrentIndex(0)
        self._update_nav()

    def _create_scheme(self) -> None:
        dialog = SchemeEditorDialog(self.config.schemes_dir, None, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        self._reload_schemes()
        if self.file_edit.text().strip():
            self._load_selected_file()

    def _reload_encoding(self) -> None:
        if self.file_edit.text().strip():
            self._load_selected_file()

    # -- проверка -----------------------------------------------------------
    def _refresh_preview(self) -> None:
        """Показывает начало файла, разбитое по полям выбранной схемы."""
        info = self.importer.info
        scheme = self._current_scheme()
        self.preview_table.clear()
        if info is None or scheme is None:
            self.preview_table.setRowCount(0)
            self.preview_table.setColumnCount(0)
            return
        self.preview_table.setColumnCount(len(scheme.fields))
        self.preview_table.setHorizontalHeaderLabels([item.name for item in scheme.fields])
        try:
            report = parse_rows(info.lines, scheme)
        except Exception:  # noqa: BLE001 - схема могла не подойти к файлу
            self.preview_table.setRowCount(0)
            return
        rows = report.rows[: self.config.preview_lines]
        self.preview_table.setRowCount(len(rows))
        self.preview_table.setVerticalHeaderLabels([str(row.row_no) for row in rows])
        problem_brush = QBrush(QColor("#F8D7DA"))
        for index, row in enumerate(rows):
            parts = split_fields(row.raw, scheme)
            for column, value in enumerate(parts):
                item = QTableWidgetItem(value)
                if row.problem is not None:
                    item.setBackground(problem_brush)
                    item.setToolTip(f"{row.problem.code}: {row.problem.message}")
                self.preview_table.setItem(index, column, item)

    def _current_scheme(self) -> Optional[LayoutScheme]:
        return self.importer.scheme

    def _validate(self) -> None:
        if self.importer.scheme is None:
            self._show_error(ImporterError("scheme_not_selected", STRINGS.import_select_scheme))
            return
        if not self.doc_no_edit.text().strip():
            self._show_error(ImporterError("document_not_set", STRINGS.import_doc_no))
            return
        try:
            self.importer.set_document(
                self.doc_no_edit.text().strip(), self.doc_date_edit.date().toPyDate()
            )
            report = self.importer.validate()
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return
        self._fill_problems()
        self._refresh_preview()
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
                self._add_problem_row(
                    row.row_no,
                    STRINGS.import_status_error,
                    self._problem_text(row.problem.code),
                )
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

    def _problem_text(self, code: str) -> str:
        template = getattr(STRINGS, f"import_problem_{code}", "")
        return template or code

    def _reason_text(self, code: str) -> str:
        if not code:
            return ""
        template = getattr(STRINGS, f"import_reason_{code}", "")
        return template or code

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
        self._refresh_preview()
        self._update_nav()

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
        self._refresh_preview()

    # -- сопоставление ------------------------------------------------------
    def _preview(self) -> None:
        if self.importer.report is None:
            self._validate()
            if self.importer.report is None:
                return
        try:
            preview = self.importer.preview_matches()
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return
        self._fill_matches(preview)

    def _fill_matches(self, preview) -> None:
        self.matches_table.setRowCount(0)
        self._duplicate_actions.clear()
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
            self.matches_table.setItem(
                row, 2, QTableWidgetItem(self._reason_text(result.reason))
            )
            self.matches_table.setItem(row, 3, QTableWidgetItem(result.value_code or ""))
            if not result.matched:
                presence = "—"
            elif not result.value_code:
                presence = STRINGS.import_value_not_set
            elif result.duplicate:
                presence = result.existing_value or STRINGS.import_has_evaluation
            else:
                presence = STRINGS.import_no_evaluation
            self.matches_table.setItem(row, 4, QTableWidgetItem(presence))
            if result.matched and result.value_code and result.duplicate:
                combo = QComboBox()
                combo.addItem(STRINGS.import_action_skip, "skip")
                combo.addItem(STRINGS.import_action_update, "update")
                combo.currentIndexChanged.connect(
                    lambda _, r=result.row.row_no, c=combo: self._duplicate_actions.__setitem__(
                        r, str(c.currentData())
                    )
                )
                self._duplicate_actions[result.row.row_no] = "skip"
                self.matches_table.setCellWidget(row, 5, combo)
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
        counts = result.counts
        self.result_label.setText(
            STRINGS.import_done.format(
                matched=counts.matched,
                unmatched=counts.unmatched,
                skipped=counts.skipped,
                rejected=counts.rejected,
                stored_path=result.stored_path or "—",
            )
        )
        value_lines = []
        for code, count in sorted(counts.by_value.items()):
            label = enum_label("evaluation_value", code) or code
            value_lines.append(f"{label}: {count}")
        lines = [
            STRINGS.import_rows_total.format(count=counts.imported),
            STRINGS.import_stats_evaluations.format(count=counts.evaluations_received),
            STRINGS.import_stats_by_value.format(values=", ".join(value_lines) or "—"),
            STRINGS.import_stats_reupdated.format(
                documents=counts.documents_reupdated,
                materials=counts.materials_reupdated,
            ),
            STRINGS.import_log_saved.format(log_id=result.log_id)
            if result.log_id
            else "",
        ]
        lines.extend(result.warnings)
        self.result_details.setPlainText("\n".join(item for item in lines if item))

    # -- навигация ----------------------------------------------------------
    def _go_back(self) -> None:
        index = self.stack.currentIndex()
        if index > 0:
            self.stack.setCurrentIndex(index - 1)
        self._update_nav()

    def _go_next(self) -> None:
        index = self.stack.currentIndex()
        if index == 0:
            if not self._load_selected_file():
                return
            if self.importer.scheme is None:
                return
            self._validate()
            if self.importer.report is None:
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
            (index == 0 and bool(self.file_edit.text().strip()))
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
