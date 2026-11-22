"""Тесты первоначальной загрузки филиала из архива головного офиса."""

import json
import uuid
import zipfile
from pathlib import Path

import pytest

from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.importexport.branch_import import (
    InitialBranchImport,
    exclude_set_for_branch,
    read_archive_branches,
    run_initial_import,
)
from internal_correspondence.services.change_tracking import register_change_tracking


def _pk(name: str) -> str:
    """Детерминированный UUID-идентификатор для тестовой записи."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"branch-import-test/{name}"))


@pytest.fixture()
def archive_data() -> tuple:
    """Модель export.json с данными двух филиалов и словарь ключей."""
    ids = {
        key: _pk(key)
        for key in (
            "D1", "D2", "G1", "G2", "E1", "E2", "M1", "M2",
            "MAT1", "MAT2", "TLG1", "S1", "S2", "F1", "F2",
            "EV1", "EV2", "RA1", "EL1", "EL2", "AT1", "AT2", "AT3", "AT4",
        )
    }
    data = {
        "Branch": {
            "BR-1": {
                "name": "Филиал 1",
                "short_name": "Ф-1",
                "territorial_unit_id": "TU-1",
            },
            "BR-2": {
                "name": "Филиал 2",
                "short_name": "Ф-2",
                "territorial_unit_id": "TU-1",
            },
            "BR-3": {"deleted": True},
        },
        "TerritorialUnit": {"TU-1": {"name": "Регион"}},
        "Country": {"RUS": {"name": "Россия"}},
        "Leader": {"LEAD-1": {"active": True}},
        "ScientificTask": {
            "TASK-0001": {"name": "Задача", "type": 1, "start_date": "2025-01-01"}
        },
        "AddedTask": {
            ids["AT1"]: {
                "task_id": "TASK-0001", "node_type": "branch", "node_id": "BR-1"
            },
            ids["AT2"]: {
                "task_id": "TASK-0001", "node_type": "branch", "node_id": "BR-2"
            },
            ids["AT3"]: {
                "task_id": "TASK-0001", "node_type": "region", "node_id": "TU-1"
            },
            ids["AT4"]: {
                "task_id": "TASK-0001", "node_type": "region", "node_id": "TU-2"
            },
        },
        "Department": {
            ids["D1"]: {"branch_id": "BR-1", "name": "Отдел 1", "active": True},
            ids["D2"]: {"branch_id": "BR-2", "name": "Отдел 2", "active": True},
        },
        "WorkingGroup": {
            ids["G1"]: {
                "department_id": ids["D1"], "name": "Группа 1", "active": True
            },
            ids["G2"]: {
                "department_id": ids["D2"], "name": "Группа 2", "active": True
            },
        },
        "Employee": {
            ids["E1"]: {
                "department_id": ids["D1"],
                "last_name": "Иванов",
                "first_name": "Иван",
                "active": True,
            },
            ids["E2"]: {
                "department_id": ids["D2"],
                "last_name": "Петров",
                "first_name": "Пётр",
                "active": True,
            },
        },
        "WorkGroupMembership": {
            ids["M1"]: {"employee_id": ids["E1"], "working_group_id": ids["G1"]},
            ids["M2"]: {"employee_id": ids["E2"], "working_group_id": ids["G2"]},
        },
        "ScientificMaterial": {
            ids["MAT1"]: {
                "branch_id": "BR-1",
                "type": 1,
                "name": "Материал 1",
                "files": [ids["F1"]],
                "sources": [ids["S1"]],
            },
            ids["MAT2"]: {
                "branch_id": "BR-2",
                "type": 1,
                "name": "Материал 2",
                "files": [ids["F2"]],
            },
        },
        "Telegram": {
            ids["TLG1"]: {"branch_id": "BR-1", "type": 1, "name": "Телеграмма 1"}
        },
        "Source": {
            ids["S1"]: {"index": "SRC-1", "type": 1},
            ids["S2"]: {"index": "SRC-2", "type": 1},
        },
        "FileRecord": {
            ids["F1"]: {"name": "a", "extension": "txt", "path": "Файлы"},
            ids["F2"]: {"name": "b", "extension": "txt", "path": "Файлы"},
        },
        "Evaluation": {
            ids["EV1"]: {
                "value": 1, "date": "2026-02-01", "materials": [ids["MAT1"]]
            },
            ids["EV2"]: {
                "value": 1, "date": "2026-02-01", "materials": [ids["MAT2"]]
            },
        },
        "ReportAddress": {
            ids["RA1"]: {
                "telegram_id": ids["TLG1"], "leader_id": "LEAD-1", "report_date": None
            },
        },
        "EvaluationList": {
            ids["EL1"]: {
                "number": "ОЦ-1", "date": "2026-02-01", "evaluations": [ids["EV1"]]
            },
            ids["EL2"]: {
                "number": "ОЦ-2", "date": "2026-02-01", "evaluations": [ids["EV2"]]
            },
        },
        "UnknownFuture": {"X1": {"foo": "bar"}},
    }
    return data, ids


def test_exclude_set_keeps_selected_branch_and_references(archive_data) -> None:
    """Справочники и данные выбранного филиала не исключаются."""
    data, ids = archive_data
    exclude = exclude_set_for_branch(data, "BR-1")
    for entity, pk in (
        ("TerritorialUnit", "TU-1"),
        ("Country", "RUS"),
        ("Leader", "LEAD-1"),
        ("ScientificTask", "TASK-0001"),
        ("AddedTask", ids["AT1"]),
        ("AddedTask", ids["AT3"]),
        ("Department", ids["D1"]),
        ("WorkingGroup", ids["G1"]),
        ("Employee", ids["E1"]),
        ("WorkGroupMembership", ids["M1"]),
        ("ScientificMaterial", ids["MAT1"]),
        ("Telegram", ids["TLG1"]),
        ("Source", ids["S1"]),
        ("FileRecord", ids["F1"]),
        ("Evaluation", ids["EV1"]),
        ("ReportAddress", ids["RA1"]),
        ("EvaluationList", ids["EL1"]),
    ):
        assert (entity, pk) not in exclude, entity


def test_exclude_set_drops_other_branch_data(archive_data) -> None:
    """Данные чужого филиала и неатрибутируемые сущности исключаются."""
    data, ids = archive_data
    exclude = exclude_set_for_branch(data, "BR-1")
    for entity, pk in (
        ("Department", ids["D2"]),
        ("WorkingGroup", ids["G2"]),
        ("Employee", ids["E2"]),
        ("WorkGroupMembership", ids["M2"]),
        ("ScientificMaterial", ids["MAT2"]),
        ("Source", ids["S2"]),
        ("FileRecord", ids["F2"]),
        ("Evaluation", ids["EV2"]),
        ("EvaluationList", ids["EL2"]),
        ("AddedTask", ids["AT2"]),
        ("AddedTask", ids["AT4"]),
    ):
        assert (entity, pk) in exclude, entity
    # Удалённые записи филиалов не участвуют в выборе, но и не мешают
    assert ("Branch", "BR-3") not in exclude
    # Неизвестные сущности в пустую базу не тянем
    assert ("UnknownFuture", "X1") in exclude


def _write_archive(path: Path, export_data: dict) -> Path:
    """Пишет экспортный архив с заданным export.json."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "export.json", json.dumps(export_data, ensure_ascii=False)
        )
        archive.writestr(
            "meta.json", json.dumps({"pack_id": "test", "pack_version": 1})
        )
    return path


