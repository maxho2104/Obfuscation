"""Главный модуль GUI-приложения."""

import os
import sys
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QFileDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import (
    BACKUPS_DIR,
    DEFAULT_CHANGES_RETENTION_DAYS,
    LOGS_DIR,
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
from internal_correspondence.gui.document_list_widget import DocumentListWidget
from internal_correspondence.gui.filter_model import (
    deserialize_filters,
    serialize_filters,
)
from internal_correspondence.gui.first_run_wizard import run_first_run_wizard
from internal_correspondence.gui.i18n import install_translations
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
from internal_correspondence.gui.settings_dialog import SettingsDialog
from internal_correspondence.gui.statistics_widget import StatisticsWidget
from internal_correspondence.gui.task_distribution_widget import TaskDistributionWidget
from internal_correspondence.gui.table_model import ColumnDef
from internal_correspondence.gui.theme import THEMES, apply_theme, current_theme
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
    Leader,
    ScientificMaterial,
    ScientificTask,
    Source,
    Telegram,
    TerritorialUnit,
)
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
from internal_correspondence.utils.string_resources import STRINGS, reload_strings

logger = get_logger("application")


def _parse_column_widths(raw: str) -> List[int]:
    """Разбирает сохранённые ширины колонок из строки настроек."""
    widths = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            widths.append(int(part))
    return widths


def _format_employees(employees) -> str:
    """Форматирует список причастных сотрудников для ячейки таблицы."""
    return ", ".join(employee.display_name() for employee in employees or [])


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
    """Форматирует список участвовавших отделов для ячейки таблицы."""
    return ", ".join(
        department.short_name or department.name for department in departments or []
    )


def _format_workgroups(workgroups) -> str:
    """Форматирует список участвовавших рабочих групп для ячейки таблицы."""
    return ", ".join(workgroup.name for workgroup in workgroups or [])


