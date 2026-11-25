"""Редактор пакета предметной области (автономная утилита).

Не является частью приложения и не подключается к его окнам: запускается
самостоятельно, как скрипт:

    python scripts_dev/pack_editor.py [путь_к_пакету.json]

Без аргумента открывается встроенный пакет ``scientific-network`` — его можно
сохранить как шаблон для новой предметной области. Редактор работает с
JSON-структурой пакета напрямую; при сохранении структура валидируется
тем же кодом, что и загрузка пакета приложением (``DomainPack.from_dict``),
поэтому некорректный файл сохранить нельзя.

Секции:
- «Общие» — идентификатор и версия пакета (пишутся в meta.json обмена);
- «Перечисления» — значения (ключ неизменяем: он связан с кодом в БД;
  метки, краткие коды, веса и признак «устаревшее» редактируются);
- «Сущности» — метки сущностей и полей;
- «Директории» — имена служебных директорий хранилища;
- «Строки» — строки интерфейса (ключи фиксированы приложением,
  редактируются только значения).
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.domain_pack import (
    DomainPack,
    DomainPackError,
    default_domain_pack,
    load_domain_pack,
    save_domain_pack,
)

# Колонки таблиц
_ENUM_COLUMNS = ("Ключ", "Код", "Метка", "Вес", "Устаревшее")
_FIELD_COLUMNS = ("Поле", "Метка", "Кратко", "Обязательное")
_DIR_COLUMNS = ("Ключ", "Имя директории")
_STRING_COLUMNS = ("Ключ", "Значение")

_ENTITY_LABEL_FIELDS = (
    ("label", "Метка"),
    ("label_plural", "Метка (мн. ч.)"),
    ("label_prepositional", "Предложный падеж"),
    ("label_prepositional_plural", "Предложный падеж (мн. ч.)"),
)


def _item(text: str) -> QTableWidgetItem:
    return QTableWidgetItem(text)


def _check_item(checked: bool) -> QTableWidgetItem:
    item = QTableWidgetItem()
    item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
    return item


class GeneralTab(QWidget):
    """Общие сведения: идентификатор и версия пакета."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        self.id_edit = QLineEdit()
        self.version_edit = QLineEdit()
        form.addRow("Идентификатор пакета:", self.id_edit)
        form.addRow("Версия:", self.version_edit)

    def load(self, data: dict) -> None:
        self.id_edit.setText(str(data.get("id", "")))
        self.version_edit.setText(str(data.get("version", "")))

    def store(self, data: dict) -> None:
        data["id"] = self.id_edit.text().strip()
        data["version"] = self.version_edit.text().strip()