def test_read_archive_branches_skips_deleted(archive_data, tmp_path: Path) -> None:
    """Список филиалов архива читается из export.json без удалённых записей."""
    data, _ids = archive_data
    archive = _write_archive(tmp_path / "export.zip", data)
    branches = read_archive_branches(archive)
    assert branches == [("BR-1", "Филиал 1"), ("BR-2", "Филиал 2")]


@pytest.fixture()
def db(tmp_path: Path) -> DatabaseManager:
    """Временная SQLite с зарегистрированным трекингом изменений."""
    register_change_tracking()
    manager = DatabaseManager(f"sqlite:///{tmp_path / 'branch.db'}")
    manager.create_tables()
    yield manager
    manager.close()


def test_run_initial_import_loads_only_selected_branch(
    archive_data, db: DatabaseManager, tmp_path: Path
) -> None:
    """Архив применяется к пустой базе: остаётся выбранный филиал и справочники."""
    from internal_correspondence.orm.models import (
        Branch,
        Country,
        Department,
        Employee,
        Evaluation,
        EvaluationList,
        FileRecord,
        ReportAddress,
        ScientificMaterial,
        Source,
        Telegram,
    )

    data, _ids = archive_data
    archive = _write_archive(tmp_path / "export.zip", data)
    storage = tmp_path / "storage"
    storage.mkdir()
    with db.get_session() as session:
        result = run_initial_import(
            session,
            storage,
            InitialBranchImport(archive_path=archive, branch_id="BR-1"),
        )
        session.commit()
    assert result["imported"] > 0

    with db.get_session() as session:
        # Филиалы — справочник: уходят в базу целиком
        assert {branch.id for branch in session.query(Branch)} == {"BR-1", "BR-2"}
        assert session.query(Country).count() == 1
        assert {dept.name for dept in session.query(Department)} == {"Отдел 1"}
        assert session.query(Employee).count() == 1
        materials = session.query(ScientificMaterial).all()
        assert len(materials) == 1
        assert materials[0].branch_id == "BR-1"
        assert session.query(Telegram).count() == 1
        assert session.query(Source).count() == 1
        assert session.query(FileRecord).count() == 1
        assert session.query(Evaluation).count() == 1
        assert session.query(EvaluationList).count() == 1
        assert session.query(ReportAddress).count() == 1
