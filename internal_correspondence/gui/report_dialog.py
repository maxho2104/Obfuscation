"""Диалог выбора периода и редактирования ручных разделов отчёта."""

from __future__ import annotations

from datetime import date
from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import ReportType
from internal_correspondence.orm.models import Branch
from internal_correspondence.reports.report_service import ReportDataService, ReportRequest
from internal_correspondence.utils.string_resources import STRINGS


class ReportDialog(QDialog):
    """Позволяет выбрать отчётный период и заполнить аналитический текст."""

    def __init__(
        self,
        session: Session,
        branch_id: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.service = ReportDataService(session)
        self.fixed_branch_id = branch_id
        self._accepted_request: Optional[ReportRequest] = None
        self._accepted_values: Dict[str, str] = {}
        self._loading = False

        self.setWindowTitle(STRINGS.title_generate_report)
        self.setModal(True)
        self.resize(680, 720)
        self._setup_ui()
        self._connect_signals()
        self._update_period_options()
        self._load_draft()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        period_group = QGroupBox(STRINGS.title_generate_report)
        period_form = QFormLayout(period_group)

        self.branch_combo = QComboBox()
        self.branch_combo.setObjectName("reportBranchCombo")
        branches = self.session.query(Branch).order_by(Branch.short_name, Branch.name).all()
        for branch in branches:
            self.branch_combo.addItem(branch.short_name or branch.name, branch.id)
        if self.fixed_branch_id:
            index = self.branch_combo.findData(self.fixed_branch_id)
            if index >= 0:
                self.branch_combo.setCurrentIndex(index)
            self.branch_combo.setEnabled(False)
        period_form.addRow(STRINGS.report_label_branch, self.branch_combo)

        self.type_combo = QComboBox()
        self.type_combo.setObjectName("reportTypeCombo")
        self.type_combo.addItem(STRINGS.report_type_month, int(ReportType.MONTH))
        self.type_combo.addItem(
            STRINGS.report_type_half_year, int(ReportType.HALF_YEAR)
        )
        period_form.addRow(STRINGS.report_label_type, self.type_combo)

        self.year_spin = QSpinBox()
        self.year_spin.setObjectName("reportYearSpin")
        self.year_spin.setRange(2000, 2100)
        self.year_spin.setValue(date.today().year)
        period_form.addRow(STRINGS.report_label_year, self.year_spin)

        self.period_combo = QComboBox()
        self.period_combo.setObjectName("reportPeriodCombo")
        period_form.addRow(STRINGS.report_label_period, self.period_combo)
        layout.addWidget(period_group)

        manual_group = QGroupBox(STRINGS.report_group_manual)
        manual_form = QFormLayout(manual_group)

        self.recipient_edit = QLineEdit()
        self.recipient_edit.setObjectName("reportRecipientEdit")
        manual_form.addRow(STRINGS.report_label_recipient, self.recipient_edit)

        self.shortcomings_edit = self._plain_text("reportShortcomingsEdit")
        manual_form.addRow(STRINGS.report_label_shortcomings, self.shortcomings_edit)
        self.results_edit = self._plain_text("reportResultsEdit")
        manual_form.addRow(STRINGS.report_label_results, self.results_edit)
        self.conclusion_edit = self._plain_text("reportConclusionEdit")
        manual_form.addRow(STRINGS.report_label_conclusion, self.conclusion_edit)
        self.plan_edit = self._plain_text("reportPlanEdit")
        manual_form.addRow(STRINGS.report_label_plan, self.plan_edit)
        self.proposals_edit = self._plain_text("reportProposalsEdit")
        manual_form.addRow(STRINGS.report_label_proposals, self.proposals_edit)

        self.signatory_position_edit = QLineEdit()
        self.signatory_position_edit.setObjectName("reportSignatoryPositionEdit")
        manual_form.addRow(
            STRINGS.report_label_signatory_position,
            self.signatory_position_edit,
        )
        self.signatory_name_edit = QLineEdit()
        self.signatory_name_edit.setObjectName("reportSignatoryNameEdit")
        manual_form.addRow(
            STRINGS.report_label_signatory_name,
            self.signatory_name_edit,
        )
        layout.addWidget(manual_group, 1)

        self.button_box = QDialogButtonBox()
        self.generate_button = QPushButton(STRINGS.report_button_generate)
        self.generate_button.setObjectName("generateReportButton")
        self.button_box.addButton(
            self.generate_button,
            QDialogButtonBox.AcceptRole,
        )
        cancel_button = self.button_box.addButton(QDialogButtonBox.Cancel)
        cancel_button.setText(STRINGS.button_cancel)
        layout.addWidget(self.button_box)

    @staticmethod
    def _plain_text(object_name: str) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setObjectName(object_name)
        editor.setMaximumHeight(76)
        return editor

    def _connect_signals(self) -> None:
        self.generate_button.clicked.connect(self._accept_request)
        self.button_box.rejected.connect(self.reject)
        self.type_combo.currentIndexChanged.connect(self._selection_changed)
        self.branch_combo.currentIndexChanged.connect(self._load_draft)
        self.year_spin.valueChanged.connect(self._load_draft)
        self.period_combo.currentIndexChanged.connect(self._load_draft)

    def _selection_changed(self) -> None:
        self._update_period_options()
        self._load_draft()

    def _update_period_options(self) -> None:
        current_number = self.period_combo.currentData()
        self._loading = True
        self.period_combo.clear()
        if self.report_type() == ReportType.MONTH:
            for index, month in enumerate(self.month_names(), start=1):
                self.period_combo.addItem(month, index)
            target = date.today().month
        else:
            self.period_combo.addItem(STRINGS.report_half_1, 1)
            self.period_combo.addItem(STRINGS.report_half_2, 2)
            target = 1 if date.today().month <= 6 else 2
        if current_number is not None:
            target = int(current_number)
        index = self.period_combo.findData(target)
        self.period_combo.setCurrentIndex(max(index, 0))
        self._loading = False

    def report_type(self) -> ReportType:
        """Возвращает выбранный тип отчёта."""
        return ReportType(int(self.type_combo.currentData()))

    @staticmethod
    def month_names() -> list[str]:
        """Возвращает пакетные названия месяцев для интерфейса и отчёта."""
        return [name.strip() for name in STRINGS.report_month_names.split(",")]

    def _current_request(self) -> Optional[ReportRequest]:
        branch_id = self.branch_combo.currentData()
        period_number = self.period_combo.currentData()
        if not branch_id or period_number is None:
            return None
        return ReportRequest(
            report_type=self.report_type(),
            branch_id=str(branch_id),
            year=self.year_spin.value(),
            period_number=int(period_number),
        )

    def _load_draft(self) -> None:
        if self._loading:
            return
        request = self._current_request()
        draft = self.service.load_draft(request) if request is not None else None
        self._loading = True
        self.recipient_edit.setText(
            (draft.recipient if draft else None) or STRINGS.report_default_recipient
        )
        self.shortcomings_edit.setPlainText((draft.shortcomings if draft else None) or "")
        self.results_edit.setPlainText(
            (draft.significant_results if draft else None) or ""
        )
        self.proposals_edit.setPlainText((draft.proposals if draft else None) or "")
        self.conclusion_edit.setPlainText((draft.conclusion if draft else None) or "")
        self.plan_edit.setPlainText((draft.plan_execution if draft else None) or "")
        self.signatory_position_edit.setText(
            (draft.signatory_position if draft else None)
            or STRINGS.report_default_signatory_position
        )
        self.signatory_name_edit.setText(
            (draft.signatory_name if draft else None)
            or STRINGS.report_default_signatory_name
        )
        self._loading = False

    def _accept_request(self) -> None:
        request = self._current_request()
        if request is None:
            QMessageBox.warning(
                self,
                STRINGS.title_generate_report,
                STRINGS.report_msg_no_branch,
            )
            return
        self._accepted_request = request
        self._accepted_values = self.draft_values()
        self.accept()

    def selected_request(self) -> ReportRequest:
        """Возвращает параметры после успешного принятия диалога."""
        if self._accepted_request is None:
            raise RuntimeError(STRINGS.report_error_dialog_not_accepted)
        return self._accepted_request

    def draft_values(self) -> Dict[str, str]:
        """Собирает ручные поля, введённые пользователем."""
        return {
            "recipient": self.recipient_edit.text(),
            "shortcomings": self.shortcomings_edit.toPlainText(),
            "significant_results": self.results_edit.toPlainText(),
            "proposals": self.proposals_edit.toPlainText(),
            "conclusion": self.conclusion_edit.toPlainText(),
            "plan_execution": self.plan_edit.toPlainText(),
            "signatory_position": self.signatory_position_edit.text(),
            "signatory_name": self.signatory_name_edit.text(),
        }
