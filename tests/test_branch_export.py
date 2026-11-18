"""Тесты экспорта по филиалам, meta.json/missing.json и анализа импорта."""

import json
import os
import re
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from internal_correspondence.core.constants import (
    ChangeOperation,
    MaterialType,
    Role,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.importexport.branch_scope import (
    branches_for_change,
    pending_branch_ids,
)
from internal_correspondence.importexport.export_service import (
    ExportError,
    ExportService,
    archive_filename,
)
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.orm.models import (
    Branch,
    Change,
    Country,
    Department,
    Employee,
    Evaluation,
    EvaluationList,
    MissingRequest,
    ScientificMaterial,
    Source,
    TerritorialUnit,
)
from internal_correspondence.services.change_tracking import register_change_tracking


@pytest.fixture(scope="function")
def db_manager(tmp_path: Path):
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_tables()
    yield db
    db.close()


def _storage(tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    storage.mkdir(exist_ok=True)
    return storage


def _setup_two_branches(session) -> None:
    """Два филиала: документы, ОШС первого, справочники."""
    session.add(TerritorialUnit(id="MSK", name="Москва"))
    session.add(
        Branch(id="FIL001", name="Филиал 1", short_name="Ф-1", territorial_unit_id="MSK")
    )
    session.add(
        Branch(id="FIL002", name="Филиал 2", short_name="Ф-2", territorial_unit_id="MSK")
    )
    session.add(Country(id="RUS", name="Россия"))
    session.commit()
    for branch_id, count in (("FIL001", 2), ("FIL002", 1)):
        for index in range(count):
            session.add(
                ScientificMaterial(
                    type=MaterialType.MESSAGE,
                    outgoing_number=f"ИСХ-{branch_id}-{index + 1}",
                    outgoing_date=date(2026, 9, index + 1),
                    name=f"Материал {branch_id}-{index}",
                    branch_id=branch_id,
                )
            )
    department = Department(name="Отдел", branch_id="FIL001")
    department.employees.append(Employee(last_name="Иванов", first_name="Иван"))
    session.add(department)
    session.commit()


def _read_json(archive: Path, name: str) -> dict:
    with zipfile.ZipFile(archive) as zf:
        return json.loads(zf.read(name).decode("utf-8"))


def _changes_for(session, entity_name: str) -> list:
    return (
        session.query(Change).filter(Change.entity_name == entity_name).all()
    )


# --- резолвер «сущность → филиал» ---


def test_branch_scope_resolution(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        material = (
            session.query(ScientificMaterial)
            .filter_by(branch_id="FIL001")
            .first()
        )
        evaluation = Evaluation(
            value=2, date=date(2026, 9, 10), materials=[material]
        )
        evaluation_list = EvaluationList(number="ОЦ-1", date=date(2026, 9, 10))
        evaluation_list.evaluations.append(evaluation)
        session.add(evaluation_list)
        linked_source = Source(
            id=uuid.uuid4(), index="SRC-L", type=0, materials=[material]
        )
        orphan_source = Source(id=uuid.uuid4(), index="SRC-O", type=0)
        session.add_all([linked_source, orphan_source])
        session.commit()

        def resolved(entity_name: str, entity_pk: str):
            change = Change(entity_name=entity_name, entity_pk=entity_pk)
            return branches_for_change(session, change)

        material_change = _changes_for(session, "ScientificMaterial")[0]
        assert branches_for_change(session, material_change) == {"FIL001"}

        department = session.query(Department).one()
        assert resolved("Department", str(department.id)) == {"FIL001"}
        employee = session.query(Employee).one()
        assert resolved("Employee", str(employee.id)) == {"FIL001"}
        assert resolved("Evaluation", str(evaluation.id)) == {"FIL001"}
        assert resolved("EvaluationList", str(evaluation_list.id)) == {"FIL001"}
        assert resolved("Source", str(linked_source.id)) == {"FIL001"}
        assert resolved("Source", str(orphan_source.id)) == set()
        assert resolved("Country", "RUS") is None  # справочник — каждому
        assert resolved("TerritorialUnit", "MSK") is None


def test_pending_branch_ids(db_manager: DatabaseManager) -> None:
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        assert pending_branch_ids(session) == {"FIL001", "FIL002"}

        # После пометки изменений FIL001 экспортированными остаётся FIL002
        for change in session.query(Change).all():
            resolved = branches_for_change(session, change)
            if resolved == {"FIL001"}:
                change.exported_at = datetime(2026, 9, 20)
        session.commit()
        assert pending_branch_ids(session) == {"FIL002"}


# --- экспорт по филиалам ---


def test_export_for_branches_creates_per_branch_archives(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        service = ExportService(
            session, storage, role=Role.HEAD_OFFICE.value, branch_id=None
        )
        outputs = service.export_for_branches(["FIL001", "FIL002"])
        session.commit()

        assert len(outputs) == 2
        names = sorted(path.name for path in outputs)
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}_\d{2}_\d{2} для Ф-1\.zip", names[0]
        ), names
        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}_\d{2}_\d{2} для Ф-2\.zip", names[1]
        ), names

        by_branch = {}
        for output in outputs:
            data = _read_json(output, "export.json")
            for record in data.get("ScientificMaterial", {}).values():
                by_branch.setdefault(record["branch_id"], set()).add(record["name"])

        assert set(by_branch) == {"FIL001", "FIL002"}
        assert len(by_branch["FIL001"]) == 2
        assert len(by_branch["FIL002"]) == 1
        # Справочники (страны) — в каждом архиве.
        for output in outputs:
            assert "Country" in _read_json(output, "export.json")

        # Все изменения помечены экспортированными.
        assert all(
            change.exported_at is not None
            for change in session.query(Change).all()
        )


