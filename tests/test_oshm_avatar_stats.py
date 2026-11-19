"""Тесты аватарок, статистики элемента и новой панели сведений ОШС."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.constants import (
    EvaluationValue,
    MaterialType,
    TelegramType,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.gui.oshm_dialog import OSHMDialog
from internal_correspondence.orm.models import (
    Branch,
    Consumer,
    Department,
    Employee,
    Evaluation,
    ScientificMaterial,
    Telegram,
    TerritorialUnit,
)
from internal_correspondence.reports.statistics_service import Period
from internal_correspondence.services.avatar_service import (
    AVATAR_HEIGHT,
    AVATAR_WIDTH,
    AvatarError,
    avatar_file_name,
    remove_avatar,
    resolve_avatar,
    save_avatar,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.services.element_stats_service import (
    ElementStatsService,
    shift_period_year,
)


@pytest.fixture(scope="function")
def db_manager(tmp_path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'panel.db'}")
    db.create_tables()
    yield db
    db.close()


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def element_data(db_manager):
    """Филиал, отдел, сотрудник и документы с оценками в разных периодах."""
    session = db_manager.get_session()
    session.add(TerritorialUnit(id="TU", name="Единица"))
    session.add(Branch(id="F1", name="Филиал 1", short_name="Ф1", territorial_unit_id="TU"))
    session.flush()
    department = Department(name="Отдел", branch_id="F1", active=True)
    session.add(department)
    session.flush()
    employee = Employee(
        last_name="Иванов", first_name="Иван",
        department_id=department.id, active=True,
    )
    session.add(employee)
    session.add(Consumer(id="C1", short_name="П1", name="Потребитель 1"))
    session.flush()

    def make_material(day, value=None, emp=True):
        material = ScientificMaterial(
            type=MaterialType.MESSAGE,
            name=f"Материал {day}",
            branch_id="F1",
            outgoing_number=f"1-{day}",
            outgoing_date=date(2026, 6, day),
            consumer_id="C1",
        )
        if emp:
            material.employees.append(employee)
        session.add(material)
        session.flush()
        if value is not None:
            evaluation = Evaluation(value=value, date=date(2026, 6, day))
            evaluation.materials.append(material)
            session.add(evaluation)
        return material

    make_material(1, EvaluationValue.USEFUL)      # вес 2
    make_material(10, EvaluationValue.IMPORTANT)  # вес 3
    make_material(20)                             # без оценки
    # Материал прошлого года (тот же период год назад)
    old = ScientificMaterial(
        type=MaterialType.DOCUMENT,
        name="Материал 2025",
        branch_id="F1",
        outgoing_number="1-0",
        outgoing_date=date(2025, 6, 5),
        consumer_id="C1",
    )
    old.employees.append(employee)
    session.add(old)
    session.flush()
    old_eval = Evaluation(value=EvaluationValue.INTERESTING, date=date(2025, 6, 5))
    old_eval.materials.append(old)
    session.add(old_eval)

    telegram = Telegram(
        type=TelegramType.THEMATIC,
        name="Телеграмма",
        branch_id="F1",
        outgoing_number="Т-1",
        outgoing_date=date(2026, 6, 15),
    )
    telegram.employees.append(employee)
    session.add(telegram)
    session.commit()
    return {"department": department, "employee": employee}


# ----------------------------------------------------------------------
# Сервис аватарок
# ----------------------------------------------------------------------


def _make_source_image(path: Path, size=(600, 400)) -> Path:
    image = Image.new("RGB", size, (40, 90, 160))
    image.save(path, format="PNG")
    return path


def test_save_and_remove_avatar(db_manager, element_data, tmp_path):
    session = db_manager.get_session()
    storage = tmp_path / "storage"
    employee = session.get(Employee, element_data["employee"].id)

    source = _make_source_image(tmp_path / "source.png")
    target = save_avatar(employee, "employee", storage, source)

    # Имя однозначно интерпретируется: тип, наименование, хвост id
    name = avatar_file_name(employee, "employee")
    assert target.name == name
    assert name.startswith("employee_Иванов_")
    assert target.is_file()
    assert not source.exists()  # файл перенесён, а не скопирован
    with Image.open(target) as saved:
        assert saved.size == (AVATAR_WIDTH, AVATAR_HEIGHT)

    assert resolve_avatar(storage, employee, "employee") == target
    remove_avatar(employee, "employee", storage)
    assert not target.exists()
    assert resolve_avatar(storage, employee, "employee") is None


def test_resolve_avatar_missing(db_manager, element_data, tmp_path):
    session = db_manager.get_session()
    storage = tmp_path / "storage"
    employee = session.get(Employee, element_data["employee"].id)
    assert resolve_avatar(storage, employee, "employee") is None


def test_save_avatar_unsupported_format(db_manager, element_data, tmp_path):
    session = db_manager.get_session()
    storage = tmp_path / "storage"
    employee = session.get(Employee, element_data["employee"].id)
    bad = tmp_path / "notes.txt"
    bad.write_text("не изображение", encoding="utf-8")
    with pytest.raises(AvatarError):
        save_avatar(employee, "employee", storage, bad)


# ----------------------------------------------------------------------
# Сервис статистики элемента
# ----------------------------------------------------------------------


def test_period_stats_employee(db_manager, element_data):
    session = db_manager.get_session()
    service = ElementStatsService(session)
    period = Period("Июнь 2026", date(2026, 6, 1), date(2026, 6, 30))

    stats = service.period_stats("employee", str(element_data["employee"].id), period)

    assert stats.materials == 3  # материалы июня (прошлогодний не попал)
    assert stats.telegrams == 1
    assert stats.evaluations == 2
    assert stats.evaluation_counts == {
        int(EvaluationValue.USEFUL): 1,
        int(EvaluationValue.IMPORTANT): 1,
    }
    assert stats.avg_weight == 2.5
    assert stats.material_type_counts == {int(MaterialType.MESSAGE): 3}
    assert stats.telegram_type_counts == {int(TelegramType.THEMATIC): 1}


def test_period_stats_department_and_branch(db_manager, element_data):
    session = db_manager.get_session()
    service = ElementStatsService(session)
    period = Period("Июнь 2026", date(2026, 6, 1), date(2026, 6, 30))

    dept_stats = service.period_stats(
        "department", str(element_data["department"].id), period
    )
    assert dept_stats.materials == 3
    assert dept_stats.telegrams == 1

    branch_stats = service.period_stats("branch", "F1", period)
    assert branch_stats.materials == 3
    assert branch_stats.telegrams == 1


def test_period_stats_previous_year(db_manager, element_data):
    session = db_manager.get_session()
    service = ElementStatsService(session)
    period = Period("Июнь 2025", date(2025, 6, 1), date(2025, 6, 30))

    stats = service.period_stats("employee", str(element_data["employee"].id), period)

    assert stats.materials == 1
    assert stats.evaluations == 1
    assert stats.avg_weight == 1.0  # «Интересно», вес 1


def test_shift_period_year():
    period = Period("Июнь 2026", date(2026, 6, 1), date(2026, 6, 30))
    shifted = shift_period_year(period, -1)
    assert shifted.start == date(2025, 6, 1)
    assert shifted.end == date(2025, 6, 30)
    assert "2025" in shifted.label
    assert shift_period_year(period, 0) == period


# ----------------------------------------------------------------------
# Панель сведений
# ----------------------------------------------------------------------


def test_details_panel_new_structure(qt_app, db_manager, element_data, tmp_path):
    """Аватарка с кнопками, коэффициент, таблица оценок и две диаграммы."""
    from PyQt5.QtCore import Qt

    from internal_correspondence.core.constants import Role

    session = db_manager.get_session()
    dialog = OSHMDialog(
        session,
        branch_id="F1",
        role=Role.BRANCH.value,
        storage_root=tmp_path / "storage",
    )
    employee = element_data["employee"]
    item = dialog.tree_structure.findItems(
        employee.display_name(), Qt.MatchContains | Qt.MatchRecursive
    )
    assert item, "сотрудник не найден в дереве"
    dialog._show_details(item[0], dialog.tree_structure)

    panel = dialog.details_panel
    # Аватарка: фиксированный размер и заглушка
    assert panel.avatar_label.width() == AVATAR_WIDTH
    assert panel.avatar_label.height() == AVATAR_HEIGHT
    assert not panel.avatar_add_btn.isEnabled() is False  # доступна
    # Коэффициент эффективности — просто цифра справа от наименования
    assert panel.coef_value is not None
    # Таблица оценок и две диаграммы на месте
    assert panel.eval_table.columnCount() == 2
    assert panel.current_chart is not None
    assert panel.previous_chart is not None
    assert panel.print_btn is not None
    dialog.deleteLater()


def test_dialog_minimum_sizes(qt_app, db_manager, element_data):
    """У диалога и половин сплиттера заданы минимальные размеры."""
    from internal_correspondence.core.constants import Role

    dialog = OSHMDialog(
        db_manager.get_session(),
        branch_id="F1",
        role=Role.BRANCH.value,
    )
    assert dialog.minimumWidth() >= 1000
    assert dialog.details_panel.minimumWidth() >= 600
    dialog.deleteLater()
