"""Тесты сохранения геометрии окна и ширин колонок между запусками."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtWidgets import QAction, QApplication, QProgressDialog, QPushButton

from internal_correspondence.core.constants import ReportType
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.settings import AppSettings, SettingsManager
from internal_correspondence.gui import application as application_module
from internal_correspondence.gui.application import (
    MainWindow,
    _create_report_progress_dialog,
    _parse_column_widths,
)
from internal_correspondence.utils.string_resources import STRINGS


@pytest.fixture(scope="module")
def qt_app() -> QApplication:
    """Единственный QApplication для тестов окон."""
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window_env(tmp_path: Path):
    """База данных и настройки во временном каталоге."""
    db = DatabaseManager(f"sqlite:///{tmp_path / 'ui.db'}")
    db.create_tables()
    manager = SettingsManager(tmp_path)
    settings = AppSettings(
        db_url=f"sqlite:///{tmp_path / 'ui.db'}",
        storage_path=str(tmp_path / "storage"),
        branch_id="BR-001",
    )
    yield settings, db, manager
    db.close()


def test_parse_column_widths() -> None:
    """Разбор строки ширин: числа через запятую, мусор игнорируется."""
    assert _parse_column_widths("80,100, 250,") == [80, 100, 250]
    assert _parse_column_widths("") == []
    assert _parse_column_widths("abc,10,-5") == [10]


# ---------------------------------------------------------------------------
# Сохранение и восстановление сортировки таблиц документов
# ---------------------------------------------------------------------------


def test_parse_sort_state() -> None:
    """Разбор сохранённой сортировки: «колонка» / «колонка:desc» / пусто."""
    from internal_correspondence.gui.application import _parse_sort_state

    assert _parse_sort_state("name") == ("name", False)
    assert _parse_sort_state("outgoing_date:desc") == ("outgoing_date", True)
    assert _parse_sort_state("") is None
    assert _parse_sort_state("   ") is None
    assert _parse_sort_state(":desc") is None


def test_data_menu_contains_generate_report_action(
    window_env,
    qt_app: QApplication,
) -> None:
    """В меню данных доступно открытие диалога формирования отчёта."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    action = window.findChild(QAction, "generateReportAction")
    assert action is not None
    assert action.text() == STRINGS.action_generate_report
    window.close()


def test_data_menu_contains_evaluation_lists_action(
    window_env,
    qt_app: QApplication,
) -> None:
    """Пункт «Оценочные листы» идёт сразу после импорта оценок."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    action = window.findChild(QAction, "evaluationListsAction")
    assert action is not None
    assert action.text() == STRINGS.menu_evaluation_lists
    data_menu = next(
        item.menu()
        for item in window.menuBar().actions()
        if item.text() == STRINGS.menu_data
    )
    texts = [item.text() for item in data_menu.actions()]
    index = texts.index(STRINGS.menu_evaluation_lists)
    assert texts[index - 1] == STRINGS.menu_import_evaluations
    window.close()


def test_document_action_button_styles_apply_to_both_tabs(
    window_env,
    qt_app: QApplication,
) -> None:
    """Обе вкладки документов получают цветовые роли основных действий."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)

    for tab in (window.materials_tab, window.telegram_tab):
        assert tab.add_btn.property("role") == "primary"
        assert tab.edit_btn.property("role") is None
        assert tab.delete_btn.property("role") == "danger"

    window.close()


