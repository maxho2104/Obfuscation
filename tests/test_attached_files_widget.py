"""Тесты док-виджета прикреплённых файлов и файловых операций сервиса."""

import os
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from internal_correspondence.core.constants import MaterialType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.domain_pack import dir_name
from internal_correspondence.gui.attached_files_widget import (
    AttachedFilesWidget,
    CopyFilesWorker,
    _explorer_select_command,
)
from internal_correspondence.orm.models import (
    Branch,
    FileRecord,
    ScientificMaterial,
    TerritorialUnit,
)
from internal_correspondence.services.document_service import ScientificMaterialService
from internal_correspondence.services.file_service import (
    FileCopyCancelled,
    cleanup_empty_dirs,
    copy_with_progress,
    is_inside_storage,
    unique_target_path,
)
from internal_correspondence.utils.string_resources import STRINGS


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="function")
def env(tmp_path: Path):
    db = DatabaseManager(f"sqlite:///{tmp_path / 'files.db'}")
    db.create_tables()
    storage = tmp_path / "storage"
    storage.mkdir()
    with db.get_session() as session:
        session.add(TerritorialUnit(id="TU", name="Единица"))
        session.add(Branch(id="F1", name="Филиал 1", short_name="Ф1", territorial_unit_id="TU"))
        material = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-1",
            outgoing_date=date(2026, 3, 1),
            name="Материал",
            branch_id="F1",
        )
        session.add(material)
        session.commit()
        material_id = material.id
    yield db, storage, material_id
    db.close()


def _get_material(db, material_id):
    session = db.get_session()
    return session.get(ScientificMaterial, material_id), session


# ---------------------------------------------------------------------------
# Файловые примитивы
# ---------------------------------------------------------------------------


def test_unique_target_path(tmp_path: Path) -> None:
    """Генерация имени с порядковым номером в скобках (как в Windows)."""
    target_dir = tmp_path / "docs"
    target_dir.mkdir()
    (target_dir / "file.doc").write_text("1", encoding="utf-8")
    (target_dir / "file(1).doc").write_text("2", encoding="utf-8")

    assert unique_target_path(target_dir, "other.txt").name == "other.txt"
    assert unique_target_path(target_dir, "file.doc").name == "file(2).doc"


def test_copy_with_progress_and_cancel(tmp_path: Path) -> None:
    """Поблочное копирование копирует данные; отмена удаляет частичный файл."""
    source = tmp_path / "source.bin"
    source.write_bytes(b"x" * (3 * 1024 * 1024))
    target = tmp_path / "nested" / "target.bin"

    chunks = []
    copy_with_progress(source, target, on_chunk=chunks.append, chunk_size=1024 * 1024)
    assert target.read_bytes() == source.read_bytes()
    assert chunks == [1024 * 1024, 2 * 1024 * 1024, 3 * 1024 * 1024]

    calls = {"count": 0}

    def cancel_after_first_chunk() -> bool:
        calls["count"] += 1
        return calls["count"] > 1

    partial = tmp_path / "partial.bin"
    with pytest.raises(FileCopyCancelled):
        copy_with_progress(
            source, partial, should_cancel=cancel_after_first_chunk,
            chunk_size=1024 * 1024,
        )
    assert not partial.exists()


def test_is_inside_storage(tmp_path: Path) -> None:
    """Проверка принадлежности пути хранилищу."""
    storage = tmp_path / "storage"
    inside = storage / "Файлы" / "a.txt"
    inside.parent.mkdir(parents=True)
    inside.write_text("x", encoding="utf-8")
    assert is_inside_storage(inside, storage)
    assert not is_inside_storage(tmp_path / "outside.txt", storage)


def test_cleanup_empty_dirs(tmp_path: Path) -> None:
    """Пустые папки удаляются вверх до стоп-папки (не включая её)."""
    root = tmp_path / "storage" / dir_name("files") / dir_name("material_files")
    leaf = root / "2026-03-01" / "М-1"
    leaf.mkdir(parents=True)
    (root / "keep.txt").write_text("x", encoding="utf-8")

    cleanup_empty_dirs(leaf, root)
    assert root.exists()
    assert not (root / "2026-03-01").exists()


# ---------------------------------------------------------------------------
# Сервис документов: привязка и отвязка
# ---------------------------------------------------------------------------


def test_attach_copied_and_link_without_duplication(env) -> None:
    """Копирование и привязка: файл вне хранилища копируется, внутри — только связь."""
    db, storage, material_id = env
    material, session = _get_material(db, material_id)
    service = ScientificMaterialService(session, storage)

    # Файл вне хранилища
    outside = storage.parent / "incoming" / "report.pdf"
    outside.parent.mkdir(parents=True)
    outside.write_text("data", encoding="utf-8")
    pairs = service.plan_copy_targets(material, [outside])
    assert len(pairs) == 1
    source, target = pairs[0]
    copy_with_progress(source, target)
    service.attach_copied_files(material, pairs)

    # Файл внутри хранилища — без копирования
    inside = storage / dir_name("files") / dir_name("material_files") / "old" / "legacy.txt"
    inside.parent.mkdir(parents=True)
    inside.write_text("old", encoding="utf-8")
    service.link_existing_files(material, [inside])

    session.commit()
    assert len(material.files) == 2
    record_names = sorted(f"{r.name}.{r.extension}" for r in material.files)
    assert record_names == ["legacy.txt", "report.pdf"]
    # Папка по номеру и дате документа
    assert target.parent.name == "М-1"
    assert target.parent.parent.name == "2026-03-01"
    session.close()


