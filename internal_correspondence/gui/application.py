"""Главный модуль GUI-приложения."""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QByteArray, Qt, QThread
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import (
    BACKUPS_DIR,
    DEFAULT_CHANGES_RETENTION_DAYS,
    LOGS_DIR,
    ReportType,
    Role,
)
from internal_correspondence.core.enum_registry import pack_enum_display
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.domain_pack import (
    DomainPackError,
    dir_name,
    get_domain_pack,
    init_domain_pack,
    save_domain_pack,
)
from internal_correspondence.core.logging_config import configure_logging, get_logger
from internal_correspondence.core.settings import AppSettings, SettingsManager
from internal_correspondence.gui.attached_files_widget import AttachedFilesWidget
from internal_correspondence.gui.custom_title_bar import (
    FramelessWindowMixin,
    WindowControlLabels,
    install_dialog_title_bars,
)
from internal_correspondence.gui.document_list_widget import DocumentListWidget
from internal_correspondence.gui.evaluation_import_dialog import EvaluationImportDialog
from internal_correspondence.gui.evaluation_lists_dialog import EvaluationListsDialog
from internal_correspondence.gui.exchange_dialogs import (
    ExportBranchesDialog,
    ExportWorker,
    ImportPreviewDialog,
    ImportWorker,
)
from internal_correspondence.gui.filter_model import (
    deserialize_filters,
    serialize_filters,
)
from internal_correspondence.gui.first_run_wizard import run_first_run_wizard
from internal_correspondence.gui.i18n import install_translations
from internal_correspondence.gui.imported_files_widget import ImportedFilesWidget
from internal_correspondence.gui.oshm_dialog import OSHMDialog
from internal_correspondence.gui.reference_dialogs import (
    AcademicTitleDialog,
    BranchDialog,
    ConsumerDialog,
    CountryDialog,
    LeaderDialog,
    ScientificTaskDialog,
    SourceDialog,
    TerritorialUnitDialog,
)
from internal_correspondence.gui.reference_editor import ReferenceEditorDialog
from internal_correspondence.gui.report_dialog import ReportDialog
from internal_correspondence.gui.settings_dialog import SettingsDialog
from internal_correspondence.gui.statistics_widget import StatisticsWidget
from internal_correspondence.gui.dashboard_widget import DashboardWidget
from internal_correspondence.gui.task_distribution_widget import TaskDistributionWidget
from internal_correspondence.gui.table_model import ColumnDef
from internal_correspondence.gui.theme import THEMES, apply_theme, current_theme
from internal_correspondence.importexport.branch_import import (
    InitialBranchImport,
    run_initial_import,
)
from internal_correspondence.importexport.export_service import ExportService
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.importexport.reference_import import (
    import_actual_data,
    import_primary_data,
)
from internal_correspondence.orm.labels import entity_label
from internal_correspondence.orm.models import (
    AcademicTitle,
    Branch,
    Consumer,
    Country,
    Department,
    Employee,
    Leader,
    ScientificMaterial,
    ScientificTask,
    Source,
    Telegram,
    TerritorialUnit,
    WorkingGroup,
)
from internal_correspondence.reports.report_service import ReportDataService
from internal_correspondence.reports.word_report import render_report
from internal_correspondence.services.change_tracking import (
    purge_expired_changes,
    register_change_tracking,
)
from internal_correspondence.services.enum_validation import validate_enum_codes
from internal_correspondence.services.reference_service import (
    AcademicTitleService,
    BranchService,
    ConsumerService,
    CountryService,
    LeaderService,
    ScientificTaskService,
    SourceService,
    TerritorialUnitService,
)
from internal_correspondence.text_import import ImporterConfig
from internal_correspondence.utils.string_resources import STRINGS, reload_strings

logger = get_logger("application")


def _window_control_labels() -> WindowControlLabels:
    """Возвращает актуальные подписи кнопок управления окнами."""
    return WindowControlLabels(
        minimize=STRINGS.window_minimize,
        maximize=STRINGS.window_maximize,
        restore=STRINGS.window_restore,
        close=STRINGS.window_close,
    )


def _create_report_progress_dialog(parent: QWidget) -> QProgressDialog:
    """Создаёт модальный индикатор формирования отчёта без кнопки отмены."""
    dialog = QProgressDialog(parent)
    dialog.setWindowTitle(STRINGS.title_generate_report)
    dialog.setLabelText(STRINGS.report_progress_creating)
    dialog.setRange(0, 0)
    dialog.setCancelButton(None)
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    return dialog


def _parse_column_widths(raw: str) -> List[int]:
    """Разбирает сохранённые ширины колонок из строки настроек."""
    widths = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            widths.append(int(part))
    return widths