def test_report_progress_dialog_is_modal_and_cannot_be_cancelled(
    window_env,
    qt_app: QApplication,
) -> None:
    """Индикатор создания отчёта блокирует окно и не предлагает отмену."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)

    dialog = _create_report_progress_dialog(window)

    assert dialog.labelText() == STRINGS.report_progress_creating
    assert dialog.minimum() == 0
    assert dialog.maximum() == 0
    assert dialog.windowModality() == Qt.ApplicationModal
    assert dialog.findChildren(QPushButton) == []
    dialog.close()
    window.close()


def test_report_progress_dialog_is_visible_while_report_is_rendered(
    window_env,
    qt_app: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Индикатор показывается после выбора пути и остаётся до конца рендера."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()
    observed = {"visible": False}

    class FakeReportDialog:
        """Принятый диалог с фиксированным месячным периодом."""

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @staticmethod
        def exec_() -> bool:
            return True

        @staticmethod
        def selected_request():
            return type(
                "Request",
                (),
                {
                    "report_type": ReportType.MONTH,
                    "period_number": 1,
                    "year": 2026,
                },
            )()

        @staticmethod
        def month_names() -> list[str]:
            return STRINGS.report_month_names.split(",")

        @staticmethod
        def draft_values() -> dict:
            return {}

    class FakeReportDataService:
        """Минимальная замена сервиса для проверки поведения окна."""

        def __init__(self, _session) -> None:
            pass

        @staticmethod
        def save_draft(_request, _values) -> None:
            return None

        @staticmethod
        def build_context(_request, _month_names) -> dict:
            return {}

    def fake_render_report(_report_type, _context, _storage_root, output_path):
        dialogs = window.findChildren(QProgressDialog)
        observed["visible"] = any(
            dialog.isVisible()
            and dialog.labelText() == STRINGS.report_progress_creating
            for dialog in dialogs
        )
        return Path(output_path)

    output_path = tmp_path / "report.docx"
    monkeypatch.setattr(application_module, "ReportDialog", FakeReportDialog)
    monkeypatch.setattr(
        application_module,
        "ReportDataService",
        FakeReportDataService,
    )
    monkeypatch.setattr(application_module, "render_report", fake_render_report)
    monkeypatch.setattr(
        application_module.QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *_args, **_kwargs: (str(output_path), "")),
    )
    monkeypatch.setattr(
        application_module.QMessageBox,
        "information",
        staticmethod(lambda *_args, **_kwargs: None),
    )

    window._generate_report()

    assert observed["visible"]
    window.close()


def test_main_window_saves_ui_state(window_env, qt_app: QApplication) -> None:
    """Закрытие окна сохраняет геометрию и ширины колонок в настройки."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.resize(1100, 700)
    window.materials_tab.table.setColumnWidth(0, 177)
    window.telegram_tab.table.setColumnWidth(1, 210)
    window._save_ui_state()

    saved = manager.load()
    assert saved.window_geometry
    assert saved.material_column_widths.split(",")[0] == "177"
    assert saved.telegram_column_widths.split(",")[1] == "210"

    # Повторное сохранение при закрытии не должно падать
    window.close()


def test_main_window_saves_table_sort(window_env, qt_app: QApplication) -> None:
    """Сортировка обеих таблиц документов сохраняется при закрытии окна."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    assert window.materials_tab.set_sort_state("name", descending=True)
    assert window.telegram_tab.set_sort_state("outgoing_date", descending=False)
    window._save_ui_state()

    saved = manager.load()
    assert saved.material_sort == "name:desc"
    assert saved.telegram_sort == "outgoing_date"
    assert window.materials_tab.sort_state() == ("name", True)
    assert window.telegram_tab.sort_state() == ("outgoing_date", False)
    window.close()


def test_main_window_restores_table_sort(window_env, qt_app: QApplication) -> None:
    """При создании окно применяет сохранённую сортировку таблиц."""
    settings, db, manager = window_env
    settings.material_sort = "name:desc"
    settings.telegram_sort = "outgoing_date"
    window = MainWindow(settings, db, manager)
    assert window.materials_tab.sort_state() == ("name", True)
    assert window.telegram_tab.sort_state() == ("outgoing_date", False)
    window.close()


def test_main_window_ignores_unknown_sort_column(window_env, qt_app: QApplication) -> None:
    """Сохранённая колонка, отсутствующая в текущей роли, не ломает старт."""
    settings, db, manager = window_env
    settings.material_sort = "no_such_column:desc"
    window = MainWindow(settings, db, manager)
    assert window.materials_tab.sort_state() is None
    window.close()


def test_main_window_restores_column_widths(window_env, qt_app: QApplication) -> None:
    """При создании окно применяет сохранённые ширины колонок."""
    settings, db, manager = window_env
    settings.material_column_widths = "177,210,300"
    settings.telegram_column_widths = "90,140"
    window = MainWindow(settings, db, manager)
    assert window.materials_tab.column_widths()[:3] == [177, 210, 300]
    assert window.telegram_tab.column_widths()[:2] == [90, 140]
    window.close()


def test_geometry_roundtrip(window_env, qt_app: QApplication) -> None:
    """Геометрия окна сохраняется и восстанавливается без искажений."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.resize(1200, 900)
    window._save_ui_state()

    saved_geometry = manager.load().window_geometry
    assert saved_geometry

    restored = window.restoreGeometry(
        QByteArray.fromBase64(saved_geometry.encode("ascii"))
    )
    assert restored
    assert window.width() == 1200
    assert window.height() == 900
    window.close()