class EnumsTab(QWidget):
    """Редактор перечислений: слева список, справа значения."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: dict = {}
        self._current: Optional[str] = None
        layout = QHBoxLayout(self)

        self.enum_list = QListWidget()
        self.enum_list.currentTextChanged.connect(self._on_select)
        layout.addWidget(self.enum_list, stretch=1)

        right = QVBoxLayout()
        self.enum_label_edit = QLineEdit()
        self.enum_label_edit.setPlaceholderText("Метка перечисления")
        self.enum_label_edit.textEdited.connect(self._store_current)
        right.addWidget(self.enum_label_edit)

        self.table = QTableWidget(0, len(_ENUM_COLUMNS))
        self.table.setHorizontalHeaderLabels(_ENUM_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemChanged.connect(lambda _item: self._store_current())
        right.addWidget(self.table)

        buttons = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setToolTip("Добавить значение")
        add_btn.clicked.connect(self._add_value)
        remove_btn = QPushButton("−")
        remove_btn.setToolTip("Удалить значение")
        remove_btn.clicked.connect(self._remove_value)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addStretch()
        right.addLayout(buttons)
        layout.addLayout(right, stretch=3)

    def load(self, data: dict) -> None:
        self._data = data
        self._current = None
        self.enum_list.clear()
        for name in sorted(data.get("enums", {})):
            self.enum_list.addItem(name)
        if self.enum_list.count():
            self.enum_list.setCurrentRow(0)

    def store(self, data: dict) -> None:
        self._store_current()

    def _on_select(self, name: str) -> None:
        self._current = name or None
        enum_def = self._data.get("enums", {}).get(name)
        self.table.blockSignals(True)
        self.enum_label_edit.blockSignals(True)
        if enum_def is None:
            self.enum_label_edit.clear()
            self.table.setRowCount(0)
        else:
            self.enum_label_edit.setText(enum_def.get("label", ""))
            values = enum_def.get("values", [])
            self.table.setRowCount(len(values))
            for row, value in enumerate(values):
                self.table.setItem(row, 0, _item(str(value.get("key", ""))))
                self.table.setItem(row, 1, _item(str(value.get("code", ""))))
                self.table.setItem(row, 2, _item(str(value.get("label", ""))))
                weight = value.get("weight")
                self.table.setItem(
                    row, 3, _item("" if weight is None else str(weight))
                )
                self.table.setItem(
                    row, 4, _check_item(bool(value.get("deprecated")))
                )
        self.enum_label_edit.blockSignals(False)
        self.table.blockSignals(False)

    def _store_current(self) -> None:
        """Переносит содержимое таблицы обратно в структуру пакета."""
        if self._current is None:
            return
        enum_def = self._data.setdefault("enums", {}).setdefault(
            self._current, {"label": "", "values": []}
        )
        enum_def["label"] = self.enum_label_edit.text()
        values: List[dict] = []
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            if key_item is None or not key_item.text().strip():
                continue
            value: dict = {"key": key_item.text().strip()}
            code_item = self.table.item(row, 1)
            value["code"] = code_item.text().strip() if code_item else ""
            label_item = self.table.item(row, 2)
            value["label"] = label_item.text().strip() if label_item else ""
            weight_item = self.table.item(row, 3)
            weight_text = weight_item.text().strip() if weight_item else ""
            if weight_text:
                try:
                    value["weight"] = int(weight_text)
                except ValueError:
                    value["weight"] = weight_text  # валидация отловит при сохранении
            check_item = self.table.item(row, 4)
            if check_item is not None and check_item.checkState() == Qt.Checked:
                value["deprecated"] = True
            values.append(value)
        enum_def["values"] = values

    def _add_value(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, _item(""))
        self.table.setItem(row, 1, _item(""))
        self.table.setItem(row, 2, _item(""))
        self.table.setItem(row, 3, _item(""))
        self.table.setItem(row, 4, _check_item(False))
        self._store_current()

    def _remove_value(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        for row in reversed(rows):
            self.table.removeRow(row)
        self._store_current()


class EntitiesTab(QWidget):
    """Редактор меток сущностей и их полей."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: dict = {}
        self._current: Optional[str] = None
        layout = QHBoxLayout(self)

        self.entity_list = QListWidget()
        self.entity_list.currentTextChanged.connect(self._on_select)
        layout.addWidget(self.entity_list, stretch=1)

        right = QVBoxLayout()
        form = QFormLayout()
        self.label_edits: Dict[str, QLineEdit] = {}
        for key, caption in _ENTITY_LABEL_FIELDS:
            edit = QLineEdit()
            edit.textEdited.connect(self._store_current)
            self.label_edits[key] = edit
            form.addRow(f"{caption}:", edit)
        right.addLayout(form)

        self.fields_table = QTableWidget(0, len(_FIELD_COLUMNS))
        self.fields_table.setHorizontalHeaderLabels(_FIELD_COLUMNS)
        self.fields_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.fields_table.itemChanged.connect(lambda _item: self._store_current())
        right.addWidget(self.fields_table)

        buttons = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setToolTip("Добавить поле")
        add_btn.clicked.connect(self._add_field)
        remove_btn = QPushButton("−")
        remove_btn.setToolTip("Удалить поле")
        remove_btn.clicked.connect(self._remove_field)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addStretch()
        right.addLayout(buttons)
        layout.addLayout(right, stretch=3)

    def load(self, data: dict) -> None:
        self._data = data
        self._current = None
        self.entity_list.clear()
        for name in sorted(data.get("entities", {})):
            self.entity_list.addItem(name)
        if self.entity_list.count():
            self.entity_list.setCurrentRow(0)

    def store(self, data: dict) -> None:
        self._store_current()

    def _on_select(self, name: str) -> None:
        self._current = name or None
        entity_def = self._data.get("entities", {}).get(name)
        for edit in self.label_edits.values():
            edit.blockSignals(True)
        self.fields_table.blockSignals(True)
        if entity_def is None:
            for edit in self.label_edits.values():
                edit.clear()
            self.fields_table.setRowCount(0)
        else:
            for key, edit in self.label_edits.items():
                edit.setText(str(entity_def.get(key, "")))
            fields = entity_def.get("fields", {})
            self.fields_table.setRowCount(len(fields))
            for row, (field_name, field_def) in enumerate(sorted(fields.items())):
                self.fields_table.setItem(row, 0, _item(field_name))
                self.fields_table.setItem(
                    row, 1, _item(str(field_def.get("label", "")))
                )
                self.fields_table.setItem(
                    row, 2, _item(str(field_def.get("short", "")))
                )
                self.fields_table.setItem(
                    row, 3, _check_item(bool(field_def.get("required")))
                )
        for edit in self.label_edits.values():
            edit.blockSignals(False)
        self.fields_table.blockSignals(False)

    def _store_current(self) -> None:
        if self._current is None:
            return
        entity_def = self._data.setdefault("entities", {}).setdefault(
            self._current, {}
        )
        for key, edit in self.label_edits.items():
            text = edit.text().strip()
            if text:
                entity_def[key] = text
            else:
                entity_def.pop(key, None)
        fields: Dict[str, dict] = {}
        for row in range(self.fields_table.rowCount()):
            name_item = self.fields_table.item(row, 0)
            if name_item is None or not name_item.text().strip():
                continue
            field_def: dict = {}
            label_item = self.fields_table.item(row, 1)
            if label_item is not None and label_item.text().strip():
                field_def["label"] = label_item.text().strip()
            short_item = self.fields_table.item(row, 2)
            if short_item is not None and short_item.text().strip():
                field_def["short"] = short_item.text().strip()
            check_item = self.fields_table.item(row, 3)
            if check_item is not None and check_item.checkState() == Qt.Checked:
                field_def["required"] = True
            fields[name_item.text().strip()] = field_def
        entity_def["fields"] = fields

    def _add_field(self) -> None:
        row = self.fields_table.rowCount()
        self.fields_table.insertRow(row)
        self.fields_table.setItem(row, 0, _item(""))
        self.fields_table.setItem(row, 1, _item(""))
        self.fields_table.setItem(row, 2, _item(""))
        self.fields_table.setItem(row, 3, _check_item(False))

    def _remove_field(self) -> None:
        rows = sorted({index.row() for index in self.fields_table.selectedIndexes()})
        for row in reversed(rows):
            self.fields_table.removeRow(row)
        self._store_current()


