"""Тесты отображения прикреплённых файлов."""

import os
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from internal_correspondence.gui.attached_files_widget import AttachedFilesWidget
from internal_correspondence.orm.models import FileRecord


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _record(name: str, extension: str, path: Path) -> FileRecord:
    return FileRecord(
        id=uuid.uuid4(),
        name=name,
        extension=extension,
        path=str(path).replace("\\", "/"),
    )


def test_attached_files_show_icons_and_mark_broken_links(qt_app, tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    relative_dir = Path("Файлы") / "docs"
    target_dir = storage / relative_dir
    target_dir.mkdir(parents=True)
    (target_dir / "present.txt").write_text("data", encoding="utf-8")

    widget = AttachedFilesWidget(storage)
    widget.set_files(
        [
            _record("present", "txt", relative_dir),
            _record("missing", "txt", relative_dir),
        ]
    )

    assert widget.list_widget.count() == 2
    present_item = widget.list_widget.item(0)
    missing_item = widget.list_widget.item(1)

    assert not present_item.icon().isNull()
    assert not missing_item.icon().isNull()
    assert not present_item.font().strikeOut()
    assert missing_item.font().strikeOut()
    assert "отсутствует" in missing_item.toolTip()
