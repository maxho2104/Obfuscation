"""Полный цикл обмена: головной офис и три филиала.

Сценарий (по описанию полного цикла):
1. Головной офис (GO.db, хранилище «Головной офис»): справочники
   (территориальные единицы, три филиала, страны, звания, потребители,
   руководители) → экспортный файл для каждого филиала.
2. Для каждого филиала: создание базы и хранилища → приём справочников →
   генерация данных филиала (tests.seed_branch, с файлами-вложениями) →
   экспортный файл филиала.
3. Головной офис: приём файлов филиалов → регистрация документов и оценки
   (tests.seed_head_office) → экспортный файл для каждого филиала.
4. Каждый филиал принимает свой файл от головного офиса.

Успех: записи филиала и головного офиса синхронизированы (входящие номера
и даты, оценки, типы и адресация докладов), конфликтов при импорте нет.
"""

import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from faker import Faker

from internal_correspondence.core.constants import Role
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.importexport.export_service import ExportService
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.orm.models import (
    Branch,
    Country,
    ScientificMaterial,
    Telegram,
)
from internal_correspondence.services.change_tracking import register_change_tracking
from tests import seed_branch, seed_head_office
from tests.seed_branch import _ensure_reference_data

BRANCHES: List[Tuple[str, str]] = [
    ("BR-001", "Ф-1"),
    ("BR-002", "Ф-2"),
    ("BR-003", "Ф-3"),
]
PERIOD = ("2026-09-01", "2026-09-10")


@pytest.fixture(scope="module")
def cycle(tmp_path_factory) -> Path:
    """Выполняет полный цикл обмена; возвращает корень временного каталога."""
    register_change_tracking()
    root = tmp_path_factory.mktemp("full_cycle")
    archives = root / "archives"
    archives.mkdir()
    hq_db_url, hq_storage = _paths(root, "GO.db", "Головной офис")
    branch_urls = {
        branch_id: _paths(root, f"{short}.db", short)
        for branch_id, short in BRANCHES
    }

    reference_zips = _step1_head_office_reference(root, archives, hq_db_url, hq_storage)
    branch_zips = _step2_branches(root, archives, branch_urls, reference_zips)
    office_zips = _step3_head_office_registration(
        root, archives, hq_db_url, hq_storage, branch_zips
    )
    _step4_branches_receive(branch_urls, office_zips)
    return root


def _paths(root: Path, db_name: str, storage_name: str) -> Tuple[str, Path]:
    storage = root / "Файловое хранилище" / storage_name
    storage.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(root / db_name).as_posix()}", storage


def _hq_service(session, storage: Path) -> ExportService:
    return ExportService(
        session, storage, role=Role.HEAD_OFFICE.value, branch_id=None
    )


def _import_zip(
    db_url: str, storage: Path, role: str, branch_id, archive: Path
) -> dict:
    db = DatabaseManager(db_url)
    try:
        with db.get_session() as session:
            service = ImportService(session, storage, role, branch_id)
            result = service.import_archive(archive)
            session.commit()
            return result
    finally:
        db.close()


# --- шаги цикла ---


def _step1_head_office_reference(
    root: Path, archives: Path, hq_db_url: str, hq_storage: Path
) -> Dict[str, Path]:
    """Головной офис заполняет справочники и выгружает их для филиалов."""
    db = DatabaseManager(hq_db_url)
    db.create_tables()
    fake = Faker("ru_RU")
    try:
        with db.get_session() as session:
            _ensure_reference_data(session, fake, 3, date.today())
            for index, (_branch_id, short) in enumerate(BRANCHES, start=1):
                session.add(
                    Branch(
                        id=f"BR-{index:03d}",
                        name=f"Филиал «{fake.company()}»",
                        short_name=short,
                        territorial_unit_id="TU-001",
                    )
                )
            session.commit()
            service = _hq_service(session, hq_storage)
            outputs = service.export_for_branches([b for b, _s in BRANCHES])
            session.commit()
    finally:
        db.close()
    return {
        branch_id: _move(output, archives / f"refs-{short}.zip")
        for (branch_id, short), output in zip(BRANCHES, outputs)
    }


def _move(source: Path, target: Path) -> Path:
    source.replace(target)
    return target


def _step2_branches(
    root: Path,
    archives: Path,
    branch_urls: Dict[str, Tuple[str, Path]],
    reference_zips: Dict[str, Path],
) -> Dict[str, Path]:
    """Филиалы принимают справочники, генерируют данные и выгружаются."""
    branch_zips: Dict[str, Path] = {}
    for index, (branch_id, short) in enumerate(BRANCHES, start=1):
        db_url, storage = branch_urls[branch_id]
        db = DatabaseManager(db_url)
        db.create_tables()
        db.close()

        result = _import_zip(
            db_url, storage, Role.BRANCH.value, branch_id, reference_zips[branch_id]
        )
        assert result["conflicts"] == [], result["conflicts"]
        reference_zips[branch_id].unlink()

        assert seed_branch.main(
            [
                "--db-url", db_url,
                "--storage", storage.as_posix(),
                "--branch", short,
                "--from", PERIOD[0],
                "--to", PERIOD[1],
                "--materials-per-day", "1-2",
                "--telegrams-per-day", "0-1",
                "--sources", "5",
                "--with-files",
                "--seed", str(index),
            ]
        ) == 0

        db = DatabaseManager(db_url)
        try:
            with db.get_session() as session:
                service = ExportService(
                    session,
                    storage,
                    role=Role.BRANCH.value,
                    branch_id=branch_id,
                )
                output = service.export_branch()
                session.commit()
        finally:
            db.close()
        branch_zips[branch_id] = _move(output, archives / f"branch-{short}.zip")
    return branch_zips