def test_empty_geometry_is_tolerated(window_env, qt_app: QApplication) -> None:
    """Отсутствие сохранённого состояния (первый запуск) не мешает старту."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    assert window.settings.window_geometry == ""
    window.close()


# ---------------------------------------------------------------------------
# Док-виджет прикреплённых файлов: меню «Вид» и перемещаемая панель
# ---------------------------------------------------------------------------


def test_files_dock_menu_action_toggles_visibility(window_env, qt_app: QApplication) -> None:
    """Пункт меню «Вид» → «Прикреплённые файлы» показывает/скрывает док."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    action = window.files_dock_action
    assert action.isCheckable()
    assert action.text() == STRINGS.menu_attached_files

    window.show()
    qt_app.processEvents()
    assert action.isChecked()

    # Снятие галочки скрывает док
    action.trigger()
    qt_app.processEvents()
    assert window.files_dock.isHidden()
    assert not action.isChecked()

    # Повторное нажатие вновь показывает док и отмечает пункт меню
    action.trigger()
    qt_app.processEvents()
    assert window.files_dock.isVisible()
    assert action.isChecked()
    window.close()


def test_files_dock_is_movable_and_floatable(window_env, qt_app: QApplication) -> None:
    """Панель файлов перетаскивается за заголовок: все области и плавание."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()

    assert window.files_dock.allowedAreas() == Qt.AllDockWidgetAreas
    features = window.files_dock.features()
    assert features & window.files_dock.DockWidgetClosable
    assert features & window.files_dock.DockWidgetMovable
    assert features & window.files_dock.DockWidgetFloatable
    assert window.dockWidgetArea(window.files_dock) == Qt.RightDockWidgetArea

    window._save_ui_state()

    saved = manager.load()
    assert saved.files_dock_visible == "true"
    assert saved.files_dock_area == str(int(Qt.RightDockWidgetArea))
    assert saved.files_dock_floating == "false"
    assert saved.files_dock_geometry == ""
    window.close()


def test_files_dock_hidden_state_saved_on_close(window_env, qt_app: QApplication) -> None:
    """Скрытый через меню док запоминается как скрытый."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.show()
    window.files_dock_action.trigger()
    window._save_ui_state()

    saved = manager.load()
    assert saved.files_dock_visible == "false"
    window.close()


def test_files_changed_signal_updates_document_row_highlight(window_env, qt_app: QApplication, tmp_path: Path) -> None:
    """Прикрепление файла через док-виджет сразу даёт подсветку изменённой строки."""
    from datetime import date

    from internal_correspondence.core.constants import MaterialType, Role
    from internal_correspondence.core.domain_pack import dir_name
    from internal_correspondence.gui.theme import current_theme
    from internal_correspondence.importexport.export_service import ExportService
    from internal_correspondence.orm.models import (
        Branch,
        ScientificMaterial,
        TerritorialUnit,
    )
    from internal_correspondence.services.change_tracking import register_change_tracking

    register_change_tracking()
    settings, db, manager = window_env
    settings.role = Role.BRANCH.value
    settings.branch_id = "F1"
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()

    with db.get_session() as session:
        session.add(TerritorialUnit(id="MSK", name="Москва"))
        session.add(Branch(id="F1", name="Филиал", short_name="Ф", territorial_unit_id="MSK"))
        material = ScientificMaterial(
            type=MaterialType.MESSAGE,
            outgoing_number="М-1",
            outgoing_date=date(2026, 1, 1),
            name="Материал",
            branch_id="F1",
        )
        session.add(material)
        session.commit()
        material_id = material.id

    # Экспортируем начальные изменения: строка без подсветки «изменено»
    storage = settings.storage_path_obj()
    storage.mkdir(parents=True, exist_ok=True)
    with db.get_session() as session:
        ExportService(session, storage).export()
        session.commit()

    window.materials_tab.refresh()
    assert window.materials_tab.reveal_record(material_id)
    row = window.materials_tab.table_model.row_of(material_id)
    theme = current_theme()
    assert (
        window.materials_tab.table_model.index(row, 0).data(Qt.BackgroundRole)
        != theme.modified_row
    )

    # Файл внутри хранилища: привязка без копирования (синхронный путь дока)
    inside = (
        storage
        / dir_name("files")
        / dir_name("material_files")
        / "old"
        / "report.txt"
    )
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_text("x", encoding="utf-8")

    window.files_dock.set_document(
        window.files_dock.session.get(ScientificMaterial, material_id)
    )
    window.files_dock._add_paths([inside])  # pylint: disable=protected-access

    color = window.materials_tab.table_model.index(row, 0).data(Qt.BackgroundRole)
    assert color == theme.modified_row
    window.close()


def test_files_dock_state_restored_from_settings(window_env, qt_app: QApplication) -> None:
    """Сохранённые область, плавание и видимость восстанавливаются."""
    settings, db, manager = window_env
    settings.files_dock_area = str(int(Qt.LeftDockWidgetArea))
    settings.files_dock_floating = "true"
    settings.files_dock_visible = "false"
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()

    assert window.dockWidgetArea(window.files_dock) == Qt.LeftDockWidgetArea
    assert window.files_dock.isFloating()
    assert window.files_dock.isHidden()
    assert not window.files_dock_action.isChecked()
    window.close()


