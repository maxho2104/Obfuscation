"""Тесты скрипта наполнения базы данными филиала (``tests.seed_branch``)."""

import re
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

import pytest

from internal_correspondence.core.constants import MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.orm.models import (
    Branch,
    Department,
    FileRecord,
    ReportAddress,
    ScientificMaterial,
    Source,
    Telegram,
)
from tests import seed_branch


def _run_seed(tmp_path: Path, extra: List[str]) -> None:
    """Запускает seed_branch с базой и хранилищем во временном каталоге."""
    argv = [
        "--db-url", f"sqlite:///{(tmp_path / 'seed.db').as_posix()}",
        "--storage", (tmp_path / "storage").as_posix(),
    ] + extra
    assert seed_branch.main(argv) == 0


def _open_db(tmp_path: Path) -> DatabaseManager:
    db = DatabaseManager(f"sqlite:///{(tmp_path / 'seed.db').as_posix()}")
    return db


def test_generates_documents_with_yearly_counters(tmp_path: Path) -> None:
    _run_seed(
        tmp_path,
        [
            "--branch", "Ф-Т",
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
            branch = session.query(Branch).filter_by(short_name="Ф-Т").one()
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
            "--branch", "Ф-Г",
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
            "--branch", "Ф-Р",
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
            "--branch", "Ф-И",
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
            assert all(re.fullmatch(r"SRC-\d{5}", idx) for idx in indexes)
    finally:
        db.close()


def test_attach_files_when_requested(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    _run_seed(
        tmp_path,
        [
            "--branch", "Ф-Ф",
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


def test_generates_new_branch_when_not_specified(tmp_path: Path) -> None:
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
    _run_seed(
        tmp_path,
        [
            "--from", "2026-09-01",
            "--to", "2026-09-02",
            "--materials-per-day", "1-1",
            "--telegrams-per-day", "0-0",
            "--seed", "6",
        ],
    )
    db = _open_db(tmp_path)
    try:
        with db.get_session() as session:
            branches = session.query(Branch).order_by(Branch.id).all()
            assert len(branches) == 2
            assert branches[0].short_name == "Ф-1"
            assert branches[1].short_name == "Ф-2"
            # Справочники не продублировались.
            from internal_correspondence.orm.models import Country
            assert session.query(Country).count() == 10
    finally:
        db.close()


def test_documents_always_have_countries_and_employees(tmp_path: Path) -> None:
    """Страны и сотрудники — обязательные поля: сидирование заполняет всегда."""
    _run_seed(
        tmp_path,
        [
            "--branch", "Ф-О",
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