def _format_countries(countries) -> str:
    """Форматирует список стран происхождения данных для ячейки таблицы."""
    return ", ".join(country.name for country in countries or [])


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
        ColumnDef("countries", width=150, formatter=_format_countries),
        ColumnDef("consumer.short_name", width=120),
    ]
    if _is_head_office(role):
        columns.append(ColumnDef("branch.short_name", width=100))
        columns.append(
            ColumnDef("participating_workgroups", width=200, formatter=_format_workgroups)
        )
    else:
        columns.extend(
            [
                ColumnDef("participating_departments", width=180, formatter=_format_departments),
                ColumnDef("participating_workgroups", width=200, formatter=_format_workgroups),
                ColumnDef("participating_employees", width=220, formatter=_format_employees),
            ]
        )
    columns.extend(
        [
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
        ColumnDef("countries", width=150, formatter=_format_countries),
        ColumnDef("report_addresses", width=160, formatter=_format_addresses),
        ColumnDef("report_type", width=100, formatter=_format_report_type),
    ]
    if _is_head_office(role):
        columns.append(ColumnDef("branch.short_name", width=100))
    else:
        columns.extend(
            [
                ColumnDef("participating_departments", width=180, formatter=_format_departments),
                ColumnDef("participating_workgroups", width=200, formatter=_format_workgroups),
                ColumnDef("participating_employees", width=220, formatter=_format_employees),
            ]
        )
    columns.extend(
        [
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
    ColumnDef("id", width=100),
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


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(
        self,
        settings: AppSettings,
        db_manager: DatabaseManager,
        settings_manager: Optional[SettingsManager] = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.db_manager = db_manager
        self._settings_manager = settings_manager or SettingsManager()
        self.setWindowTitle(STRINGS.app_title)
        self.setMinimumSize(1024, 768)
        self._setup_ui()
        self._setup_menu()
        self._restore_ui_state()

    def _setup_ui(self) -> None:
        """Инициализирует интерфейс главного окна с вкладками."""
        container = QWidget()
        layout = QVBoxLayout(container)

        from internal_correspondence.orm.models import ScientificMaterial, Telegram

        self.tabs = QTabWidget()
        self.materials_tab = DocumentListWidget(
            self.db_manager.get_session(),
            self.settings.storage_path_obj(),
            ScientificMaterial,
            material_columns(self.settings.role),
            self.settings.branch_id,
            role=self.settings.role,
        )
        self.telegram_tab = DocumentListWidget(
            self.db_manager.get_session(),
            self.settings.storage_path_obj(),
            Telegram,
            telegram_columns(self.settings.role),
            self.settings.branch_id,
            role=self.settings.role,
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

        self.tabs.addTab(self.materials_tab, entity_label(ScientificMaterial, plural=True))
        self.tabs.addTab(self.telegram_tab, entity_label(Telegram, plural=True))
        self.tabs.addTab(self.tasks_tab, STRINGS.tab_tasks)
        self.tabs.addTab(self.statistics_tab, STRINGS.tab_statistics)
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)

        self.materials_tab.filtersChanged.connect(self._materials_filters_changed)
        self.telegram_tab.filtersChanged.connect(self._telegram_filters_changed)

        # Док-виджет прикреплённых файлов привязан к текущей записи вкладки
        self.files_dock = AttachedFilesWidget(
            self.db_manager.get_session(),
            self.settings.storage_path_obj(),
            self,
        )
        self.addDockWidget(Qt.RightDockWidgetArea, self.files_dock)
        self.tabs.currentChanged.connect(lambda _index: self._sync_files_dock())
        self.materials_tab.currentDocumentChanged.connect(
            lambda document: self._files_document_changed(self.materials_tab, document)
        )
        self.telegram_tab.currentDocumentChanged.connect(
            lambda document: self._files_document_changed(self.telegram_tab, document)
        )
        self._sync_files_dock()

    def _files_document_changed(self, tab, document) -> None:
        """Привязывает док файлов к записи, если её вкладка активна."""
        if tab is self.tabs.currentWidget():
            self.files_dock.set_document(document)

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

    def _setup_menu(self) -> None:
        """Формирует главное меню приложения."""
        menubar = self.menuBar()
        if menubar is None:
            return

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
            lambda: ReferenceEditorDialog(
                self.db_manager.get_session(),
                model_class,
                service_class,
                columns,
                dialog_factory,
                read_only=not editable,
                parent=self,
            ).exec_()
        )
        menu.addAction(action)

    def _open_settings(self) -> None:
        """Открывает диалог настроек."""
        dialog = SettingsDialog(self.settings, self.db_manager, self)
        if dialog.exec_() == SettingsDialog.Accepted:
            settings_manager = SettingsManager()
            settings_manager.save(self.settings)
            QMessageBox.information(
                self,
                STRINGS.dialog_settings_title,
                STRINGS.msg_settings_saved,
            )

    def closeEvent(self, event) -> None:
        """Сохраняет геометрию окна и ширины колонок при закрытии."""
        self._save_ui_state()
        super().closeEvent(event)

    def _save_ui_state(self) -> None:
        """Сохраняет геометрию окна и ширины колонок таблиц в настройки."""
        self.settings.window_geometry = (
            self.saveGeometry().toBase64().data().decode("ascii")
        )
        self.settings.material_column_widths = ",".join(
            str(width) for width in self.materials_tab.column_widths()
        )
        self.settings.telegram_column_widths = ",".join(
            str(width) for width in self.telegram_tab.column_widths()
        )
        self._settings_manager.save(self.settings)

    def _restore_ui_state(self) -> None:
        """Восстанавливает геометрию окна и ширины колонок из настроек."""
        if self.settings.window_geometry:
            self.restoreGeometry(
                QByteArray.fromBase64(self.settings.window_geometry.encode("ascii"))
            )
        material_widths = _parse_column_widths(self.settings.material_column_widths)
        if material_widths:
            self.materials_tab.set_column_widths(material_widths)
        telegram_widths = _parse_column_widths(self.settings.telegram_column_widths)
        if telegram_widths:
            self.telegram_tab.set_column_widths(telegram_widths)
        self._restore_filters()

    def _restore_filters(self) -> None:
        """Восстанавливает фильтры таблиц из настроек (два набора раздельно)."""
        self.materials_tab.set_filters(
            deserialize_filters(self.settings.material_filters, ScientificMaterial)
        )
        self.telegram_tab.set_filters(
            deserialize_filters(self.settings.telegram_filters, Telegram)
        )

    def _set_theme(self, theme_key: str) -> None:
        """Применяет тему оформления и сохраняет выбор в настройках."""
        if self.settings.theme == theme_key:
            return
        self.settings.theme = theme_key
        apply_theme(QApplication.instance(), theme_key)
        self._settings_manager.save(self.settings)
        # Перекрашиваем строки таблиц и графики
        self.materials_tab.refresh()
        self.telegram_tab.refresh()
        self.tasks_tab.apply_theme()
        self.statistics_tab.apply_theme()

    def _export(self) -> None:
        """Формирует экспортный ZIP-архив."""
        session = self.db_manager.get_session()
        try:
            service = ExportService(
                session,
                self.settings.storage_path_obj(),
                retention_days=_changes_retention_days(self.settings),
            )
            output = service.export()
            session.commit()
            self.materials_tab.refresh()
            self.telegram_tab.refresh()
            QMessageBox.information(
                self, STRINGS.title_export, STRINGS.msg_export_done.format(output=output)
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка экспорта")
            session.rollback()
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_export_error.format(error=exc)
            )
        finally:
            session.close()

    def _import(self) -> None:
        """Импортирует ZIP-архив."""
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
            result = service.import_archive(Path(path))
            message = STRINGS.msg_import_result.format(
                imported=result["imported"],
                deleted=result["deleted"],
                skipped=result["skipped"],
                conflicts=len(result["conflicts"]),
            )
            warnings = result.get("warnings") or []
            if warnings:
                message += f"\n\n{STRINGS.msg_import_warnings}\n" + "\n".join(warnings)
            QMessageBox.information(self, STRINGS.title_import, message)
            self.materials_tab.refresh()
            self.telegram_tab.refresh()
            self.tasks_tab.refresh_all()
            self.statistics_tab.refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка импорта")
            session.rollback()
            QMessageBox.critical(
                self, STRINGS.title_error, STRINGS.msg_import_error.format(error=exc)
            )
        finally:
            session.close()

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
        dialog = OSHMDialog(
            self.db_manager.get_session(),
            branch_id=branch_id or None,
            role=self.settings.role,
            parent=self,
        )
        # Кнопка «Статистика» на панели сведений: диалог закрывается,
        # открывается вкладка статистики с выделенной строкой элемента
        self._oshm_statistics_node = None
        dialog.details_panel.statistics_requested.connect(
            lambda node: self._on_oshm_statistics(dialog, node)
        )
        dialog.exec_()
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


def _load_or_create_settings(app_dir: Path) -> AppSettings:
    """Загружает настройки или запускает мастер первого запуска."""
    settings_manager = SettingsManager(app_dir)
    if settings_manager.exists:
        return settings_manager.load()

    settings = run_first_run_wizard()
    if settings is None:
        sys.exit(0)

    settings_manager.save(settings)
    return settings


def run_application(argv: List[str]) -> int:
    """Инициализирует и запускает приложение."""
    app = QApplication(argv)

    app_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent
    configure_logging(app_dir)
    _ensure_app_dirs(app_dir)

    install_translations(app)

    settings = _load_or_create_settings(app_dir)
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

    window = MainWindow(settings, db_manager)
    window.show()

    return app.exec_()
