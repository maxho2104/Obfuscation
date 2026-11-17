"""Просмотр журналов импорта оценок и их строк (только чтение)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from internal_correspondence.orm.labels import entity_label
from internal_correspondence.orm.models import ScientificMaterial, Telegram
from internal_correspondence.text_import import repository
from internal_correspondence.utils.string_resources import STRINGS

_STATUS_COLORS = {
    "matched": "#D9EAD3",
    "unmatched": "#F4CCCC",
    "rejected": "#FCE5CD",
}
_STATUS_LABELS = {
    "matched": STRINGS.evaluation_lists_status_matched,
    "unmatched": STRINGS.evaluation_lists_status_unmatched,
    "rejected": STRINGS.evaluation_lists_status_rejected,
}
_REASON_LABELS = {
    "document_not_found": STRINGS.evaluation_lists_reason_document_not_found,
    "document_ambiguous": STRINGS.evaluation_lists_reason_document_ambiguous,
    "key_empty": STRINGS.evaluation_lists_reason_key_empty,
    "year_month_invalid": STRINGS.evaluation_lists_reason_year_month_invalid,
}
_TEXT_COLOR = QColor("#1F2937")


class EvaluationListsDialog(QDialog):
    """Список журналов импорта слева и строки выбранного журнала справа."""

    def __init__(self, engine: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(STRINGS.evaluation_lists_title)
        self.resize(1180, 640)
        self._session = Session(engine)
        repository.ensure_schema(engine)
        self._logs: list[Any] = []
        self._current_log_id: Optional[int] = None

        self._build_ui()
        self._load_logs()

    # -- построение интерфейса ---------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal, self)

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.logs_table = self._make_table(
            [
                STRINGS.evaluation_lists_journal_no,
                STRINGS.evaluation_lists_import_date,
                STRINGS.evaluation_lists_document,
            ]
        )
        self.logs_table.itemSelectionChanged.connect(self._on_log_selected)
        self.logs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.logs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.logs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.logs_table.setColumnWidth(0, 110)
        self.logs_table.setColumnWidth(1, 155)
        left.setMinimumWidth(430)
        left_layout.addWidget(self.logs_table)
        splitter.addWidget(left)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.hint_label = QLabel(STRINGS.evaluation_lists_select, right)
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.rows_table = self._make_table(
            [
                STRINGS.evaluation_lists_row_no,
                STRINGS.evaluation_lists_branch,
                STRINGS.evaluation_lists_outgoing,
                STRINGS.evaluation_lists_month,
                STRINGS.evaluation_lists_value,
                STRINGS.evaluation_lists_date,
                STRINGS.evaluation_lists_status,
                STRINGS.evaluation_lists_entity,
                STRINGS.evaluation_lists_reason,
                STRINGS.evaluation_lists_raw,
            ]
        )
        self.rows_table.setWordWrap(False)
        right.setMinimumWidth(480)
        right_layout.addWidget(self.rows_table, 1)
        right_layout.addWidget(self.hint_label)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([440, 740])
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.close_button = QPushButton(STRINGS.import_close, self)
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setAlternatingRowColors(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    # -- данные -------------------------------------------------------------
    def _load_logs(self) -> None:
        statement = select(
            repository.import_log.c.id,
            repository.import_log.c.doc_no,
            repository.import_log.c.doc_date,
            repository.import_log.c.started_at,
        ).order_by(
            repository.import_log.c.started_at.desc(),
            repository.import_log.c.id.desc(),
        )
        self._logs = list(self._session.execute(statement).all())
        self.logs_table.setRowCount(len(self._logs))
        for row_index, row in enumerate(self._logs):
            self._set_item(self.logs_table, row_index, 0, str(row.id))
            self._set_item(self.logs_table, row_index, 1, _format_datetime(row.started_at))
            self._set_item(
                self.logs_table,
                row_index,
                2,
                f"{row.doc_no} от {_format_date(row.doc_date)}",
            )
        if self._logs:
            self.logs_table.selectRow(0)
        else:
            self.hint_label.setText(STRINGS.evaluation_lists_empty)

    def _on_log_selected(self) -> None:
        selected = self.logs_table.selectionModel().selectedRows()
        if not selected:
            self._current_log_id = None
            self.rows_table.setRowCount(0)
            self.rows_table.hide()
            self.hint_label.setText(STRINGS.evaluation_lists_select)
            self.hint_label.show()
            return
        row_index = selected[0].row()
        if row_index < 0 or row_index >= len(self._logs):
            return
        log_id = int(self._logs[row_index].id)
        if log_id == self._current_log_id:
            return
        self._current_log_id = log_id
        self._load_rows(log_id)

    def _load_rows(self, import_id: int) -> None:
        statement = (
            select(
                repository.import_rows.c.source_row_no,
                repository.import_rows.c.status,
                repository.import_rows.c.error,
                repository.import_rows.c.branch_code,
                repository.import_rows.c.outgoing_no,
                repository.import_rows.c.year_month,
                repository.import_rows.c.value_code,
                repository.import_rows.c.evaluation_date,
                repository.import_rows.c.matched_entity_type,
                repository.import_rows.c.raw_line,
            )
            .where(repository.import_rows.c.import_id == import_id)
            .order_by(repository.import_rows.c.source_row_no)
        )
        rows = list(self._session.execute(statement).all())
        self.rows_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = [
                str(row.source_row_no),
                row.branch_code or "—",
                row.outgoing_no or "—",
                _format_month(row.year_month),
                row.value_code or "—",
                _format_date(row.evaluation_date) if row.evaluation_date else "—",
                _STATUS_LABELS.get(str(row.status), str(row.status)),
                _entity_label(row.matched_entity_type),
                _reason_label(row.error),
                row.raw_line or "",
            ]
            for column, value in enumerate(values):
                item = self._set_item(self.rows_table, index, column, value)
                if str(row.status) in _STATUS_COLORS:
                    item.setBackground(QBrush(QColor(_STATUS_COLORS[str(row.status)])))
                item.setForeground(QBrush(_TEXT_COLOR))
            self.rows_table.item(index, 9).setToolTip(row.raw_line or "")

        self.hint_label.setVisible(not rows)
        self.rows_table.setVisible(bool(rows))
        if rows:
            for column in range(9):
                self.rows_table.resizeColumnToContents(column)
            self.rows_table.horizontalHeader().setStretchLastSection(True)

    # -- вспомогательное -----------------------------------------------------
    @staticmethod
    def _set_item(
        table: QTableWidget,
        row: int,
        column: int,
        value: str,
    ) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        table.setItem(row, column, item)
        return item

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._session.close()
        super().closeEvent(event)

    def accept(self) -> None:  # noqa: D401 - Qt API
        self._session.close()
        super().accept()

    def reject(self) -> None:  # noqa: D401 - Qt API
        self._session.close()
        super().reject()


def _format_date(value: Optional[date]) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def _format_datetime(value: Optional[datetime]) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def _format_month(value: Optional[str]) -> str:
    """Показывает отчётный месяц как ММ.ГГГГ (принимает ГГГГММ и ММГГГГ)."""
    if not value:
        return "—"
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 6:
        return str(value)
    first = int(digits[4:])
    if 1 <= first <= 12:
        year, month = digits[:4], digits[4:]
    else:
        month, year = digits[:2], digits[2:]
    return f"{month}.{year}"


def _entity_label(entity_type: Optional[str]) -> str:
    if entity_type == "material":
        return entity_label(ScientificMaterial)
    if entity_type == "telegram":
        return entity_label(Telegram)
    return "—"


def _reason_label(error: Optional[str]) -> str:
    if not error:
        return "—"
    return _REASON_LABELS.get(error, error)