def _step3_head_office_registration(
    root: Path,
    archives: Path,
    hq_db_url: str,
    hq_storage: Path,
    branch_zips: Dict[str, Path],
) -> Dict[str, Path]:
    """Головной офис принимает данные филиалов, регистрирует и оценивает."""
    for branch_id, _short in BRANCHES:
        result = _import_zip(
            hq_db_url, hq_storage, Role.HEAD_OFFICE.value, None, branch_zips[branch_id]
        )
        assert result["conflicts"] == [], result["conflicts"]
        branch_zips[branch_id].unlink()

    assert seed_head_office.main(
        [
            "--db-url", hq_db_url,
            "--storage", hq_storage.as_posix(),
            "--seed", "9",
        ]
    ) == 0

    db = DatabaseManager(hq_db_url)
    try:
        with db.get_session() as session:
            service = _hq_service(session, hq_storage)
            outputs = service.export_for_branches([b for b, _s in BRANCHES])
            session.commit()
    finally:
        db.close()
    return {
        branch_id: _move(output, archives / f"office-{short}.zip")
        for (branch_id, short), output in zip(BRANCHES, outputs)
    }


def _step4_branches_receive(
    branch_urls: Dict[str, Tuple[str, Path]],
    office_zips: Dict[str, Path],
) -> None:
    """Филиалы принимают изменения головного офиса."""
    for branch_id, _short in BRANCHES:
        db_url, storage = branch_urls[branch_id]
        result = _import_zip(
            db_url, storage, Role.BRANCH.value, branch_id, office_zips[branch_id]
        )
        assert result["conflicts"] == [], result["conflicts"]
        office_zips[branch_id].unlink()


# --- проверки синхронизации ---


def _snapshot(db_url: str, branch_id: str) -> dict:
    db = DatabaseManager(db_url)
    try:
        with db.get_session() as session:
            materials = (
                session.query(ScientificMaterial)
                .filter_by(branch_id=branch_id)
                .order_by(ScientificMaterial.outgoing_number)
                .all()
            )
            material_rows = {
                m.outgoing_number: (
                    m.incoming_number,
                    m.incoming_date,
                    None
                    if m.latest_evaluation is None
                    else (int(m.latest_evaluation.value), m.latest_evaluation.date),
                    m.consumer_id,
                    m.comment,
                )
                for m in materials
            }
            telegrams = (
                session.query(Telegram)
                .filter_by(branch_id=branch_id)
                .order_by(Telegram.outgoing_number)
                .all()
            )
            telegram_rows = {
                t.outgoing_number: (
                    t.incoming_number,
                    t.incoming_date,
                    t.report_type,
                    None
                    if t.latest_evaluation is None
                    else (int(t.latest_evaluation.value), t.latest_evaluation.date),
                    sorted(
                        address.report_date
                        for address in t.report_addresses
                    ),
                )
                for t in telegrams
            }
            return {"materials": material_rows, "telegrams": telegram_rows}
    finally:
        db.close()


def _db_url(root: Path, name: str) -> str:
    return f"sqlite:///{(root / name).as_posix()}"


@pytest.mark.parametrize("branch_id,short", BRANCHES)
def test_cycle_synchronizes_documents(cycle: Path, branch_id: str, short: str) -> None:
    """После цикла записи филиала и головного офиса совпадают."""
    hq = _snapshot(_db_url(cycle, "GO.db"), branch_id)
    branch = _snapshot(_db_url(cycle, f"{short}.db"), branch_id)

    assert branch["materials"], "в филиале должны быть материалы"
    assert hq["materials"] == branch["materials"]
    assert hq["telegrams"] == branch["telegrams"]

    # Все материалы зарегистрированы и оценены головным офисом.
    for incoming_number, incoming_date, evaluation, _consumer, _comment in (
        branch["materials"].values()
    ):
        assert incoming_number is not None
        assert incoming_date is not None
        assert evaluation is not None


def test_cycle_imports_references(cycle: Path) -> None:
    """Справочники доехали до филиалов."""
    for _branch_id, short in BRANCHES:
        db = DatabaseManager(_db_url(cycle, f"{short}.db"))
        try:
            with db.get_session() as session:
                assert session.query(Branch).count() == len(BRANCHES)
                assert session.query(Country).count() == 10
        finally:
            db.close()
