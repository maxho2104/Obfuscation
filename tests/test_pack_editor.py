"""Дымовой тест автономного редактора пакета предметной области."""

import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pack_editor_module():
    """Загружает scripts_dev/pack_editor.py как модуль."""
    spec = importlib.util.spec_from_file_location(
        "pack_editor", PROJECT_ROOT / "scripts_dev" / "pack_editor.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_editor_loads_builtin_and_saves(pack_editor_module, qt_app, tmp_path):
    """Встроенный пакет загружается, правка строки сохраняется и перечитывается."""
    from internal_correspondence.core.domain_pack import load_domain_pack

    window = pack_editor_module.PackEditorWindow()
    assert window._data["id"] == "scientific-network"
    assert window.enums_tab.enum_list.count() > 0
    assert window.strings_tab.table.rowCount() > 0

    # Правим значение первой строки таблицы строк
    item = window.strings_tab.table.item(0, 1)
    original_key = window.strings_tab.table.item(0, 0).text()
    item.setText("Изменённое значение")

    target = tmp_path / "edited_pack.json"
    window._save_to(target)
    assert target.exists()

    pack = load_domain_pack(target)
    assert pack.strings()[original_key] == "Изменённое значение"
    window.deleteLater()


def test_editor_validation_rejects_bad_pack(pack_editor_module, qt_app):
    """Некорректная структура отклоняется валидатором приложения."""
    window = pack_editor_module.PackEditorWindow()
    window.general_tab.id_edit.setText("")  # пустой id — ошибка валидации
    error = window._do_validate()
    assert error is not None
    window.deleteLater()


def test_editor_enum_edit_roundtrip(pack_editor_module, qt_app, tmp_path):
    """Метка значения перечисления правится и сохраняется."""
    from internal_correspondence.core.domain_pack import load_domain_pack

    window = pack_editor_module.PackEditorWindow()
    # Первая перечислимая секция, первая строка значений
    window.enums_tab.enum_list.setCurrentRow(0)
    enum_name = window.enums_tab.enum_list.currentItem().text()
    label_item = window.enums_tab.table.item(0, 2)
    label_item.setText("Новая метка")
    window.enums_tab._store_current()

    target = tmp_path / "pack.json"
    window._save_to(target)
    pack = load_domain_pack(target)
    first_value = pack.enum(enum_name).values[0]
    assert first_value.label == "Новая метка"
    window.deleteLater()
