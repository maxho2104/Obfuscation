"""Тесты подготовки данных и формирования аналитических DOCX-отчётов."""

import hashlib
import os
import zipfile
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from docx import Document

from internal_correspondence.core.constants import (
    EvaluationValue,
    MaterialType,
    ReportType,
    ScientificTaskType,
    TelegramReportType,
    TelegramType,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.report_dialog import ReportDialog
from internal_correspondence.orm.models import (
    Branch,
    Department,
    Employee,
    Evaluation,
    Leader,
    ReportAddress,
    ScientificMaterial,
    ScientificTask,
    Telegram,
    TerritorialUnit,
    WorkGroupMembership,
    WorkingGroup,
)
from internal_correspondence.reports.report_service import ReportDataService, ReportRequest
from internal_correspondence.reports import word_report
from internal_correspondence.reports.word_report import ensure_user_templates, render_report
from internal_correspondence.services.change_tracking import register_change_tracking


MONTH_NAMES = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def report_env(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'reports.db'}")
    db.create_tables()
    session = db.get_session()

    session.add(TerritorialUnit(id="TU", name="Территориальная единица"))
    session.add(
        Branch(
            id="BR",
            name="Научный филиал",
            short_name="НФ",
            territorial_unit_id="TU",
        )
    )
    department = Department(name="Научный отдел", short_name="НО", branch_id="BR")
    session.add(department)
    session.flush()
    workgroup = WorkingGroup(name="Рабочая группа", department_id=department.id)
    session.add(workgroup)
    session.flush()
    employee = Employee(
        last_name="Иванов",
        first_name="Иван",
        department_id=department.id,
        workgroup_memberships=[WorkGroupMembership(working_group=workgroup)],
    )
    task = ScientificTask(
        id="TASK-1",
        name="Основная научная задача",
        type=ScientificTaskType.MAIN,
        start_date=date(2025, 1, 1),
    )
    session.add_all([employee, task, Leader(id="Директор", active=True)])
    session.flush()

    current_material = ScientificMaterial(
        type=MaterialType.MESSAGE,
        name="Материал текущего периода",
        branch_id="BR",
        outgoing_number="М-1",
        outgoing_date=date(2026, 7, 10),
        cost=1250,
        employees=[employee],
        tasks=[task],
    )
    previous_material = ScientificMaterial(
        type=MaterialType.DOCUMENT,
        name="Материал прошлого периода",
        branch_id="BR",
        outgoing_number="М-0",
        outgoing_date=date(2025, 7, 12),
        cost=500,
        employees=[employee],
        tasks=[task],
    )
    evaluation = Evaluation(
        value=EvaluationValue.IMPORTANT,
        date=date(2026, 7, 20),
    )
    current_material.evaluations = [evaluation]

    current_telegram = Telegram(
        type=TelegramType.THEMATIC,
        name="Телеграмма текущего периода",
        branch_id="BR",
        outgoing_number="Т-1",
        outgoing_date=date(2026, 7, 15),
        report_type=TelegramReportType.URGENTLY_REPORTED,
        employees=[employee],
    )
    current_telegram.report_addresses = [
        ReportAddress(leader_id="Директор", report_date=date(2026, 7, 15))
    ]
    previous_telegram = Telegram(
        type=TelegramType.RESULTS_REPORT,
        name="Телеграмма прошлого периода",
        branch_id="BR",
        outgoing_number="Т-0",
        outgoing_date=date(2025, 7, 16),
        report_type=TelegramReportType.REPORTED,
        employees=[employee],
    )
    session.add_all(
        [
            current_material,
            previous_material,
            current_telegram,
            previous_telegram,
        ]
    )
    session.commit()

    yield db, session, tmp_path
    session.close()
    db.close()


def test_monthly_context_compares_same_month_previous_year(report_env) -> None:
    _db, session, _tmp_path = report_env
    service = ReportDataService(session)
    request = ReportRequest(ReportType.MONTH, "BR", 2026, 7)

    context = service.build_context(request, MONTH_NAMES)

    assert context["period_label"] == "Июль 2026"
    assert context["materials_total"] == {"current": 1, "previous": 1}
    assert context["telegrams_total"] == {"current": 1, "previous": 1}
    assert context["task_rows"][0]["display"] == "1 (1)"
    assert context["evaluated_materials"]["current"] == 1
    assert context["reported_percent"] == "100,0"
    assert context["telegram_details"][0]["leaders"].startswith("Директор")


def test_halfyear_context_contains_department_tables(report_env) -> None:
    _db, session, _tmp_path = report_env
    service = ReportDataService(session)
    request = ReportRequest(ReportType.HALF_YEAR, "BR", 2026, 2)

    context = service.build_context(request, MONTH_NAMES)

    assert context["department_telegram_rows"][0]["total"] == "1 (1)"
    assert context["workgroup_telegram_rows"][0]["urgent"] == "1 (0)"
    assert context["department_material_rows"][0]["total"] == "1 (1)"
    assert context["department_material_rows"][0]["type_values"][0] == "1 (0)"
    assert "НО" in context["department_ranking"]


def test_report_draft_is_saved_for_period(report_env) -> None:
    _db, session, _tmp_path = report_env
    service = ReportDataService(session)
    request = ReportRequest(ReportType.MONTH, "BR", 2026, 7)

    draft = service.save_draft(
        request,
        {
            "recipient": "Руководителю",
            "shortcomings": "Замечание",
            "signatory_name": "И. Иванов",
        },
    )
    session.commit()
    session.expire_all()

    loaded = service.load_draft(request)
    assert loaded is not None
    assert loaded.id == draft.id
    assert loaded.shortcomings == "Замечание"
    assert loaded.signatory_name == "И. Иванов"


@pytest.mark.parametrize(
    ("report_type", "period_number"),
    [(ReportType.MONTH, 7), (ReportType.HALF_YEAR, 2)],
)
def test_docx_report_is_rendered_without_template_markers(
    report_env,
    report_type: ReportType,
    period_number: int,
) -> None:
    _db, session, tmp_path = report_env
    service = ReportDataService(session)
    request = ReportRequest(report_type, "BR", 2026, period_number)
    context = service.build_context(request, MONTH_NAMES)
    output = tmp_path / f"report-{int(report_type)}.docx"

    render_report(report_type, context, tmp_path / "storage", output)

    assert output.exists()
    with zipfile.ZipFile(output) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert "{{" not in xml
    assert "{%" not in xml
    document = Document(output)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Научный филиал" in text or "НФ" in text
    expected_table_count = 1 if report_type == ReportType.MONTH else 3
    assert len(document.tables) == expected_table_count


def test_known_obsolete_template_is_refreshed_without_overwriting_custom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / "storage"
    template_dir = ensure_user_templates(storage_root)
    month_path = template_dir / "monthly_analysis.docx"
    halfyear_path = template_dir / "halfyear_analysis.docx"

    obsolete_content = b"known obsolete template"
    custom_content = b"custom user template"
    month_path.write_bytes(obsolete_content)
    halfyear_path.write_bytes(custom_content)
    obsolete_hash = hashlib.sha256(obsolete_content).hexdigest()
    monkeypatch.setitem(
        word_report._OBSOLETE_TEMPLATE_HASHES,
        "monthly_analysis.docx",
        {obsolete_hash},
    )

    ensure_user_templates(storage_root)

    assert month_path.read_bytes() != obsolete_content
    assert len(Document(month_path).tables) == 1
    assert halfyear_path.read_bytes() == custom_content


def test_report_dialog_switches_period_type_and_collects_values(
    report_env,
    qt_app: QApplication,
) -> None:
    _db, session, _tmp_path = report_env
    dialog = ReportDialog(session, branch_id="BR")

    assert dialog.period_combo.count() == 12
    dialog.type_combo.setCurrentIndex(1)
    assert dialog.period_combo.count() == 2
    dialog.conclusion_edit.setPlainText("Итоговый вывод")
    dialog._accept_request()

    assert dialog.selected_request().report_type == ReportType.HALF_YEAR
    assert dialog.draft_values()["conclusion"] == "Итоговый вывод"
    dialog.close()
