"""Тесты скрипта наполнения базы данными филиала (``tests.seed_branch``)."""

import random
import re
import uuid
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path
from typing import List

import pytest
from faker import Faker

from internal_correspondence.core.constants import MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    AddedTask,
    AcademicTitle,
    Branch,
    Consumer,
    Country,
    Department,
    Employee,
    FileRecord,
    Leader,
    ReportAddress,
    ScientificMaterial,
    ScientificTask,
    Source,
    Telegram,
    TerritorialUnit,
    WorkGroupMembership,
    WorkingGroup,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from internal_correspondence.services.task_distribution_service import (
    NODE_BRANCH,
    NODE_DEPARTMENT,
    NODE_EMPLOYEE,
    NODE_WORKGROUP,
)
from tests.seed_data import seed_branch_2, seed_branch_add_4, seed_reference_1
from tests.seed_data.seed_branch_2 import (
    BranchSeedError,
    _distribute_branch_tasks,
    _load_reference_data,
    _resolve_branch,
)


# ---------------------------------------------------------------------------
# Запуск скрипта на временной базе
# ---------------------------------------------------------------------------


def _ensure_references(tmp_path: Path, branches: int = 1) -> None:
    """Создаёт справочники ГО (аналог приёма архива головного офиса)."""
    register_change_tracking()
    db = _open_db(tmp_path)
    db.create_tables()
    try:
        with db.get_session() as session:
            if session.query(Branch).count():
                return
            seed_reference_1.create_reference_data(
                session,
                Faker("ru_RU"),
                Namespace(
                    units=1,
                    branches_per_unit=branches,
                    countries=(30, 40),
                    consumers=10,
                    leaders=5,
                    tasks=60,
                ),
            )
            session.commit()
    finally:
        db.close()


def _run_seed(tmp_path: Path, extra: List[str]) -> None:
    """Запускает seed_branch с базой и хранилищем во временном каталоге."""
    _ensure_references(tmp_path)
    argv = [
        "--db-url", f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
        "--storage", (tmp_path / "storage").as_posix(),
    ] + extra
    assert seed_branch_2.main(argv) == 0


def _open_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(f"sqlite:///{(tmp_path / 'seed.db').as_posix()}")
    return db