def test_export_for_single_branch_keeps_other_branch_pending(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        service = ExportService(
            session, storage, role=Role.HEAD_OFFICE.value, branch_id=None
        )
        outputs = service.export_for_branches(["FIL001"])
        session.commit()
        assert len(outputs) == 1

        pending_changes = [
            change
            for change in session.query(Change).all()
            if change.exported_at is None
        ]
        assert pending_changes, "изменения FIL002 должны остаться неэкспортированными"
        for change in pending_changes:
            assert branches_for_change(session, change) in ({"FIL002"}, set())

        # Следующий экспортирует только FIL002: справочники уже ушли,
        # в архиве — только его материал.
        outputs = service.export_for_branches(["FIL002"])
        session.commit()
        data = _read_json(outputs[0], "export.json")
        assert set(data) == {"ScientificMaterial"}


def test_meta_summary_counts_operations(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        # Одно изменение справочника после наполнения: правка страны.
        # Сначала «экспортируем» создание, чтобы правка стала отдельным
        # изменением (иначе операции сливаются в одну запись CREATE).
        country_change = _changes_for(session, "Country")[0]
        country_change.exported_at = datetime(2026, 9, 15)
        country = session.query(Country).one()
        country.name = "Российская Федерация"
        session.commit()

        service = ExportService(
            session, storage, role=Role.HEAD_OFFICE.value, branch_id=None
        )
        output = service.export_for_branches(["FIL001"])[0]
        session.commit()

        meta = _read_json(output, "meta.json")
        summary = meta["summary"]
        assert summary["scientific_materials"] == {"added": 2, "updated": 0, "deleted": 0}
        # Создание страны уже «экспортировано» — в архиве только правка.
        assert summary["countries"] == {"added": 0, "updated": 1, "deleted": 0}
        assert summary["departments"] == {"added": 1, "updated": 0, "deleted": 0}
        assert "pack_id" in meta and "pack_version" in meta


def test_export_branch_names_archive_and_marks_all(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        service = ExportService(
            session,
            storage,
            role=Role.BRANCH.value,
            branch_id="FIL001",
        )
        output = service.export_branch()
        session.commit()

        assert re.fullmatch(
            r"\d{4}-\d{2}-\d{2}_\d{2}_\d{2} от Ф-1\.zip", output.name
        ), output.name
        data = _read_json(output, "export.json")
        # Филиал отправляет все неэкспортированные изменения базы,
        # включая документы других филиалов тестового набора.
        assert {
            record["branch_id"] for record in data["ScientificMaterial"].values()
        } == {"FIL001", "FIL002"}
        assert all(
            change.exported_at is not None
            for change in session.query(Change).all()
        )


def test_export_for_branches_rejects_branch_role(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        service = ExportService(
            session, storage, role=Role.BRANCH.value, branch_id="FIL001"
        )
        with pytest.raises(ExportError):
            service.export_for_branches(["FIL001"])


def test_archive_filename_sanitizes_unsafe_chars() -> None:
    name = archive_filename("2026-11-18_12_00", "для", 'Ф/1:*?"<>|')
    assert name == "2026-11-18_12_00 для Ф_1_______.zip", name


# --- missing.json и запросы контрагенту ---


def test_export_includes_missing_json_and_clears_requests(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        session.add(
            MissingRequest(entity_name="ScientificMaterial", entity_pk=str(uuid.uuid4()))
        )
        session.add(
            MissingRequest(
                branch_id="FIL001",
                entity_name="Telegram",
                entity_pk=str(uuid.uuid4()),
            )
        )
        session.commit()
        assert session.query(MissingRequest).count() == 2

        service = ExportService(
            session,
            storage,
            role=Role.BRANCH.value,
            branch_id="FIL001",
        )
        output = service.export_branch()
        session.commit()

        missing = _read_json(output, "missing.json")
        assert len(missing) == 2
        assert {row["entity_name"] for row in missing} == {
            "ScientificMaterial",
            "Telegram",
        }
        assert any(row["branch_id"] == "FIL001" for row in missing)
        assert any(row["branch_id"] is None for row in missing)
        # Таблица очищена после формирования запроса.
        assert session.query(MissingRequest).count() == 0


# --- анализ импорта ---


def _write_archive(path: Path, payload: dict) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("export.json", json.dumps(payload, ensure_ascii=False))
    return path


def test_analyze_archive_marks_entries(db_manager: DatabaseManager, tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    register_change_tracking()
    db = DatabaseManager(f"sqlite:///{tmp_path / 'target.db'}")
    db.create_tables()
    with db.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(
            Branch(id="FIL001", name="Филиал", short_name="Ф-1", territorial_unit_id="MSK")
        )
        existing = ScientificMaterial(
            type=0,
            outgoing_number="ИСХ-1",
            outgoing_date=date(2026, 1, 1),
            name="Существующий",
            branch_id="FIL001",
        )
        session.add(existing)
        session.commit()

        ok_pk = str(uuid.uuid4())
        delete_pk = str(uuid.uuid4())
        missing_required_pk = str(uuid.uuid4())
        missing_dep_pk = str(uuid.uuid4())
        update_pk = str(existing.id)
        archive = _write_archive(
            tmp_path / "incoming.zip",
            {
                "ScientificMaterial": {
                    ok_pk: {
                        "type": 0,
                        "outgoing_number": "1",
                        "outgoing_date": "2026-01-01",
                        "name": "Новый",
                        "branch_id": "FIL001",
                    },
                    missing_required_pk: {"type": 0, "name": "Без номера"},
                    missing_dep_pk: {
                        "type": 0,
                        "outgoing_number": "2",
                        "outgoing_date": "2026-01-02",
                        "name": "Чужой филиал",
                        "branch_id": "FIL404",
                    },
                    delete_pk: {"deleted": True},
                    # Изменение существующей записи без обязательных полей:
                    # для update проверка обязательных полей не выполняется.
                    update_pk: {"comment": "Уточнённый комментарий"},
                },
                "UnknownEntity": {"k1": {}},
            },
        )

        service = ImportService(
            session, storage, Role.HEAD_OFFICE.value, None
        )
        analysis = service.analyze_archive(archive)
        entries = {(e["pk"]): e for e in analysis["entries"]}

        assert entries[ok_pk]["status"] == "ok"
        assert entries[ok_pk]["operation"] == "create"

        assert entries[update_pk]["status"] == "ok"
        assert entries[update_pk]["operation"] == "update"

        assert entries[delete_pk]["status"] == "warning"
        assert entries[delete_pk]["operation"] == "delete"

        assert entries[missing_required_pk]["status"] == "error"
        assert "обязательные поля" in entries[missing_required_pk]["reason"]

        assert entries[missing_dep_pk]["status"] == "error"
        assert "не найдены зависимости" in entries[missing_dep_pk]["reason"]

        unknown = entries["k1"]
        assert unknown["status"] == "error"
        assert unknown["entity_name"] == "UnknownEntity"

        # Запросы контрагенту: только «не найден»-записи.
        recorded = service.record_missing_requests(list(entries.values()))
        assert recorded == 1
        request = session.query(MissingRequest).one()
        assert request.entity_name == "ScientificMaterial"
        assert request.entity_pk == missing_dep_pk
        assert request.branch_id is None  # головной офис

        # Импорт с исключением «красных» и «жёлтых»: зелёные применяются.
        exclude = {
            (e["entity_name"], e["pk"])
            for e in entries.values()
            if e["status"] in ("warning", "error")
        }
        result = service.import_archive(archive, exclude=exclude)
        assert result["imported"] == 2
        # Пропущены: warning + 2 error по известным сущностям;
        # неизвестная сущность игнорируется молча (до проверки exclude).
        assert result["skipped"] == 3
        material = session.get(ScientificMaterial, uuid.UUID(ok_pk))
        assert material is not None
        assert material.name == "Новый"
        assert session.get(ScientificMaterial, uuid.UUID(missing_dep_pk)) is None
        updated = session.get(ScientificMaterial, uuid.UUID(update_pk))
        assert updated.comment == "Уточнённый комментарий"
        session.commit()
    db.close()


def test_record_missing_requests_sets_branch_for_branch_role(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    with db_manager.get_session() as session:
        _setup_two_branches(session)
        session.commit()
        service = ImportService(
            session, storage, Role.BRANCH.value, "FIL001"
        )
        entries = [
            {
                "entity_name": "ScientificMaterial",
                "pk": str(uuid.uuid4()),
                "status": "error",
                "reason": "не найдены зависимости: branch_id",
            },
            {
                "entity_name": "ScientificMaterial",
                "pk": str(uuid.uuid4()),
                "status": "error",
                "reason": "пропущены обязательные поля: name",
            },
            {
                "entity_name": "ScientificMaterial",
                "pk": str(uuid.uuid4()),
                "status": "ok",
                "reason": "",
            },
        ]
        assert service.record_missing_requests(entries) == 1
        request = session.query(MissingRequest).one()
        assert request.branch_id == "FIL001"


def test_analyze_archive_of_real_export_is_all_ok(
    db_manager: DatabaseManager, tmp_path: Path
) -> None:
    storage = _storage(tmp_path)
    target = DatabaseManager(f"sqlite:///{tmp_path / 'target.db'}")
    target.create_tables()
    try:
        with db_manager.get_session() as session:
            _setup_two_branches(session)
            service = ExportService(session, storage)
            output = service.export()
            session.commit()

        with target.get_session() as session:
            service = ImportService(session, storage, Role.HEAD_OFFICE.value, None)
            analysis = service.analyze_archive(output)
            assert analysis["entries"]
            assert all(
                entry["status"] == "ok" for entry in analysis["entries"]
            ), [e for e in analysis["entries"] if e["status"] != "ok"]
    finally:
        target.close()


def test_import_preview_dialog_renders_entries() -> None:
    """Превью импорта отображает записи со статусами и отдаёт ключи-исключения."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    from internal_correspondence.gui.exchange_dialogs import ImportPreviewDialog

    app = QApplication.instance() or QApplication([])
    entries = [
        {
            "entity_name": "ScientificMaterial",
            "entity_label": "Научный материал",
            "pk": "pk-1",
            "operation": "create",
            "status": "ok",
            "reason": "",
        },
        {
            "entity_name": "ScientificMaterial",
            "entity_label": "Научный материал",
            "pk": "pk-2",
            "operation": "delete",
            "status": "warning",
            "reason": "запись для удаления не найдена",
        },
        {
            "entity_name": "Telegram",
            "entity_label": "Телеграмма",
            "pk": "pk-3",
            "operation": "update",
            "status": "error",
            "reason": "не найдены зависимости",
        },
    ]
    dialog = ImportPreviewDialog(entries)
    assert dialog._table.rowCount() == 3
    # Текст статусов заполнен для всех строк (регрессия: строка словаря
    # не должна вызываться как callable).
    for row in range(3):
        assert dialog._table.item(row, 3).text()
    assert dialog.excluded_keys(entries) == {
        ("ScientificMaterial", "pk-2"),
        ("Telegram", "pk-3"),
    }
    dialog.close()