def _parse_bool(raw: str, default: bool) -> bool:
    """Разбирает булево значение из строки настроек."""
    raw = (raw or "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return default


def _format_sort_state(state: Optional[Tuple[str, bool]]) -> str:
    """Сериализует состояние сортировки: «колонка» или «колонка:desc»."""
    if state is None:
        return ""
    column, descending = state
    return f"{column}:desc" if descending else column


def _parse_sort_state(raw: str) -> Optional[Tuple[str, bool]]:
    """Разбирает сохранённое состояние сортировки; None — не задано или пусто."""
    raw = (raw or "").strip()
    if not raw:
        return None
    descending = raw.endswith(":desc")
    column = raw[: -len(":desc")] if descending else raw
    if not column:
        return None
    return (column, descending)


def _format_employees(employees) -> str:
    """Форматирует список причастных сотрудников для ячейки таблицы.

    Значения перечисляются в алфавитном порядке отображаемых имён.
    """
    names = sorted(
        (employee.display_name() for employee in employees or []),
        key=str.casefold,
    )
    return ", ".join(names)


def _format_material_type(value) -> str:
    """Краткий код типа материала из пакета предметной области."""
    return pack_enum_display("material_type", value)


def _format_telegram_type(value) -> str:
    """Краткий код типа телеграммы из пакета предметной области."""
    return pack_enum_display("telegram_type", value)


def _format_report_type(value) -> str:
    """Краткий код типа доклада из пакета предметной области."""
    return pack_enum_display("telegram_report_type", value)


def _format_task_type(value) -> str:
    """Краткий код типа задачи из пакета предметной области."""
    return pack_enum_display("scientific_task_type", value)


def _format_source_type(value) -> str:
    """Краткий код типа источника из пакета предметной области."""
    return pack_enum_display("source_type", value)


def _format_departments(departments) -> str:
    """Форматирует список участвовавших отделов для ячейки таблицы.

    Значения перечисляются в алфавитном порядке отображаемых названий.
    """
    names = sorted(
        (department.short_name or department.name for department in departments or []),
        key=str.casefold,
    )
    return ", ".join(names)


def _format_workgroups(workgroups) -> str:
    """Форматирует список участвовавших рабочих групп для ячейки таблицы.

    Значения перечисляются в алфавитном порядке названий.
    """
    names = sorted(
        (workgroup.name for workgroup in workgroups or []),
        key=str.casefold,
    )
    return ", ".join(names)


def _format_countries(countries) -> str:
    """Форматирует список стран происхождения данных для ячейки таблицы.

    Значения перечисляются в алфавитном порядке названий.
    """
    names = sorted(
        (country.name for country in countries or []),
        key=str.casefold,
    )
    return ", ".join(names)


def _format_sources(sources) -> str:
    """Форматирует список источников данных для ячейки таблицы.

    Значения перечисляются в алфавитном порядке индексов.
    """
    indexes = sorted(
        (source.index for source in sources or []),
        key=str.casefold,
    )
    return ", ".join(indexes)


def _format_addresses(addresses) -> str:
    """Форматирует адресацию доклада («ИД+» через запятую)."""
    from internal_correspondence.gui.edit_elements import format_report_addresses

    return format_report_addresses(addresses or [])


def _is_head_office(role: Optional[str]) -> bool:
    """Проверяет, задана ли роль «головной офис»."""
    return role == Role.HEAD_OFFICE.value


def material_columns(role: Optional[str] = None) -> List[ColumnDef]:
    """Возвращает описания столбцов таблицы научных материалов для роли.

    Порядок и состав столбцов — по плану редактирования отображения:
    для роли «филиал» дополнительно отделы и сотрудники, для роли
    «головной офис» — филиал.
    """
    columns = [
        ColumnDef("outgoing_number", width=100),
        ColumnDef("outgoing_date", width=110),
        ColumnDef("type", width=80, formatter=_format_material_type),
        ColumnDef("name", width=250),
        ColumnDef(
            "countries",
            width=150,
            formatter=_format_countries,
            filter_target=Country,
        ),
        ColumnDef(
            "sources",
            width=110,
            formatter=_format_sources,
            filter_target=Source,
        ),
        ColumnDef("consumer.short_name", width=120),
    ]
    if _is_head_office(role):
        columns.append(ColumnDef("branch.short_name", width=100))
        columns.append(
            ColumnDef(
                "participating_workgroups",
                width=200,
                formatter=_format_workgroups,
                filter_target=WorkingGroup,
            )
        )
    else:
        columns.extend(
            [
                ColumnDef(
                    "participating_departments",
                    width=180,
                    formatter=_format_departments,
                    filter_target=Department,
                ),
                ColumnDef(
                    "participating_workgroups",
                    width=200,
                    formatter=_format_workgroups,
                    filter_target=WorkingGroup,
                ),
                ColumnDef(
                    "participating_employees",
                    width=220,
                    formatter=_format_employees,
                    filter_target=Employee,
                ),
            ]
        )
    columns.extend(
        [
            ColumnDef(
                "tasks_display",
                width=140,
                filter_target=ScientificTask,
                filter_attr="tasks",
            ),
            ColumnDef("incoming_number", width=100),
            ColumnDef("incoming_date", width=110),
            ColumnDef("evaluation_display", width=90),
        ]
    )
    return columns


def telegram_columns(role: Optional[str] = None) -> List[ColumnDef]:
    """Возвращает описания столбцов таблицы телеграмм для роли."""
    columns = [
        ColumnDef("outgoing_number", width=100),
        ColumnDef("outgoing_date", width=110),
        ColumnDef("type", width=80, formatter=_format_telegram_type),
        ColumnDef("name", width=280),
        ColumnDef(
            "countries",
            width=150,
            formatter=_format_countries,
            filter_target=Country,
        ),
        ColumnDef(
            "sources",
            width=110,
            formatter=_format_sources,
            filter_target=Source,
        ),
        ColumnDef(
            "report_addresses",
            width=160,
            formatter=_format_addresses,
            filter_target=Leader,
            filter_attr="report_addresses",
        ),
        ColumnDef("report_type", width=100, formatter=_format_report_type),
    ]
    if _is_head_office(role):
        columns.append(ColumnDef("branch.short_name", width=100))
    else:
        columns.extend(
            [
                ColumnDef(
                    "participating_departments",
                    width=180,
                    formatter=_format_departments,
                    filter_target=Department,
                ),
                ColumnDef(
                    "participating_workgroups",
                    width=200,
                    formatter=_format_workgroups,
                    filter_target=WorkingGroup,
                ),
                ColumnDef(
                    "participating_employees",
                    width=220,
                    formatter=_format_employees,
                    filter_target=Employee,
                ),
            ]
        )
    columns.extend(
        [
            ColumnDef(
                "tasks_display",
                width=140,
                filter_target=ScientificTask,
                filter_attr="tasks",
            ),
            ColumnDef("incoming_number", width=100),
            ColumnDef("incoming_date", width=110),
            ColumnDef("evaluation_display", width=90),
        ]
    )
    return columns


# Описания столбцов таблицы научных материалов (роль «филиал»)
MATERIAL_COLUMNS = material_columns()

# Описания столбцов для таблицы телеграмм (роль «филиал»)
TELEGRAM_COLUMNS = telegram_columns()

# Описания столбцов справочников
TERRITORIAL_UNIT_COLUMNS = [
    ColumnDef("id", width=120),
    ColumnDef("name", width=300),
]

BRANCH_COLUMNS = [
    ColumnDef("id", width=100),
    ColumnDef("name", width=250),
    ColumnDef("short_name", width=100),
    ColumnDef("territorial_unit.name", width=150),
]

COUNTRY_COLUMNS = [
    ColumnDef("id", width=80),
    ColumnDef("name", width=300),
]

ACADEMIC_TITLE_COLUMNS = [
    ColumnDef("id", width=80),
    ColumnDef("name", width=200),
    ColumnDef("genitive", width=200),
    ColumnDef("dative", width=200),
    ColumnDef("sort_order", width=80),
]

SCIENTIFIC_TASK_COLUMNS = [
    ColumnDef("id", width=100),
    ColumnDef("name", width=300),
    ColumnDef("type", width=80, formatter=_format_task_type),
    ColumnDef("start_date", width=100),
    ColumnDef("end_date", width=100),
]

CONSUMER_COLUMNS = [
    ColumnDef("id", width=100),
    ColumnDef("short_name", width=150),
    ColumnDef("name", width=300),
]

LEADER_COLUMNS = [
    ColumnDef("id", width=150),
    ColumnDef("active", width=100),
]

SOURCE_COLUMNS = [
    ColumnDef("index", width=100),
    ColumnDef("type", width=100, formatter=_format_source_type),
    ColumnDef("comment", width=300),
]


def _ensure_storage_dirs(storage_root: Path) -> None:
    """Создаёт поддиректории файлового хранилища."""
    (storage_root / dir_name("files")).mkdir(parents=True, exist_ok=True)
    (storage_root / dir_name("templates")).mkdir(parents=True, exist_ok=True)
    (storage_root / dir_name("export")).mkdir(parents=True, exist_ok=True)


def _ensure_app_dirs(app_dir: Path) -> None:
    """Создаёт служебные директории приложения."""
    (app_dir / LOGS_DIR).mkdir(parents=True, exist_ok=True)
    (app_dir / BACKUPS_DIR).mkdir(parents=True, exist_ok=True)


class MainWindow(FramelessWindowMixin, QMainWindow):
    """Главное окно приложения."""

    def __init__(
        self,
        settings: AppSettings,
        db_manager: DatabaseManager,
        settings_manager: Optional[SettingsManager] = None,
        app_dir: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.db_manager = db_manager
        self._settings_manager = settings_manager or SettingsManager()
        self.app_dir = Path(app_dir) if app_dir is not None else Path(__file__).resolve().parent.parent.parent
        self.setWindowTitle(STRINGS.app_title)
        self.setMinimumSize(1024, 768)
        self._setup_ui()
        self._setup_menu()
        self._restore_ui_state()

    def _setup_ui(self) -> None:
        """Инициализирует интерфейс главного окна с вкладками."""
        container = QWidget()
        container.setObjectName("centralContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)

        from internal_correspondence.orm.models import ScientificMaterial, Telegram

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.materials_tab = DocumentListWidget(
            self.db_manager.get_session(),
            self.settings.storage_path_obj(),
            ScientificMaterial,
            material_columns(self.settings.role),
            self.settings.branch_id,
            role=self.settings.role,
            settings=self.settings,
        )
        self.telegram_tab = DocumentListWidget(
            self.db_manager.get_session(),
            self.settings.storage_path_obj(),
            Telegram,
            telegram_columns(self.settings.role),
            self.settings.branch_id,
            role=self.settings.role,
            settings=self.settings,
        )
        self.statistics_tab = StatisticsWidget(
            self.db_manager.get_session(),
            self.settings.branch_id if self.settings.role == Role.BRANCH.value else None,
        )
        self.tasks_tab = TaskDistributionWidget(
            self.db_manager.get_session(),
            self.settings.role,
            self.settings.branch_id,
        )
        self.dashboard_tab = DashboardWidget(
            self.db_manager.get_session(),
            self.settings.role,
            self.settings.branch_id,
            self.settings.storage_path_obj(),
        )

        self.tabs.addTab(self.dashboard_tab, STRINGS.tab_dashboard)
        self.tabs.addTab(self.materials_tab, entity_label(ScientificMaterial, plural=True))
        self.tabs.addTab(self.telegram_tab, entity_label(Telegram, plural=True))
        self.tabs.addTab(self.tasks_tab, STRINGS.tab_tasks)
        self.tabs.addTab(self.statistics_tab, STRINGS.tab_statistics)
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)

        self.materials_tab.filtersChanged.connect(self._materials_filters_changed)
        self.telegram_tab.filtersChanged.connect(self._telegram_filters_changed)
        self.tasks_tab.filtersChanged.connect(self._tasks_filters_changed)

        # Док-виджет прикреплённых файлов привязан к текущей записи вкладки
        self.files_dock = AttachedFilesWidget(
            self.db_manager.get_session(),
            self.settings.storage_path_obj(),
            self,
        )
        self.addDockWidget(Qt.RightDockWidgetArea, self.files_dock)
        self.files_dock.filesChanged.connect(self._on_files_changed)
        self.materials_tab.currentDocumentChanged.connect(
            lambda document: self._files_document_changed(self.materials_tab, document)
        )
        self.telegram_tab.currentDocumentChanged.connect(
            lambda document: self._files_document_changed(self.telegram_tab, document)
        )

        # Док-виджет файлов последнего импорта ведёт манифест импорта и имеет
        # смысл только в головном офисе: в филиале импорт пакетов не выполняется
        self.imported_files_dock: Optional[ImportedFilesWidget] = None
        if self.settings.role == Role.HEAD_OFFICE.value:
            self.imported_files_dock = ImportedFilesWidget(
                self.db_manager.get_session(),
                self.settings.storage_path_obj(),
                self,
            )
            # Правая область — как у панели прикреплённых файлов: панели
            # показываются на разных вкладках и не делят место одновременно
            self.addDockWidget(Qt.RightDockWidgetArea, self.imported_files_dock)

        # Выбор оператора (галочки меню «Вид») хранится отдельно от
        # фактической видимости: панель показывается только на своей вкладке
        self._files_dock_preference = True
        self._imported_files_dock_preference = True
        self._syncing_docks = False

        self.tabs.currentChanged.connect(lambda _index: self._on_tab_changed())
        self._on_tab_changed()

    def _on_tab_changed(self) -> None:
        """Синхронизирует доки с активной вкладкой."""
        self._sync_files_dock()
        self._update_docks_visibility()

    def _apply_dock_visibility(self, dock, visible: bool) -> None:
        """Показывает или скрывает док, не считая это выбором оператора."""
        self._syncing_docks = True
        try:
            dock.setVisible(visible)
        finally:
            self._syncing_docks = False

    def _is_document_tab(self) -> bool:
        """Проверяет, активна ли вкладка со списком документов."""
        return isinstance(self.tabs.currentWidget(), DocumentListWidget)

    def _update_docks_visibility(self) -> None:
        """Применяет правила показа доков для активной вкладки и роли.

        Прикреплённые файлы видны на вкладках документов на любом уровне,
        файлы последнего импорта — только на дашборде головного офиса. Выбор
        оператора учитывается в пределах разрешённых вкладок, поэтому смена
        вкладки не сбрасывает галочку меню.
        """
        self._apply_dock_visibility(
            self.files_dock,
            self._is_document_tab() and self._files_dock_preference,
        )
        if self.imported_files_dock is None:
            return
        show_imported = (
            self.tabs.currentWidget() is self.dashboard_tab
            and self._imported_files_dock_preference
        )
        self._apply_dock_visibility(self.imported_files_dock, show_imported)
        if show_imported:
            self.imported_files_dock.refresh()
    def _refresh_imported_files_dock(self) -> None:
        """Перечитывает манифест последнего импорта для открытой панели."""
        if self.imported_files_dock is not None:
            self.imported_files_dock.refresh()

    def _files_dock_visibility_changed(self, visible: bool) -> None:
        """Запоминает выбор оператора: панель закрыта или открыта вручную."""
        if self._syncing_docks:
            return
        self._files_dock_preference = visible
        self.files_dock_action.setChecked(visible)

    def _imported_files_dock_visibility_changed(self, visible: bool) -> None:
        """Запоминает выбор оператора для панели файлов последнего импорта."""
        if self._syncing_docks or self.imported_files_dock is None:
            return
        self._imported_files_dock_preference = visible
        if self.imported_files_dock_action is not None:
            self.imported_files_dock_action.setChecked(visible)

    def _files_document_changed(self, tab, document) -> None:
        """Привязывает док файлов к записи, если её вкладка активна."""
        if tab is self.tabs.currentWidget():
            self.files_dock.set_document(document)

    def _on_files_changed(self, document_id) -> None:
        """Обновляет подсветку строки после операций док-виджета с файлами.

        Записи Change создаются в сессии док-виджета, поэтому табличные
        модели перечитывают служебное состояние записи явно. Обновляем обе
        вкладки документов: док может быть привязан к записи, даже если
        активна другая вкладка (например, «Дашборд»).
        """
        for tab in (self.materials_tab, self.telegram_tab):
            tab.reload_document_state(document_id)

    def _sync_files_dock(self) -> None:
        """Обновляет док файлов при смене вкладки."""
        tab = self.tabs.currentWidget()
        if isinstance(tab, DocumentListWidget):
            self.files_dock.set_document(tab.current_document())
        else:
            self.files_dock.set_document(None)

    def _materials_filters_changed(self, filters) -> None:
        """Запоминает фильтры материалов для сохранения при закрытии."""
        self.settings.material_filters = serialize_filters(filters)

    def _telegram_filters_changed(self, filters) -> None:
        """Запоминает фильтры телеграмм для сохранения при закрытии."""
        self.settings.telegram_filters = serialize_filters(filters)

    def _tasks_filters_changed(self, filters) -> None:
        """Запоминает фильтры таблицы управления задачами."""
        self.settings.task_filters = serialize_filters(filters)

    def _setup_menu(self) -> None:
        """Формирует главное меню приложения."""
        menubar = self.menuBar()

        is_head_office = self.settings.role == Role.HEAD_OFFICE.value

        file_menu = menubar.addMenu(STRINGS.menu_file)
        settings_action = QAction(STRINGS.menu_settings, self)
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        export_action = QAction(STRINGS.action_export, self)
        export_action.triggered.connect(self._export)
        file_menu.addAction(export_action)

        import_action = QAction(STRINGS.action_import, self)
        import_action.triggered.connect(self._import)
        file_menu.addAction(import_action)

        file_menu.addSeparator()
        exit_action = QAction(STRINGS.menu_exit, self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню "Данные" — справочники
        data_menu = menubar.addMenu(STRINGS.menu_data)
        self._add_reference_action(
            data_menu,
            TerritorialUnit, TerritorialUnitService, TERRITORIAL_UNIT_COLUMNS,
            TerritorialUnitDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu,
            Branch, BranchService, BRANCH_COLUMNS,
            BranchDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu,
            Country, CountryService, COUNTRY_COLUMNS,
            CountryDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu,
            AcademicTitle, AcademicTitleService, ACADEMIC_TITLE_COLUMNS,
            AcademicTitleDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu,
            ScientificTask, ScientificTaskService, SCIENTIFIC_TASK_COLUMNS,
            ScientificTaskDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu,
            Consumer, ConsumerService, CONSUMER_COLUMNS,
            ConsumerDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu,
            Leader, LeaderService, LEADER_COLUMNS,
            LeaderDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu,
            Source, SourceService, SOURCE_COLUMNS,
            SourceDialog, is_head_office,
        )
        data_menu.addSeparator()
        import_primary_action = QAction(STRINGS.action_import_primary, self)
        import_primary_action.triggered.connect(self._import_primary_data)
        data_menu.addAction(import_primary_action)
        import_actual_action = QAction(STRINGS.action_import_actual, self)
        import_actual_action.triggered.connect(self._import_actual_data)
        data_menu.addAction(import_actual_action)

        data_menu.addSeparator()
        import_evaluations_action = QAction(STRINGS.menu_import_evaluations, self)
        import_evaluations_action.setEnabled(is_head_office)
        import_evaluations_action.triggered.connect(self._import_evaluations)
        data_menu.addAction(import_evaluations_action)
        evaluation_lists_action = QAction(STRINGS.menu_evaluation_lists, self)
        evaluation_lists_action.setObjectName("evaluationListsAction")
        evaluation_lists_action.triggered.connect(self._open_evaluation_lists)
        data_menu.addAction(evaluation_lists_action)
        data_menu.addSeparator()

        generate_report_action = QAction(STRINGS.action_generate_report, self)
        generate_report_action.setObjectName("generateReportAction")
        generate_report_action.triggered.connect(self._generate_report)
        data_menu.addAction(generate_report_action)
        data_menu.addSeparator()

        # Меню "ОШС"
        oshm_action = QAction(STRINGS.action_oshm, self)
        oshm_action.triggered.connect(self._open_oshm)
        data_menu.addAction(oshm_action)

        data_menu.addSeparator()
        domain_pack_action = QAction(STRINGS.action_domain_pack, self)
        domain_pack_action.triggered.connect(self._export_domain_pack)
        data_menu.addAction(domain_pack_action)

        # Меню "Вид" — оформление
        view_menu = menubar.addMenu(STRINGS.menu_view)
        theme_menu = view_menu.addMenu(STRINGS.menu_theme)
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for theme_key, theme in THEMES.items():
            action = QAction(theme.label, self)
            action.setCheckable(True)
            action.setChecked(theme_key == current_theme().key)
            action.triggered.connect(
                lambda _checked=False, key=theme_key: self._set_theme(key)
            )
            theme_group.addAction(action)
            theme_menu.addAction(action)

        # Показ/скрытие доков (восстановление — в _restore_ui_state)
        view_menu.addSeparator()
        self.files_dock_action = QAction(STRINGS.menu_attached_files, self)
        self.files_dock_action.setObjectName("filesDockAction")
        self.files_dock_action.setCheckable(True)
        self.files_dock_action.setChecked(self._files_dock_preference)
        self.files_dock_action.toggled.connect(self._files_dock_action_toggled)
        self.files_dock.visibilityChanged.connect(
            self._files_dock_visibility_changed
        )
        view_menu.addAction(self.files_dock_action)

        self.imported_files_dock_action: Optional[QAction] = None
        if self.imported_files_dock is not None:
            action = QAction(STRINGS.menu_imported_files, self)
            action.setObjectName("importedFilesDockAction")
            action.setCheckable(True)
            action.setChecked(self._imported_files_dock_preference)
            action.toggled.connect(self._imported_files_action_toggled)
            self.imported_files_dock.visibilityChanged.connect(
                self._imported_files_dock_visibility_changed
            )
            view_menu.addAction(action)
            self.imported_files_dock_action = action

        self.setup_custom_title_bar(
            menubar,
            self.windowTitle(),
            _window_control_labels(),
            self._organization_title(),
        )

    def _organization_title(self) -> str:
        """Возвращает подпись роли или выбранного филиала для шапки."""
        if self.settings.role == Role.HEAD_OFFICE.value:
            return STRINGS.role_head_office

        branch_id = str(self.settings.branch_id or "").strip()
        if not branch_id:
            return STRINGS.role_branch

        session = self.db_manager.get_session()
        try:
            branch = session.get(Branch, branch_id)
            if branch is not None and branch.name.strip():
                return f"{branch.id} — {branch.name.strip()}"
        except Exception:  # pylint: disable=broad-except
            logger.warning(
                "Не удалось получить наименование филиала %s для шапки",
                branch_id,
                exc_info=True,
            )
        finally:
            session.close()
        return branch_id

    def _refresh_organization_title(self) -> None:
        """Обновляет центральную подпись главной шапки."""
        self.window_context_title.set_context(self._organization_title())

    def _files_dock_action_toggled(self, checked: bool) -> None:
        """Включает или отключает док прикреплённых файлов из меню."""
        self._files_dock_preference = checked
        self._update_docks_visibility()

    def _imported_files_action_toggled(self, checked: bool) -> None:
        """Включает или отключает док файлов последнего импорта из меню."""
        self._imported_files_dock_preference = checked
        self._update_docks_visibility()

    def _add_reference_action(
        self,
        menu: QMenu,
        model_class,
        service_class,
        columns,
        dialog_factory,
        editable: bool,
    ) -> None:
        """Добавляет пункт меню для редактора справочника."""
        action = QAction(entity_label(model_class, plural=True), self)
        action.triggered.connect(
            lambda: self._open_reference_editor(
                model_class, service_class, columns, dialog_factory, editable
            )
        )
        menu.addAction(action)

    def _open_reference_editor(
        self,
        model_class,
        service_class,
        columns,
        dialog_factory,
        editable: bool,
    ) -> None:
        """Открывает редактор справочника с сессией, закрываемой в любом случае."""
        session = self.db_manager.get_session()
        try:
            ReferenceEditorDialog(
                session,
                model_class,
                service_class,
                columns,
                dialog_factory,
                read_only=not editable,
                parent=self,
            ).exec_()
        finally:
            session.close()

    def _open_settings(self) -> None:
        """Открывает диалог настроек."""
        dialog = SettingsDialog(self.settings, self.db_manager, self)
        if dialog.exec_() == SettingsDialog.Accepted:
            settings_manager = SettingsManager()
            settings_manager.save(self.settings)
            self._refresh_organization_title()
            QMessageBox.information(
                self,
                STRINGS.dialog_settings_title,
                STRINGS.msg_settings_saved,
            )

    def closeEvent(self, event) -> None:
        """Сохраняет геометрию окна, колонки и сортировку таблиц, док файлов."""
        self._save_ui_state()
        super().closeEvent(event)

    def _save_ui_state(self) -> None:
        """Сохраняет геометрию окна, колонки и сортировку таблиц, док в настройки."""
        self.settings.window_geometry = (
            self.saveGeometry().toBase64().data().decode("ascii")
        )
        self.settings.material_column_widths = ",".join(
            str(width) for width in self.materials_tab.column_widths()
        )
        self.settings.telegram_column_widths = ",".join(
            str(width) for width in self.telegram_tab.column_widths()
        )
        self.settings.material_columns_layout = self.materials_tab.columns_layout()
        self.settings.telegram_columns_layout = self.telegram_tab.columns_layout()
        self.settings.material_sort = _format_sort_state(
            self.materials_tab.sort_state()
        )
        self.settings.telegram_sort = _format_sort_state(
            self.telegram_tab.sort_state()
        )
        self.settings.task_columns_layout = (
            self.tasks_tab.management_widget.columns_layout()
        )
        self.settings.task_sort = _format_sort_state(
            self.tasks_tab.management_widget.sort_state()
        )
        self._save_files_dock_state()
        self._settings_manager.save(self.settings)

    def _save_files_dock_state(self) -> None:
        """Сохраняет настройки обоих доков: видимость, область и плавание."""
        self._save_dock_state(
            self.files_dock,
            self._files_dock_preference,
            "files_dock",
        )
        if self.imported_files_dock is not None:
            self._save_dock_state(
                self.imported_files_dock,
                self._imported_files_dock_preference,
                "imported_files_dock",
            )

    def _save_dock_state(self, dock, visible: bool, prefix: str) -> None:
        """Записывает состояние одного дока в поля настроек с префиксом.

        Сохраняется выбор оператора, а не фактическая видимость: панель может
        быть скрыта правилами активной вкладки, и это не должно выглядеть как
        отказ от панели при следующем запуске.
        """
        setattr(self.settings, f"{prefix}_visible", "true" if visible else "false")
        setattr(self.settings, f"{prefix}_area", str(int(self.dockWidgetArea(dock))))
        setattr(
            self.settings,
            f"{prefix}_floating",
            "true" if dock.isFloating() else "false",
        )
        # Геометрию храним только для плавающего окна: у пристыкованной
        # панели положение определяется областью и размерами главного окна.
        setattr(
            self.settings,
            f"{prefix}_geometry",
            dock.saveGeometry().toBase64().data().decode("ascii")
            if dock.isFloating()
            else "",
        )

    def _restore_ui_state(self) -> None:
        """Восстанавливает геометрию окна, колонки и сортировку таблиц, доки."""
        if self.settings.window_geometry:
            self.restoreGeometry(
                QByteArray.fromBase64(self.settings.window_geometry.encode("ascii"))
            )
        self._restore_files_dock_state()
        if self.settings.material_columns_layout:
            self.materials_tab.set_columns_layout(
                self.settings.material_columns_layout
            )
        else:
            material_widths = _parse_column_widths(
                self.settings.material_column_widths
            )
            if material_widths:
                self.materials_tab.set_column_widths(material_widths)
        if self.settings.telegram_columns_layout:
            self.telegram_tab.set_columns_layout(
                self.settings.telegram_columns_layout
            )
        else:
            telegram_widths = _parse_column_widths(
                self.settings.telegram_column_widths
            )
            if telegram_widths:
                self.telegram_tab.set_column_widths(telegram_widths)
        self._restore_table_sort(self.materials_tab, self.settings.material_sort)
        self._restore_table_sort(self.telegram_tab, self.settings.telegram_sort)
        if self.settings.task_columns_layout:
            self.tasks_tab.management_widget.set_columns_layout(
                self.settings.task_columns_layout
            )
        self._restore_table_sort(
            self.tasks_tab.management_widget, self.settings.task_sort
        )
        self._restore_filters()

    def _restore_table_sort(self, tab, raw: str) -> None:
        """Применяет сохранённую сортировку таблицы; чужие колонки игнорируются."""
        state = _parse_sort_state(raw)
        if state is not None:
            tab.set_sort_state(state[0], state[1])

    def _restore_files_dock_state(self) -> None:
        """Восстанавливает состояние обоих доков и применяет правила показа."""
        self._files_dock_preference = self._restore_dock_state(
            self.files_dock, "files_dock", True
        )
        self.files_dock_action.setChecked(self._files_dock_preference)
        if self.imported_files_dock is not None:
            self._imported_files_dock_preference = self._restore_dock_state(
                self.imported_files_dock, "imported_files_dock", True
            )
            if self.imported_files_dock_action is not None:
                self.imported_files_dock_action.setChecked(
                    self._imported_files_dock_preference
                )
        self._update_docks_visibility()

    def _restore_dock_state(self, dock, prefix: str, default: bool) -> bool:
        """Восстанавливает область, плавание и выбор видимости одного дока."""
        raw_area = getattr(self.settings, f"{prefix}_area", "")
        try:
            area = Qt.DockWidgetArea(int(raw_area))
        except (TypeError, ValueError):
            area = Qt.RightDockWidgetArea
        if area not in (
            Qt.LeftDockWidgetArea,
            Qt.RightDockWidgetArea,
            Qt.TopDockWidgetArea,
            Qt.BottomDockWidgetArea,
        ):
            area = Qt.RightDockWidgetArea
        self.addDockWidget(area, dock)
        floating = _parse_bool(getattr(self.settings, f"{prefix}_floating", ""), False)
        dock.setFloating(floating)
        raw_geometry = getattr(self.settings, f"{prefix}_geometry", "")
        if floating and raw_geometry:
            dock.restoreGeometry(
                QByteArray.fromBase64(raw_geometry.encode("ascii"))
            )
        # visibilityChanged не приходит, пока окно не показано: показ панели
        # выполняет _update_docks_visibility по правилам активной вкладки
        return _parse_bool(
            getattr(self.settings, f"{prefix}_visible", ""), default
        )

    def _restore_filters(self) -> None:
        """Восстанавливает фильтры таблиц из настроек (два набора раздельно)."""
        self.materials_tab.set_filters(
            deserialize_filters(self.settings.material_filters, ScientificMaterial)
        )
        self.telegram_tab.set_filters(
            deserialize_filters(self.settings.telegram_filters, Telegram)
        )
        self.tasks_tab.management_widget.set_filters(
            deserialize_filters(
                self.settings.task_filters, ScientificTask
            )
        )

    def _set_theme(self, theme_key: str) -> None:
        """Применяет тему оформления и сохраняет выбор в настройках."""
        if (
            self.settings.theme == theme_key
            and current_theme().key == theme_key
        ):
            return
        theme = apply_theme(QApplication.instance(), theme_key)
        self.window_controls.refresh_icons()
        # Перекрашиваем строки таблиц и графики
        self.materials_tab.refresh()
        self.telegram_tab.refresh()
        self.tasks_tab.apply_theme()
        self.statistics_tab.apply_theme()
        self.dashboard_tab.apply_theme()
        self.settings.theme = theme.key
        self._settings_manager.save(self.settings)

    def _export(self) -> None:
        """Формирует экспортные ZIP-архивы (в отдельном потоке)."""
        storage_root = self.settings.storage_path_obj()
        retention_days = _changes_retention_days(self.settings)

        branch_ids: Optional[List[str]] = None
        if self.settings.role == Role.HEAD_OFFICE.value:
            session = self.db_manager.get_session()
            try:
                service = ExportService(
                    session,
                    storage_root,
                    retention_days=retention_days,
                    role=self.settings.role,
                    branch_id=self.settings.branch_id,
                )
                pending = service.pending_branches()
            finally:
                session.close()
            if not pending:
                QMessageBox.information(
                    self, STRINGS.title_export, STRINGS.msg_export_no_changes
                )
                return
            dialog = ExportBranchesDialog(pending, self)
            if dialog.exec_() != QDialog.Accepted:
                return
            branch_ids = dialog.selected_branch_ids()
            if not branch_ids:
                return

        self._run_export_worker(storage_root, retention_days, branch_ids)

    def _run_export_worker(
        self,
        storage_root: Path,
        retention_days: int,
        branch_ids: Optional[List[str]],
    ) -> None:
        """Запускает формирование архивов в потоке с прогресс-диалогом."""
        thread = QThread(self)
        worker = ExportWorker(
            self.db_manager,
            storage_root,
            retention_days,
            self.settings.role,
            self.settings.branch_id,
            branch_ids,
        )
        worker.moveToThread(thread)

        progress = QProgressDialog(
            STRINGS.progress_export_caption,
            STRINGS.button_cancel,
            0,
            100,
            self,
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        worker.progressed.connect(
            lambda current, total, message: self._on_export_progress(
                progress, current, total, message
            )
        )
        worker.succeeded.connect(
            lambda outputs: self._on_export_finished(thread, worker, progress, outputs)
        )
        worker.failed.connect(
            lambda error: self._on_export_failed(thread, worker, progress, error)
        )
        thread.started.connect(worker.run)
        # Пока поток жив, держим ссылки на объекты в атрибутах окна.
        self._export_thread = thread
        self._export_worker = worker
        thread.start()

    @staticmethod
    def _on_export_progress(
        progress: QProgressDialog, current: int, total: int, message: str
    ) -> None:
        """Обновляет прогресс-диалог экспорта."""
        progress.setMaximum(max(total, 1))
        progress.setLabelText(message)
        progress.setValue(current)

    def _on_export_finished(
        self,
        thread: QThread,
        worker: ExportWorker,
        progress: QProgressDialog,
        outputs: List[str],
    ) -> None:
        """Завершает экспорт: освобождает поток, показывает результат."""
        thread.quit()
        thread.wait()
        progress.close()
        self.materials_tab.refresh()
        self.telegram_tab.refresh()
        self.dashboard_tab.refresh()
        QMessageBox.information(
            self,
            STRINGS.title_export,
            STRINGS.msg_export_files_done.format(files="\n".join(outputs)),
        )

    def _on_export_failed(
        self,
        thread: QThread,
        worker: ExportWorker,
        progress: QProgressDialog,
        error: str,
    ) -> None:
        """Показывает ошибку экспорта; изменения остаются неэкспортированными."""
        thread.quit()
        thread.wait()
        progress.close()
        logger.exception("Ошибка экспорта")
        QMessageBox.critical(
            self, STRINGS.title_error, STRINGS.msg_export_error.format(error=error)
        )

    def _import(self) -> None:
        """Импортирует ZIP-архив: анализ, подтверждение, применение (в потоке)."""
        path, _ = QFileDialog.getOpenFileName(
            self, STRINGS.dialog_select_export_file, "", "ZIP (*.zip)"
        )
        if not path:
            return
        session = self.db_manager.get_session()
        try:
            service = ImportService(
                session,
                self.settings.storage_path_obj(),
                self.settings.role,
                self.settings.branch_id,
            )
            analysis = service.analyze_archive(Path(path))
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка анализа импортируемого архива")
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_import_error.format(error=exc)
            )
            return
        finally:
            session.close()

        entries = analysis["entries"]
        preview = ImportPreviewDialog(entries, self)
        if preview.exec_() != QDialog.Accepted:
            QMessageBox.information(
                self, STRINGS.title_import, STRINGS.msg_import_canceled
            )
            return
        exclude = preview.excluded_keys(entries)
        rejected = [entry for entry in entries if entry["status"] == "error"]
        self._import_analysis_warnings = list(analysis.get("warnings") or [])
        self._run_import_worker(Path(path), exclude, rejected)

    def _run_import_worker(
        self,
        archive_path: Path,
        exclude: Set[Tuple[str, str]],
        rejected: List[Dict[str, Any]],
    ) -> None:
        """Запускает применение импорта в потоке с прогресс-диалогом."""
        thread = QThread(self)
        worker = ImportWorker(
            self.db_manager,
            self.settings.storage_path_obj(),
            self.settings.role,
            self.settings.branch_id,
            archive_path,
            exclude,
            rejected,
        )
        worker.moveToThread(thread)

        progress = QProgressDialog(
            STRINGS.progress_import_caption,
            STRINGS.button_cancel,
            0,
            100,
            self,
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        worker.progressed.connect(
            lambda current, total, message: self._on_import_progress(
                progress, current, total, message
            )
        )
        worker.succeeded.connect(
            lambda payload: self._on_import_finished(thread, worker, progress, payload)
        )
        worker.failed.connect(
            lambda error: self._on_import_failed(thread, worker, progress, error)
        )
        thread.started.connect(worker.run)
        # Пока поток жив, держим ссылки на объекты в атрибутах окна.
        self._import_thread = thread
        self._import_worker = worker
        thread.start()

    @staticmethod
    def _on_import_progress(
        progress: QProgressDialog, current: int, total: int, message: str
    ) -> None:
        """Обновляет прогресс-диалог импорта."""
        progress.setMaximum(max(total, 1))
        progress.setLabelText(message)
        progress.setValue(current)

    def _on_import_finished(
        self,
        thread: QThread,
        worker: ImportWorker,
        progress: QProgressDialog,
        payload: Dict[str, Any],
    ) -> None:
        """Завершает импорт: освобождает поток, показывает результат."""
        thread.quit()
        thread.wait()
        progress.close()
        result = payload["result"]
        recorded = payload["recorded"]
        message = STRINGS.msg_import_result.format(
            imported=result["imported"],
            deleted=result["deleted"],
            skipped=result["skipped"],
            conflicts=len(result["conflicts"]),
        )
        warnings = list(getattr(self, "_import_analysis_warnings", [])) + list(
            result.get("warnings") or []
        )
        if warnings:
            message += f"\n\n{STRINGS.msg_import_warnings}\n" + "\n".join(warnings)
        if recorded:
            message += "\n" + STRINGS.msg_missing_recorded.format(count=recorded)
        QMessageBox.information(self, STRINGS.title_import, message)
        self.materials_tab.refresh()
        self.telegram_tab.refresh()
        self.tasks_tab.refresh_all()
        self.statistics_tab.refresh()
        self.dashboard_tab.refresh()
        # Манифест последнего импорта перезаписан сервисом: панель дашборда
        # должна показать новый состав файлов, даже если она уже открыта
        self._refresh_imported_files_dock()

    def _on_import_failed(
        self,
        thread: QThread,
        worker: ImportWorker,
        progress: QProgressDialog,
        error: str,
    ) -> None:
        """Показывает ошибку импорта; транзакция откачена в воркере."""
        thread.quit()
        thread.wait()
        progress.close()
        logger.exception("Ошибка импорта")
        QMessageBox.critical(
            self, STRINGS.title_error, STRINGS.msg_import_error.format(error=error)
        )

    def _import_primary_data(self) -> None:
        """Импортирует первичные справочные данные из XLSX."""
        path, _ = QFileDialog.getOpenFileName(
            self, STRINGS.dialog_primary_data_file, "", "Excel (*.xlsx)"
        )
        if not path:
            return
        self._import_reference_file(Path(path), import_primary_data, "первичных данных")

    def _import_actual_data(self) -> None:
        """Импортирует актуальные справочные данные из XLSX."""
        path, _ = QFileDialog.getOpenFileName(
            self, STRINGS.dialog_actual_data_file, "", "Excel (*.xlsx)"
        )
        if not path:
            return
        self._import_reference_file(Path(path), import_actual_data, "актуальных данных")

    def _import_reference_file(self, path: Path, importer, subject: str) -> None:
        """Импортирует справочный файл одной сессией с закрытием в любом случае."""
        session = self.db_manager.get_session()
        try:
            results = importer(session, path)
            session.commit()
            self.dashboard_tab.refresh()
            QMessageBox.information(
                self,
                STRINGS.title_import,
                STRINGS.msg_import_done.format(
                    results=self._format_import_results(results)
                ),
            )
        except Exception as exc:  # pylint: disable=broad-except
            session.rollback()
            logger.exception("Ошибка импорта %s", subject)
            QMessageBox.critical(self, STRINGS.title_error, str(exc))
        finally:
            session.close()

    def _format_import_results(self, results: dict) -> str:
        """Форматирует результаты импорта для сообщения."""
        return "\n".join(f"{sheet}: {count}" for sheet, count in results.items())

    def _import_evaluations(self) -> None:
        """Открывает мастер импорта оценок из текстового файла (только ГО)."""
        if self.settings.role != Role.HEAD_OFFICE.value:
            QMessageBox.warning(
                self,
                STRINGS.title_error,
                STRINGS.msg_import_head_office_only,
            )
            return
        config = ImporterConfig(
            file_storage_dir=self.settings.storage_path_obj(),
            schemes_dir=self.app_dir / "schemes",
            matcher_rules_path=self.app_dir / "matcher_rules.json",
            storage_subdir=dir_name("import"),
        )
        dialog = EvaluationImportDialog(config, self.db_manager.engine, self)
        try:
            dialog.exec_()
        finally:
            dialog.importer.close()
        self.materials_tab.refresh()
        self.telegram_tab.refresh()
        self.statistics_tab.refresh()
        self.dashboard_tab.refresh()

    def _open_evaluation_lists(self) -> None:
        """Открывает просмотр журналов импорта оценок (только чтение)."""
        dialog = EvaluationListsDialog(self.db_manager.engine, self)
        dialog.exec_()

    def _generate_report(self) -> None:
        """Открывает диалог и формирует аналитический отчёт в DOCX."""
        branch_id = (
            self.settings.branch_id
            if self.settings.role == Role.BRANCH.value
            else None
        )
        if self.settings.role == Role.BRANCH.value and not branch_id:
            QMessageBox.warning(
                self,
                STRINGS.title_generate_report,
                STRINGS.report_msg_no_branch,
            )
            return

        session = self.db_manager.get_session()
        progress_dialog: Optional[QProgressDialog] = None
        output: Optional[Path] = None
        report_error: Optional[Exception] = None
        try:
            dialog = ReportDialog(session, branch_id=branch_id, parent=self)
            if not dialog.exec_():
                return
            request = dialog.selected_request()
            month_names = dialog.month_names()
            if request.report_type == ReportType.MONTH:
                filename = STRINGS.report_month_filename.format(
                    month=month_names[request.period_number - 1].lower(),
                    year=request.year,
                )
            else:
                filename = STRINGS.report_half_filename.format(
                    half=request.period_number,
                    year=request.year,
                )
            output_dir = self.settings.storage_path_obj() / dir_name("export")
            output_dir.mkdir(parents=True, exist_ok=True)
            path, _ = QFileDialog.getSaveFileName(
                self,
                STRINGS.report_dialog_save,
                str(output_dir / filename),
                STRINGS.report_file_filter,
            )
            if not path:
                return

            progress_dialog = _create_report_progress_dialog(self)
            progress_dialog.show()
            QApplication.processEvents()

            service = ReportDataService(session)
            service.save_draft(request, dialog.draft_values())
            session.commit()
            context = service.build_context(request, month_names)
            output = render_report(
                request.report_type,
                context,
                self.settings.storage_path_obj(),
                Path(path),
            )
        except Exception as exc:  # pylint: disable=broad-except
            session.rollback()
            logger.exception("Ошибка формирования аналитического отчёта")
            report_error = exc
        finally:
            if progress_dialog is not None:
                progress_dialog.close()
                progress_dialog.deleteLater()
                QApplication.processEvents()
            session.close()

        if report_error is not None:
            QMessageBox.critical(
                self,
                STRINGS.title_error,
                STRINGS.report_msg_error.format(error=report_error),
            )
        elif output is not None:
            QMessageBox.information(
                self,
                STRINGS.title_generate_report,
                STRINGS.report_msg_done.format(output=output),
            )

    def _export_domain_pack(self) -> None:
        """Выгружает активный пакет предметной области в JSON-файл."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            STRINGS.dialog_domain_pack_save,
            "domain_pack.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            save_domain_pack(get_domain_pack(), Path(path))
        except OSError as exc:
            logger.exception("Ошибка сохранения пакета предметной области")
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_pack_save_error.format(error=exc)
            )
            return
        answer = QMessageBox.question(
            self,
            STRINGS.title_domain_pack,
            STRINGS.msg_pack_saved_use.format(path=path),
        )
        if answer == QMessageBox.Yes:
            self.settings.domain_pack = path
            SettingsManager().save(self.settings)

    def _open_oshm(self) -> None:
        """Открывает диалог ОШС: головной офис видит все филиалы, филиал — себя."""
        is_head_office = self.settings.role == Role.HEAD_OFFICE.value
        branch_id = self.settings.branch_id
        if not is_head_office and not branch_id:
            QMessageBox.warning(self, STRINGS.title_oshm, STRINGS.msg_no_branch_selected)
            return
        session = self.db_manager.get_session()
        dialog = OSHMDialog(
            session,
            branch_id=branch_id or None,
            role=self.settings.role,
            storage_root=self.settings.storage_path_obj(),
            parent=self,
        )
        # Кнопка «Статистика» на панели сведений: диалог закрывается,
        # открывается вкладка статистики с выделенной строкой элемента
        self._oshm_statistics_node = None
        dialog.details_panel.statistics_requested.connect(
            lambda node: self._on_oshm_statistics(dialog, node)
        )
        try:
            dialog.exec_()
        finally:
            session.close()
        if self._oshm_statistics_node is not None:
            self.tabs.setCurrentWidget(self.statistics_tab)
            self.statistics_tab.show_element(self._oshm_statistics_node)
            self._oshm_statistics_node = None

    def _on_oshm_statistics(self, dialog: OSHMDialog, node) -> None:
        """Запоминает элемент ОШС для статистики и закрывает диалог."""
        self._oshm_statistics_node = node
        dialog.accept()


def _changes_retention_days(settings: AppSettings) -> int:
    """Возвращает срок хранения записей Change в днях (<= 0 — бессрочно)."""
    try:
        return int(settings.changes_retention_days)
    except (TypeError, ValueError):
        return DEFAULT_CHANGES_RETENTION_DAYS


def _load_or_create_settings(
    app_dir: Path,
) -> Tuple[AppSettings, Optional[InitialBranchImport]]:
    """Загружает настройки или запускает мастер первого запуска.

    Returns:
        Пара (настройки, план первоначальной загрузки филиала из архива
        головного офиса — только если он выбран в мастере).
    """
    settings_manager = SettingsManager(app_dir)
    if settings_manager.exists:
        return settings_manager.load(), None

    settings, initial_import = run_first_run_wizard()
    if settings is None:
        sys.exit(0)

    settings_manager.save(settings)
    return settings, initial_import


def run_application(argv: List[str]) -> int:
    """Инициализирует и запускает приложение."""
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, False)
    app = QApplication(argv)
    app.setStyle("Fusion")

    app_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent
    configure_logging(app_dir)
    _ensure_app_dirs(app_dir)

    install_translations(app)

    # Светлая тема оформляет в том числе мастер первого запуска; после чтения
    # настроек ниже она заменяется сохранённой темой пользователя.
    apply_theme(app, "light")
    install_dialog_title_bars(app, _window_control_labels)

    settings, initial_import = _load_or_create_settings(app_dir)
    _ensure_storage_dirs(settings.storage_path_obj())
    apply_theme(app, settings.theme)

    # Пакет предметной области: внешний файл из настроек или встроенный
    try:
        init_domain_pack(Path(settings.domain_pack) if settings.domain_pack else None)
    except DomainPackError as exc:
        logger.exception("Ошибка загрузки пакета предметной области")
        QMessageBox.warning(
            None,
            STRINGS.title_domain_pack,
            STRINGS.msg_pack_load_error.format(path=settings.domain_pack, error=exc),
        )
    reload_strings()

    register_change_tracking()

    db_manager = DatabaseManager(settings.db_url, app_dir)
    try:
        db_manager.create_tables()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Ошибка инициализации БД")
        QMessageBox.critical(None, STRINGS.title_error, STRINGS.msg_db_error.format(error=exc))
        return 1

    # Первоначальная загрузка филиала из архива головного офиса (выбрана
    # в мастере первого запуска): применяется до открытия главного окна.
    if initial_import is not None:
        try:
            import_session = db_manager.get_session()
            try:
                run_initial_import(
                    import_session, settings.storage_path_obj(), initial_import
                )
                import_session.commit()
            finally:
                import_session.close()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка первоначальной загрузки из архива ГО")
            QMessageBox.warning(
                None,
                STRINGS.title_attention,
                STRINGS.wizard_archive_import_error.format(error=exc),
            )

    # Удаление устаревших записей Change по настройке срока хранения
    try:
        purge_session = db_manager.get_session()
        try:
            purge_expired_changes(purge_session, _changes_retention_days(settings))
            purge_session.commit()
        finally:
            purge_session.close()
    except Exception:  # pylint: disable=broad-except
        logger.exception("Ошибка очистки устаревших записей Change")

    # Проверка кодов перечислений в БД на соответствие активному пакету
    try:
        check_session = db_manager.get_session()
        try:
            code_warnings = validate_enum_codes(check_session)
        finally:
            check_session.close()
        if code_warnings:
            QMessageBox.warning(
                None,
                STRINGS.title_domain_pack,
                STRINGS.msg_unknown_codes_in_db + "\n".join(code_warnings),
            )
    except Exception:  # pylint: disable=broad-except
        logger.exception("Не удалось проверить коды перечислений в БД")

    window = MainWindow(settings, db_manager, app_dir=app_dir)
    window.show()

    return app.exec_()