def test_files_dock_moved_position_is_saved_and_restored(
    window_env, qt_app: QApplication
) -> None:
    """Панель, перетащенная пользователем в левую область, встаёт туда же."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()

    window.addDockWidget(Qt.LeftDockWidgetArea, window.files_dock)
    window._save_ui_state()
    saved = manager.load()
    assert saved.files_dock_area == str(int(Qt.LeftDockWidgetArea))
    window.close()

    restored_settings = manager.load()
    window2 = MainWindow(restored_settings, db, manager)
    window2.show()
    qt_app.processEvents()
    assert window2.dockWidgetArea(window2.files_dock) == Qt.LeftDockWidgetArea
    window2.close()


def test_files_dock_invalid_area_falls_back_to_right(
    window_env, qt_app: QApplication
) -> None:
    """Мусор в настройке области не ломает старт: панель встаёт справа."""
    settings, db, manager = window_env
    settings.files_dock_area = "12345"
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()

    assert window.dockWidgetArea(window.files_dock) == Qt.RightDockWidgetArea
    window.close()


def test_files_dock_garbage_geometry_is_tolerated(window_env, qt_app: QApplication) -> None:
    """Мусор в сохранённой геометрии плавающего дока не ломает старт."""
    settings, db, manager = window_env
    settings.files_dock_floating = "true"
    settings.files_dock_geometry = "legacy-geometry"
    window = MainWindow(settings, db, manager)
    window.show()
    qt_app.processEvents()

    assert window.files_dock.isFloating()
    window.close()


# ---------------------------------------------------------------------------
# Раскладка колонок таблиц документов: видимость, порядок, ширина
# ---------------------------------------------------------------------------


def test_header_menu_lists_all_columns_checkable(
    window_env, qt_app: QApplication
) -> None:
    """Меню заголовка содержит все колонки с галочками видимости."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    tab = window.materials_tab
    menu = tab._build_header_menu()
    actions = menu.actions()

    assert len(actions) == len(tab.columns)
    assert all(action.isCheckable() for action in actions)
    assert all(action.isChecked() for action in actions)
    assert {action.data() for action in actions} == set(range(len(tab.columns)))
    window.close()


def test_column_visibility_toggle_and_last_guard(
    window_env, qt_app: QApplication
) -> None:
    """Галочка скрывает/показывает колонку; последняя видимая не скрывается."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    tab = window.materials_tab
    header = tab.table.horizontalHeader()

    tab._set_column_visible(1, False)
    assert header.isSectionHidden(1)

    tab._set_column_visible(1, True)
    assert not header.isSectionHidden(1)

    # Последнюю видимую колонку скрыть нельзя
    for logical in range(1, len(tab.columns)):
        tab._set_column_visible(logical, False)
    visible = [
        logical for logical in range(len(tab.columns))
        if not header.isSectionHidden(logical)
    ]
    assert visible == [0]
    tab._set_column_visible(0, False)
    assert not header.isSectionHidden(0)
    window.close()


def test_columns_layout_roundtrip(window_env, qt_app: QApplication) -> None:
    """Сериализация раскладки возвращает порядок, видимость и ширины."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    tab = window.materials_tab
    header = tab.table.horizontalHeader()

    tab.table.setColumnWidth(0, 200)
    tab._set_column_visible(2, False)
    header.moveSection(0, 3)  # первая колонка — на четвёртое место

    layout = tab.columns_layout()
    entries = layout.split(",")
    assert entries[3].startswith(f"{tab.columns[0].name}:200:1")
    hidden_entry = next(entry for entry in entries if entry.endswith(":0"))
    assert hidden_entry.startswith(f"{tab.columns[2].name}:")

    # Применение к «свежей» таблице даёт ту же раскладку
    tab.set_columns_layout(",".join(reversed(entries)))
    restored = tab.columns_layout()
    assert restored == ",".join(reversed(entries))
    window.close()


def test_main_window_saves_and_restores_columns_layout(
    window_env, qt_app: QApplication
) -> None:
    """Порядок, видимость и ширины колонок переживают перезапуск окна."""
    settings, db, manager = window_env
    window = MainWindow(settings, db, manager)
    tab = window.materials_tab
    header = tab.table.horizontalHeader()

    tab.table.setColumnWidth(1, 233)
    tab._set_column_visible(0, False)
    header.moveSection(1, 0)  # вторая колонка — вперёди
    window._save_ui_state()

    saved = manager.load()
    assert saved.material_columns_layout
    window.close()

    restored = MainWindow(saved, db, manager)
    tab2 = restored.materials_tab
    header2 = tab2.table.horizontalHeader()
    assert header2.isSectionHidden(0)
    assert header2.visualIndex(1) == 0
    assert tab2.table.columnWidth(1) == 233
    restored.close()