class KeyValueTab(QWidget):
    """Таблица «ключ — значение» (директории, строки интерфейса)."""

    def __init__(
        self,
        section: str,
        key_editable: bool,
        with_filter: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._section = section
        self._key_editable = key_editable
        self._data: dict = {}
        layout = QVBoxLayout(self)
        self._filter: Optional[QLineEdit] = None
        if with_filter:
            self._filter = QLineEdit()
            self._filter.setPlaceholderText("Фильтр по ключу и значению...")
            self._filter.textChanged.connect(self._apply_filter)
            layout.addWidget(self._filter)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Ключ", "Значение"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)
        if key_editable:
            buttons = QHBoxLayout()
            add_btn = QPushButton("+")
            add_btn.clicked.connect(self._add_row)
            remove_btn = QPushButton("−")
            remove_btn.clicked.connect(self._remove_rows)
            buttons.addWidget(add_btn)
            buttons.addWidget(remove_btn)
            buttons.addStretch()
            layout.addLayout(buttons)

    def load(self, data: dict) -> None:
        self._data = data
        section = data.get(self._section, {})
        self.table.setRowCount(len(section))
        for row, (key, value) in enumerate(sorted(section.items())):
            key_item = _item(key)
            if not self._key_editable:
                key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, key_item)
            self.table.setItem(row, 1, _item(str(value)))
        if self._filter is not None:
            self._filter.clear()

    def store(self, data: dict) -> None:
        section: Dict[str, str] = {}
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            if key_item is None or not key_item.text().strip():
                continue
            value_item = self.table.item(row, 1)
            section[key_item.text().strip()] = (
                value_item.text() if value_item is not None else ""
            )
        data[self._section] = section

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.table.rowCount()):
            key_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            haystack = " ".join(
                item.text().lower() for item in (key_item, value_item) if item
            )
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _add_row(self) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, _item(""))
        self.table.setItem(row, 1, _item(""))

    def _remove_rows(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        for row in reversed(rows):
            self.table.removeRow(row)


class PackEditorWindow(QMainWindow):
    """Главное окно редактора пакета предметной области."""

    def __init__(self, path: Optional[Path] = None) -> None:
        super().__init__()
        self.setWindowTitle("Редактор пакета предметной области")
        self.resize(1000, 700)
        self._path: Optional[Path] = None
        self._data: dict = {}

        toolbar = QToolBar("Действия")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for text, handler in (
            ("Открыть...", self._open_file),
            ("Встроенный пакет", self._load_builtin),
            ("Сохранить", self._save),
            ("Сохранить как...", self._save_as),
            ("Проверить", self._validate),
        ):
            action = toolbar.addAction(text)
            action.triggered.connect(handler)

        self.tabs = QTabWidget()
        self.general_tab = GeneralTab()
        self.enums_tab = EnumsTab()
        self.entities_tab = EntitiesTab()
        self.directories_tab = KeyValueTab("directories", key_editable=True)
        self.strings_tab = KeyValueTab(
            "strings", key_editable=False, with_filter=True
        )
        self.tabs.addTab(self.general_tab, "Общие")
        self.tabs.addTab(self.enums_tab, "Перечисления")
        self.tabs.addTab(self.entities_tab, "Сущности")
        self.tabs.addTab(self.directories_tab, "Директории")
        self.tabs.addTab(self.strings_tab, "Строки")
        self.setCentralWidget(self.tabs)
        self.setStatusBar(QStatusBar())

        if path is not None:
            self._open_path(path)
        else:
            self._load_builtin()

    # ------------------------------------------------------------------
    # Данные
    # ------------------------------------------------------------------

    def _load_data(self, data: dict, path: Optional[Path]) -> None:
        self._data = data
        self._path = path
        self.general_tab.load(data)
        self.enums_tab.load(data)
        self.entities_tab.load(data)
        self.directories_tab.load(data)
        self.strings_tab.load(data)
        title = "Редактор пакета предметной области"
        if path is not None:
            title += f" — {path}"
        self.setWindowTitle(title)

    def _collect(self) -> dict:
        """Собирает структуру пакета из всех вкладок."""
        self.general_tab.store(self._data)
        self.enums_tab.store(self._data)
        self.entities_tab.store(self._data)
        self.directories_tab.store(self._data)
        self.strings_tab.store(self._data)
        return self._data

    def _open_path(self, path: Path) -> bool:
        try:
            pack = load_domain_pack(path)
        except (DomainPackError, OSError) as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить пакет:\n{exc}")
            return False
        self._load_data(pack.to_dict(), path)
        self.statusBar().showMessage(f"Загружен пакет {pack.id} v{pack.version}")
        return True

    def _open_file(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, "Открыть пакет", "", "Пакеты предметной области (*.json)"
        )
        if path:
            self._open_path(Path(path))

    def _load_builtin(self) -> None:
        self._load_data(default_domain_pack().to_dict(), None)
        self.statusBar().showMessage("Загружен встроенный пакет")

    def _do_validate(self) -> Optional[str]:
        """Валидирует структуру; возвращает текст ошибки или None."""
        try:
            DomainPack.from_dict(self._collect(), source="<редактор>")
        except DomainPackError as exc:
            return str(exc)
        return None

    def _validate(self) -> bool:
        """Проверяет структуру тем же валидатором, что и приложение."""
        error = self._do_validate()
        if error is not None:
            QMessageBox.warning(self, "Ошибка валидации", error)
            self.statusBar().showMessage("Ошибка валидации")
            return False
        pack = DomainPack.from_dict(self._data, source="<редактор>")
        self.statusBar().showMessage(
            f"Пакет корректен: {pack.id} v{pack.version}, "
            f"перечислений: {len(pack.enums)}"
        )
        return True

    def _save(self) -> None:
        if self._path is None:
            self._save_as()
            return
        self._save_to(self._path)

    def _save_as(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self, "Сохранить пакет", "domain_pack.json",
            "Пакеты предметной области (*.json)",
        )
        if path:
            self._save_to(Path(path))

    def _save_to(self, path: Path) -> None:
        try:
            pack = DomainPack.from_dict(self._collect(), source="<редактор>")
        except DomainPackError as exc:
            QMessageBox.warning(self, "Ошибка валидации", str(exc))
            return
        save_domain_pack(pack, path)
        self._path = path
        self.setWindowTitle(f"Редактор пакета предметной области — {path}")
        self.statusBar().showMessage(f"Сохранено: {path}")


def main(argv: Optional[List[str]] = None) -> int:
    """Точка входа автономного редактора пакета."""
    args = list(sys.argv if argv is None else argv)
    app = QApplication(args)
    path = Path(args[1]) if len(args) > 1 else None
    window = PackEditorWindow(path)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