def test_generates_documents_with_yearly_counters(tmp_path: Path) -> None:
    _run_seed(
        tmp_path,
        [

            "--from", "2026-10-01",
            "--to", "2026-10-05",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "1-1",
            "--seed", "42",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            branch = session.query(Branch).filter_by(short_name="Ф-1").one()
            materials = (
                session.query(ScientificMaterial)
                .order_by(ScientificMaterial.outgoing_date,
                          ScientificMaterial.outgoing_number)
                .all()
            )
            telegrams = (
                session.query(Telegram)
                .order_by(Telegram.outgoing_date, Telegram.outgoing_number)
                .all()
            )

            assert len(materials) == 5
            assert len(telegrams) == 5
            # Исходящие номера материалов и телеграмм — раздельные
            # последовательности, цифры по порядку в течение года.
            material_nums = [
                int(m.outgoing_number.split("-")[1]) for m in materials
            ]
            telegram_nums = [
                int(t.outgoing_number.split("-")[1]) for t in telegrams
            ]
            assert material_nums == list(range(1, 6))
            assert telegram_nums == list(range(1, 6))
            assert all(m.outgoing_number.startswith("ИСХ-") for m in materials)
            assert all(t.outgoing_number.startswith("ТЛГ-") for t in telegrams)
            # Номера монотонно возрастают по датам.
            assert [m.outgoing_date for m in materials] == sorted(
                m.outgoing_date for m in materials
            )
            # Все документы — от лица заданного филиала.
            assert all(m.branch_id == branch.id for m in materials)
            assert all(t.branch_id == branch.id for t in telegrams)
            # ОШС филиала создана.
            assert session.query(Department).count() >= 2
            # Адреса докладов без даты (дату проставляет головной офис).
            addresses = session.query(ReportAddress).all()
            assert addresses
            assert all(a.report_date is None for a in addresses)
    finally:
        db.close()


def test_counters_reset_on_new_year(tmp_path: Path) -> None:
    _run_seed(
        tmp_path,
        [

            "--from", "2025-12-30",
            "--to", "2026-01-02",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "0-0",
            "--seed", "1",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            materials = (
                session.query(ScientificMaterial)
                .order_by(ScientificMaterial.outgoing_date)
                .all()
            )
            by_year = {}
            for material in materials:
                number = int(material.outgoing_number.split("-")[1])
                by_year.setdefault(material.outgoing_date.year, []).append(number)
            # 2025: 30 и 31 декабря; 2026: счётчик сброшен, нумерация с 1.
            assert by_year[2025] == [1, 2], by_year
            assert by_year[2026] == [1, 2], by_year
    finally:
        db.close()


def test_permit_fields_for_sample_types(tmp_path: Path) -> None:
    _run_seed(
        tmp_path,
        [

            "--from", "2026-09-01",
            "--to", "2026-09-20",
            "--materials-per-day", "2-3",
            "--telegrams-per-day", "0-0",
            "--seed", "7",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            materials = session.query(ScientificMaterial).all()
            permit_types = {
                MaterialType.PRODUCT_SAMPLE.value,
                MaterialType.TECHNICAL_DOCUMENT.value,
            }
            permitted = [m for m in materials if m.type in permit_types]
            assert permitted, "ожидались материалы типов с разрешительным документом"
            permit_numbers = []
            for material in permitted:
                assert material.serial_number
                assert material.release_year is not None
                assert material.permit_number
                assert material.permit_date in (
                    material.outgoing_date,
                    material.outgoing_date - timedelta(days=1),
                )
                permit_numbers.append(int(material.permit_number.split("-")[1]))
                if material.type == MaterialType.PRODUCT_SAMPLE.value:
                    assert material.cost is not None
            # Разрешительные документы нумеруются отдельным счётчиком.
            assert sorted(permit_numbers) == list(range(1, len(permit_numbers) + 1))
            # Остальные типы разрешительного документа не имеют.
            others = [m for m in materials if m.type not in permit_types]
            assert all(m.permit_number is None for m in others)
    finally:
        db.close()


def test_sources_have_uuid_and_unique_index(tmp_path: Path) -> None:
    _run_seed(
        tmp_path,
        [

            "--from", "2026-09-01",
            "--to", "2026-09-02",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "0-0",
            "--sources", "12",
            "--seed", "3",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            sources = session.query(Source).all()
            assert len(sources) == 12
            assert all(isinstance(source.id, uuid.UUID) for source in sources)
            indexes = [source.index for source in sources]
            assert len(indexes) == len(set(indexes))
            assert all(
                re.fullmatch(r"(А|И|Д|П|СМИ)\d{5}", idx) for idx in indexes
            )
    finally:
        db.close()


def test_attach_files_when_requested(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    _run_seed(
        tmp_path,
        [

            "--from", "2026-09-01",
            "--to", "2026-09-15",
            "--materials-per-day", "1-2",
            "--telegrams-per-day", "1-1",
            "--with-files",
            "--seed", "11",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            records = session.query(FileRecord).all()
            assert records
            for record in records:
                path = (
                    storage
                    / record.path
                    / f"{record.name}.{record.extension}"
                )
                assert path.exists(), path
    finally:
        db.close()


def test_branch_taken_from_references_when_not_specified(tmp_path: Path) -> None:
    """Без параметра используется единственный филиал из справочников ГО."""
    _ensure_references(tmp_path, branches=1)
    _run_seed(
        tmp_path,
        [
            "--from", "2026-09-01",
            "--to", "2026-09-02",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "0-0",
            "--seed", "5",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            branches = session.query(Branch).all()
            assert len(branches) == 1
            assert branches[0].short_name == "Ф-1"
            # Справочники не продублировались.
            assert 30 <= session.query(Country).count() <= 40
    finally:
        db.close()


def test_documents_always_have_countries_and_employees(tmp_path: Path) -> None:
    """Страны и сотрудники — обязательные поля: сидирование заполняет всегда."""
    _run_seed(
        tmp_path,
        [

            "--from", "2026-09-01",
            "--to", "2026-09-12",
            "--materials-per-day", "1-2",
            "--telegrams-per-day", "1-1",
            "--seed", "17",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            materials = session.query(ScientificMaterial).all()
            telegrams = session.query(Telegram).all()
            assert materials and telegrams
            for document in materials + telegrams:
                assert len(document.countries) >= 1, document.outgoing_number
                assert len(document.employees) >= 1, document.outgoing_number
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Справочники из архива головного офиса
# ---------------------------------------------------------------------------


@pytest.fixture()
def session(tmp_path: Path):
    """Сессия временной SQLite со справочниками головного офиса."""
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'branch.db'}")
    db.create_tables()
    with db.get_session() as current:
        current.add(TerritorialUnit(id="TU-1", name="Регион"))
        current.add(
            Branch(id="BR-1", name="Филиал 1", short_name="Ф-1",
                   territorial_unit_id="TU-1")
        )
        current.add(Country(id="RUS", name="Россия"))
        current.add(
            AcademicTitle(id="Д-р", name="Доктор наук", genitive="Доктора наук",
                          dative="Доктору наук", sort_order=1)
        )
        current.add(Consumer(id="CONS-1", short_name="Потр-1", name="Потребитель"))
        current.add(Leader(id="LEAD-1"))
        current.add(
            ScientificTask(
                id="TASK-0001", name="Задача", type=1, start_date=date(2025, 1, 1)
            )
        )
        current.commit()
        yield current
    db.close()


def test_load_reference_data_raises_when_missing(tmp_path: Path) -> None:
    """Без справочников ГО скрипт филиала отказывается работать."""
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'empty.db'}")
    db.create_tables()
    with db.get_session() as current:
        with pytest.raises(BranchSeedError):
            _load_reference_data(current)
    db.close()


def test_load_reference_data_returns_rows(session) -> None:
    """Справочники читаются из базы, загруженной из архива головного офиса."""
    references = _load_reference_data(session)
    assert references["countries"]
    assert references["tasks"]


def test_resolve_branch_takes_single_branch_from_db(session) -> None:
    """Филиал берётся из базы, без параметров командной строки."""
    assert _resolve_branch(session).id == "BR-1"


def test_resolve_branch_errors_with_many(session) -> None:
    """При нескольких филиалах без однозначного выбора — ошибка."""
    session.add(
        Branch(id="BR-2", name="Филиал 2", short_name="Ф-2",
               territorial_unit_id="TU-1")
    )
    session.flush()
    with pytest.raises(BranchSeedError):
        _resolve_branch(session)


# ---------------------------------------------------------------------------
# Каскадное распределение задач филиала
# ---------------------------------------------------------------------------


def _build_structure(session, branch: Branch) -> None:
    """Создаёт отдел с группой из двух сотрудников."""
    department = Department(name="Отдел", short_name="О-1", branch=branch)
    group = WorkingGroup(name="Группа", department=department)
    for last_name in ("Иванов", "Петров"):
        employee = Employee(
            last_name=last_name, first_name="Иван", department=department
        )
        employee.workgroup_memberships.append(
            WorkGroupMembership(
                working_group=group, start_date=date(2025, 1, 1), end_date=None
            )
        )
    session.add(department)
    session.flush()


def _assign_to_branch(session, task_id: str, branch_id: str) -> None:
    """Назначает задачу филиалу, как это делает головной офис."""
    session.add(
        AddedTask(task_id=task_id, node_type=NODE_BRANCH, node_id=branch_id)
    )
    session.flush()


def test_distribute_branch_tasks_cascade(session) -> None:
    """Каждая задача филиала доходит до отделов, групп и сотрудников."""
    random.seed(7)
    branch = session.query(Branch).one()
    _build_structure(session, branch)
    for index in range(10, 13):
        session.add(
            ScientificTask(
                id=f"TASK-{index:04d}", name=f"Задача {index}", type=1,
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
            )
        )
    session.flush()
    for index in range(10, 13):
        _assign_to_branch(session, f"TASK-{index:04d}", branch.id)

    stats = _distribute_branch_tasks(session, branch, date.today())

    assert stats["tasks"] == 3
    assert stats["undistributed"] == 0
    assignments = session.query(AddedTask).all()
    by_type = {}
    for row in assignments:
        by_type.setdefault(row.node_type, set()).add(row.task_id)
    # Ни одной задачи филиала без назначения на отдел
    assert by_type[NODE_DEPARTMENT] == {"TASK-0010", "TASK-0011", "TASK-0012"}
    # Каждая задача опускается до групп и сотрудников (равенство наборов:
    # минимум одна группа на отдел и минимум один сотрудник на группу)
    assert by_type[NODE_WORKGROUP] == by_type[NODE_DEPARTMENT]
    assert by_type[NODE_EMPLOYEE] == by_type[NODE_WORKGROUP]


def test_distribute_branch_tasks_without_departments(session) -> None:
    """Без отделов задачи остаются на уровне филиала и считаются нераспределёнными."""
    branch = session.query(Branch).one()
    _assign_to_branch(session, "TASK-0001", branch.id)

    stats = _distribute_branch_tasks(session, branch, date.today())

    assert stats["undistributed"] == 1
    assert session.query(AddedTask).count() == 1  # только назначение филиалу


def test_distribute_branch_tasks_is_idempotent(session) -> None:
    """Повторный прогон не дублирует назначения (ограничение уникальности)."""
    random.seed(3)
    branch = session.query(Branch).one()
    _build_structure(session, branch)
    _assign_to_branch(session, "TASK-0001", branch.id)

    _distribute_branch_tasks(session, branch, date.today())
    count = session.query(AddedTask).count()
    _distribute_branch_tasks(session, branch, date.today())
    assert session.query(AddedTask).count() == count


def test_distribute_skips_ended_memberships(session) -> None:
    """Сотрудники с закрытым участием в группе задачи не получают."""
    random.seed(11)
    branch = session.query(Branch).one()
    department = Department(name="Отдел", short_name="О-1", branch=branch)
    group = WorkingGroup(name="Группа", department=department)
    active = Employee(last_name="Иванов", first_name="Иван", department=department)
    active.workgroup_memberships.append(
        WorkGroupMembership(working_group=group, start_date=date(2025, 1, 1))
    )
    ended = Employee(last_name="Петров", first_name="Пётр", department=department)
    ended.workgroup_memberships.append(
        WorkGroupMembership(
            working_group=group,
            start_date=date(2024, 1, 1),
            end_date=date.today() - timedelta(days=1),
        )
    )
    session.add(department)
    session.flush()
    _assign_to_branch(session, "TASK-0001", branch.id)

    _distribute_branch_tasks(session, branch, date.today())

    employees_with_tasks = {
        row.node_id
        for row in session.query(AddedTask).filter_by(node_type=NODE_EMPLOYEE)
    }
    assert str(ended.id) not in employees_with_tasks


def test_generated_structure_guarantees_distributability(tmp_path: Path) -> None:
    """ОШС сидирования всегда распределябельна: активные группы и участники."""
    _run_seed(
        tmp_path,
        [
            "--from", "2026-09-01",
            "--to", "2026-09-03",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "0-0",
            "--seed", "23",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            departments = session.query(Department).all()
            assert departments
            for department in departments:
                assert department.workgroups, "у отдела нет групп"
                assert any(group.active for group in department.workgroups)
                assert any(employee.active for employee in department.employees)
                for group in department.workgroups:
                    assert any(
                        membership.is_active_on(date.today())
                        and membership.employee.active
                        for membership in group.memberships
                    ), f"у группы {group.name} нет действующего участника"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Скрипт добавления порций документов (seed_branch_add_4)
# ---------------------------------------------------------------------------


def _run_add(tmp_path: Path, extra: List[str]) -> None:
    """Запускает seed_branch_add_4 с базой и хранилищем во временном каталоге."""
    argv = [
        "--db-url", f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
        "--storage", (tmp_path / "storage").as_posix(),
    ] + extra
    assert seed_branch_add_4.main(argv) == 0


def test_add_continues_from_latest_document_date(tmp_path: Path) -> None:
    """Добавление начинается со дня после крайней даты документов в базе."""
    _run_seed(
        tmp_path,
        [
            "--from", "2026-09-01",
            "--to", "2026-09-02",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "1-1",
            "--sources", "3",
            "--seed", "42",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            departments_before = session.query(Department).count()
            sources_before = session.query(Source).count()
    finally:
        db.close()

    _run_add(
        tmp_path,
        [
            "--to", "2026-09-04",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "1-1",
            "--seed", "7",
        ],
    )

    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            # ОШС и источники не создаются заново.
            assert session.query(Department).count() == departments_before
            assert session.query(Source).count() == sources_before
            materials = session.query(ScientificMaterial).all()
            telegrams = session.query(Telegram).all()
            assert len(materials) == 4
            assert len(telegrams) == 4
            # Документы покрывают оба периода без разрыва и наложения.
            assert {m.outgoing_date for m in materials} == {
                date(2026, 9, 1),
                date(2026, 9, 2),
                date(2026, 9, 3),
                date(2026, 9, 4),
            }
            # Нумерация продолжает годовые счётчики.
            new_materials = [
                m
                for m in materials
                if m.outgoing_date > date(2026, 9, 2)
            ]
            assert sorted(m.outgoing_number for m in new_materials) == [
                "ИСХ-00003",
                "ИСХ-00004",
            ]
            new_telegrams = [
                t for t in telegrams if t.outgoing_date > date(2026, 9, 2)
            ]
            assert sorted(t.outgoing_number for t in new_telegrams) == [
                "ТЛГ-00003",
                "ТЛГ-00004",
            ]
            # Новые документы ссылаются на имеющиеся источники филиала.
            assert all(len(m.sources) <= 2 for m in new_materials)
    finally:
        db.close()


def test_add_requires_structure_and_documents(tmp_path: Path) -> None:
    """Без ОШС или документов скрипт отказывает с понятной ошибкой."""
    _ensure_references(tmp_path, branches=1)
    with pytest.raises(BranchSeedError, match="организационно-штатной структуры"):
        seed_branch_add_4.main(
            [
                "--db-url", f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
                "--storage", (tmp_path / "storage").as_posix(),
                "--to", "2026-09-05",
                "--seed", "1",
            ]
        )

    # Структура без документов: начало периода не определить.
    _run_seed(
        tmp_path,
        [
            "--from", "2026-09-01",
            "--to", "2026-09-02",
            "--materials-per-day", "0-0",
            "--telegrams-per-day", "0-0",
            "--sources", "0",
            "--seed", "2",
        ],
    )
    with pytest.raises(BranchSeedError, match="нет документов"):
        seed_branch_add_4.main(
            [
                "--db-url", f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
                "--storage", (tmp_path / "storage").as_posix(),
                "--to", "2026-09-05",
                "--seed", "1",
            ]
        )


def test_add_rejects_end_before_derived_start(tmp_path: Path) -> None:
    """Дата --to раньше производного начала периода — ошибка."""
    _run_seed(
        tmp_path,
        [
            "--from", "2026-09-01",
            "--to", "2026-09-02",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "0-0",
            "--seed", "3",
        ],
    )
    with pytest.raises(BranchSeedError, match="не раньше"):
        seed_branch_add_4.main(
            [
                "--db-url", f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
                "--storage", (tmp_path / "storage").as_posix(),
                "--to", "2026-09-02",
                "--seed", "1",
            ]
        )