def test_link_existing_reuses_record(env) -> None:
    """Повторная привязка того же файла не создаёт дубль записи."""
    db, storage, material_id = env
    material, session = _get_material(db, material_id)
    service = ScientificMaterialService(session, storage)
    inside = storage / dir_name("files") / dir_name("material_files") / "old" / "shared.txt"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text("x", encoding="utf-8")

    first = service.link_existing_files(material, [inside])[0]
    second = service.link_existing_files(material, [inside])[0]
    session.commit()
    assert first is second
    session.close()


def test_detach_removes_unshared_file_and_empty_dirs(env) -> None:
    """Отвязка удаляет с диска файл, не разделённый с другими записями."""
    db, storage, material_id = env
    material, session = _get_material(db, material_id)
    service = ScientificMaterialService(session, storage)

    target_dir = storage / dir_name("files") / dir_name("material_files") / "2026-03-01" / "М-1"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "temp.txt"
    target.write_text("x", encoding="utf-8")
    pairs = [(target, target)]
    record = service.attach_copied_files(material, pairs)[0]
    session.commit()

    service.detach_files(material, [record])
    session.commit()

    assert not target.exists()
    assert not target_dir.exists()
    # Корневая папка типа документа сохраняется
    assert (storage / dir_name("files") / dir_name("material_files")).exists()
    assert session.get(FileRecord, record.id) is None
    session.close()


def test_detach_keeps_shared_file(env) -> None:
    """Разделённый с другой записью файл при отвязке с диска не удаляется."""
    db, storage, material_id = env
    material, session = _get_material(db, material_id)
    service = ScientificMaterialService(session, storage)

    target = storage / dir_name("files") / dir_name("material_files") / "2026-03-01" / "М-1" / "shared.doc"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")
    record = service.attach_copied_files(material, [(target, target)])[0]

    second = ScientificMaterial(
        type=MaterialType.MESSAGE,
        outgoing_number="М-2",
        outgoing_date=date(2026, 3, 2),
        name="Другой",
        branch_id="F1",
    )
    second.files.append(record)
    session.add(second)
    session.commit()

    service.detach_files(material, [record])
    session.commit()

    assert target.exists()
    assert session.get(FileRecord, record.id) is not None
    assert [r.id for r in second.files] == [record.id]
    session.close()


# ---------------------------------------------------------------------------
# Док-виджет
# ---------------------------------------------------------------------------


def test_dock_shows_document_files_and_marks_broken(env, qapp) -> None:
    """Док показывает файлы записи; битые ссылки выделяются зачёркиванием."""
    db, storage, material_id = env
    material, session = _get_material(db, material_id)
    service = ScientificMaterialService(session, storage)

    target_dir = storage / dir_name("files") / dir_name("material_files") / "2026-03-01" / "М-1"
    target_dir.mkdir(parents=True, exist_ok=True)
    present = target_dir / "present.txt"
    present.write_text("x", encoding="utf-8")
    service.attach_copied_files(
        material, [(present, present), (target_dir / "missing.txt", target_dir / "missing.txt")]
    )
    session.commit()
    session.close()

    dock_session = db.get_session()
    dock = AttachedFilesWidget(dock_session, storage)
    material = dock_session.get(ScientificMaterial, material_id)
    dock.set_document(material)

    assert dock.list_widget.count() == 2
    items = {
        dock.list_widget.item(row).text(): dock.list_widget.item(row)
        for row in range(dock.list_widget.count())
    }
    present_item = items["present.txt"]
    missing_item = items["missing.txt"]
    assert not present_item.font().strikeOut()
    assert missing_item.font().strikeOut()
    assert "отсутствует" in missing_item.toolTip()
    assert "М-1" in dock.header_label.text()
    assert "01.03.2026" in dock.header_label.text()

    dock.set_document(None)
    assert dock.list_widget.count() == 0
    assert dock.header_label.text() == STRINGS.files_no_selection
    dock_session.close()


def test_copy_worker_reports_progress(env, qapp, tmp_path: Path) -> None:
    """Поток копирования отдаёт прогресс и список завершённых пар."""
    db, storage, material_id = env
    source = tmp_path / "doc.txt"
    source.write_text("data", encoding="utf-8")
    target = storage / dir_name("files") / dir_name("material_files") / "2026-03-01" / "М-1" / "doc.txt"

    worker = CopyFilesWorker([(source, target)])
    progressed = []
    finished = []
    worker.progressed.connect(progressed.append)
    worker.finished.connect(finished.append)
    worker.run()

    assert finished == [[(source, target)]]
    assert target.read_text(encoding="utf-8") == "data"
    assert progressed and "doc.txt" in progressed[0]


def test_explorer_select_command_keeps_key_outside_quotes() -> None:
    """Ключ /select, остаётся вне кавычек даже для путей с пробелами."""
    command = _explorer_select_command(
        Path(r"C:\Users\user name\Storage\file.txt")
    )
    assert command == r'explorer /select,"C:\Users\user name\Storage\file.txt"'
    assert command.startswith('explorer /select,"')
