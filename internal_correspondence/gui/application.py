"""Главный модуль GUI-приложения."""

import os
import sys
from pathlib import Path
from typing import List

from PyQt5.QtWidgets import (
    QAction,
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
    EXPORT_DIR,
    FILES_DIR,
    LOGS_DIR,
    Role,
    TEMPLATES_DIR,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.logging_config import configure_logging, get_logger
from internal_correspondence.core.settings import AppSettings, SettingsManager
from internal_correspondence.gui.document_list_widget import DocumentListWidget
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
from internal_correspondence.gui.table_model import ColumnDef
from internal_correspondence.importexport.export_service import ExportService
from internal_correspondence.importexport.import_service import ImportService
from internal_correspondence.importexport.reference_import import (
    import_actual_data,
    import_primary_data,
)
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
from internal_correspondence.services.change_tracking import register_change_tracking
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
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("application")


def _format_employees(employees) -> str:
    """Форматирует список причастных сотрудников для ячейки таблицы."""
    return ", ".join(employee.display_name() for employee in employees or [])


def _format_departments(departments) -> str:
    """Форматирует список участвовавших отделов для ячейки таблицы."""
    return ", ".join(
        department.short_name or department.name for department in departments or []
    )


def _format_workgroups(workgroups) -> str:
    """Форматирует список участвовавших рабочих групп для ячейки таблицы."""
    return ", ".join(workgroup.name for workgroup in workgroups or [])


# Описания столбцов для таблицы научных материалов
MATERIAL_COLUMNS = [
    ColumnDef("type", "Тип", 80),
    ColumnDef("outgoing_number", "Исх. номер", 100),
    ColumnDef("outgoing_date", "Дата исх.", 100),
    ColumnDef("name", "Наименование", 250),
    ColumnDef("evaluation_display", "Оценка", 90),
    ColumnDef("incoming_number", "Вх. номер", 100),
    ColumnDef("incoming_date", "Дата вх.", 100),
    ColumnDef("participating_employees", "Сотрудники", 220, formatter=_format_employees),
    ColumnDef("participating_departments", "Отделы", 180, formatter=_format_departments),
    ColumnDef("participating_workgroups", "Рабочие группы", 200, formatter=_format_workgroups),
    ColumnDef("branch.short_name", "Филиал", 100),
    ColumnDef("consumer.short_name", "Потребитель", 120),
]

# Описания столбцов для таблицы телеграмм
TELEGRAM_COLUMNS = [
    ColumnDef("type", "Тип", 80),
    ColumnDef("outgoing_number", "Исх. номер", 100),
    ColumnDef("outgoing_date", "Дата исх.", 100),
    ColumnDef("name", "Наименование", 300),
    ColumnDef("evaluation_display", "Оценка", 90),
    ColumnDef("incoming_number", "Вх. номер", 100),
    ColumnDef("incoming_date", "Дата вх.", 100),
    ColumnDef("participating_employees", "Сотрудники", 220, formatter=_format_employees),
    ColumnDef("participating_departments", "Отделы", 180, formatter=_format_departments),
    ColumnDef("participating_workgroups", "Рабочие группы", 200, formatter=_format_workgroups),
    ColumnDef("report_type", "Тип доклада", 100),
    ColumnDef("branch.short_name", "Филиал", 100),
]

# Описания столбцов справочников
TERRITORIAL_UNIT_COLUMNS = [
    ColumnDef("id", "Сокращение", 120),
    ColumnDef("name", "Наименование", 300),
]

BRANCH_COLUMNS = [
    ColumnDef("id", "Индекс", 100),
    ColumnDef("name", "Наименование", 250),
    ColumnDef("short_name", "Сокращение", 100),
    ColumnDef("territorial_unit.name", "Территориальная единица", 150),
]

COUNTRY_COLUMNS = [
    ColumnDef("id", "Сокращение", 80),
    ColumnDef("name", "Наименование", 300),
]

ACADEMIC_TITLE_COLUMNS = [
    ColumnDef("id", "Сокращение", 80),
    ColumnDef("name", "Наименование", 200),
    ColumnDef("genitive", "Род. падеж", 200),
    ColumnDef("dative", "Дат. падеж", 200),
    ColumnDef("sort_order", "Порядок", 80),
]

SCIENTIFIC_TASK_COLUMNS = [
    ColumnDef("id", "Код", 100),
    ColumnDef("name", "Наименование", 300),
    ColumnDef("type", "Тип", 80),
    ColumnDef("start_date", "Начало", 100),
    ColumnDef("end_date", "Окончание", 100),
]

CONSUMER_COLUMNS = [
    ColumnDef("id", "Индекс", 100),
    ColumnDef("short_name", "Сокращение", 150),
    ColumnDef("name", "Наименование", 300),
]

LEADER_COLUMNS = [
    ColumnDef("id", "Сокращение", 150),
    ColumnDef("active", "Действительный", 100),
]

SOURCE_COLUMNS = [
    ColumnDef("id", "Индекс", 100),
    ColumnDef("type", "Тип", 100),
    ColumnDef("comment", "Комментарий", 300),
]


def _ensure_storage_dirs(storage_root: Path) -> None:
    """Создаёт поддиректории файлового хранилища."""
    (storage_root / FILES_DIR).mkdir(parents=True, exist_ok=True)
    (storage_root / TEMPLATES_DIR).mkdir(parents=True, exist_ok=True)
    (storage_root / EXPORT_DIR).mkdir(parents=True, exist_ok=True)


def _ensure_app_dirs(app_dir: Path) -> None:
    """Создаёт служебные директории приложения."""
    (app_dir / LOGS_DIR).mkdir(parents=True, exist_ok=True)
    (app_dir / BACKUPS_DIR).mkdir(parents=True, exist_ok=True)


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self, settings: AppSettings, db_manager: DatabaseManager) -> None:
        super().__init__()
        self.settings = settings
        self.db_manager = db_manager
        self.setWindowTitle(STRINGS.app_title)
        self.setMinimumSize(1024, 768)
        self._setup_ui()
        self._setup_menu()

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
            MATERIAL_COLUMNS,
            self.settings.branch_id,
        )
        self.telegram_tab = DocumentListWidget(
            self.db_manager.get_session(),
            self.settings.storage_path_obj(),
            Telegram,
            TELEGRAM_COLUMNS,
            self.settings.branch_id,
        )
        self.statistics_tab = StatisticsWidget(
            self.db_manager.get_session(),
            self.settings.branch_id if self.settings.role == Role.BRANCH.value else None,
        )

        self.tabs.addTab(self.materials_tab, "Научные материалы")
        self.tabs.addTab(self.telegram_tab, "Телеграммы")
        self.tabs.addTab(self.statistics_tab, "Статистика")
        layout.addWidget(self.tabs)
        self.setCentralWidget(container)

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

        export_action = QAction("Экспорт...", self)
        export_action.triggered.connect(self._export)
        file_menu.addAction(export_action)

        import_action = QAction("Импорт...", self)
        import_action.triggered.connect(self._import)
        file_menu.addAction(import_action)

        file_menu.addSeparator()
        exit_action = QAction(STRINGS.menu_exit, self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Меню "Данные" — справочники
        data_menu = menubar.addMenu(STRINGS.menu_data)
        self._add_reference_action(
            data_menu, "Территориальные единицы",
            TerritorialUnit, TerritorialUnitService, TERRITORIAL_UNIT_COLUMNS,
            TerritorialUnitDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu, "Филиалы",
            Branch, BranchService, BRANCH_COLUMNS,
            BranchDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu, "Страны",
            Country, CountryService, COUNTRY_COLUMNS,
            CountryDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu, "Научные звания",
            AcademicTitle, AcademicTitleService, ACADEMIC_TITLE_COLUMNS,
            AcademicTitleDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu, "Научные задачи",
            ScientificTask, ScientificTaskService, SCIENTIFIC_TASK_COLUMNS,
            ScientificTaskDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu, "Потребители",
            Consumer, ConsumerService, CONSUMER_COLUMNS,
            ConsumerDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu, "Руководители",
            Leader, LeaderService, LEADER_COLUMNS,
            LeaderDialog, is_head_office,
        )
        self._add_reference_action(
            data_menu, "Источники",
            Source, SourceService, SOURCE_COLUMNS,
            SourceDialog, is_head_office,
        )
        data_menu.addSeparator()
        import_primary_action = QAction("Загрузка первичных данных...", self)
        import_primary_action.triggered.connect(self._import_primary_data)
        data_menu.addAction(import_primary_action)
        import_actual_action = QAction("Загрузка актуальных данных...", self)
        import_actual_action.triggered.connect(self._import_actual_data)
        data_menu.addAction(import_actual_action)

        # Меню "ОШС"
        oshm_action = QAction("ОШС", self)
        oshm_action.triggered.connect(self._open_oshm)
        data_menu.addAction(oshm_action)

    def _add_reference_action(
        self,
        menu: QMenu,
        title: str,
        model_class,
        service_class,
        columns,
        dialog_factory,
        editable: bool,
    ) -> None:
        """Добавляет пункт меню для редактора справочника."""
        action = QAction(title, self)
        action.triggered.connect(
            lambda: ReferenceEditorDialog(
                title,
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
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec_() == SettingsDialog.Accepted:
            settings_manager = SettingsManager()
            settings_manager.save(self.settings)
            QMessageBox.information(
                self,
                STRINGS.dialog_settings_title,
                STRINGS.msg_settings_saved,
            )

    def _export(self) -> None:
        """Формирует экспортный ZIP-архив."""
        session = self.db_manager.get_session()
        try:
            service = ExportService(session, self.settings.storage_path_obj())
            output = service.export()
            session.commit()
            self.materials_tab._refresh()
            self.telegram_tab._refresh()
            QMessageBox.information(self, "Экспорт", f"Экспорт завершён:\n{output}")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка экспорта")
            session.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось выполнить экспорт:\n{exc}")
        finally:
            session.close()

    def _import(self) -> None:
        """Импортирует ZIP-архив."""
        path, _ = QFileDialog.getOpenFileName(self, "Выберите экспортный файл", "", "ZIP (*.zip)")
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
            QMessageBox.information(
                self,
                "Импорт",
                f"Импортировано: {result['imported']}\n"
                f"Удалено: {result['deleted']}\n"
                f"Пропущено: {result['skipped']}\n"
                f"Конфликтов: {len(result['conflicts'])}",
            )
            self.materials_tab._refresh()
            self.telegram_tab._refresh()
            self.statistics_tab.refresh()
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка импорта")
            session.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось выполнить импорт:\n{exc}")
        finally:
            session.close()

    def _import_primary_data(self) -> None:
        """Импортирует первичные справочные данные из XLSX."""
        path, _ = QFileDialog.getOpenFileName(self, "Файл первичных данных", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            results = import_primary_data(self.db_manager.get_session(), Path(path))
            self.db_manager.get_session().commit()
            QMessageBox.information(self, "Импорт", f"Импорт завершён:\n{self._format_import_results(results)}")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка импорта первичных данных")
            QMessageBox.critical(self, "Ошибка", str(exc))
            self.db_manager.get_session().rollback()

    def _import_actual_data(self) -> None:
        """Импортирует актуальные справочные данные из XLSX."""
        path, _ = QFileDialog.getOpenFileName(self, "Файл актуальных данных", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            results = import_actual_data(self.db_manager.get_session(), Path(path))
            self.db_manager.get_session().commit()
            QMessageBox.information(self, "Импорт", f"Импорт завершён:\n{self._format_import_results(results)}")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Ошибка импорта актуальных данных")
            QMessageBox.critical(self, "Ошибка", str(exc))
            self.db_manager.get_session().rollback()

    def _format_import_results(self, results: dict) -> str:
        """Форматирует результаты импорта для сообщения."""
        return "\n".join(f"{sheet}: {count}" for sheet, count in results.items())

    def _open_oshm(self) -> None:
        """Открывает диалог ОШС."""
        branch_id = self.settings.branch_id
        if not branch_id:
            if self.settings.role == Role.HEAD_OFFICE.value:
                # В головном офисе можно выбрать филиал для просмотра
                branch, ok = self._select_branch()
                if not ok or not branch:
                    return
                branch_id = branch
            else:
                QMessageBox.warning(self, "ОШС", "Не выбран филиал в настройках.")
                return
        is_head_office = self.settings.role == Role.HEAD_OFFICE.value
        dialog = OSHMDialog(
            self.db_manager.get_session(),
            branch_id,
            read_only=is_head_office,
            parent=self,
        )
        dialog.exec_()

    def _select_branch(self) -> tuple:
        """Показывает простой выбор филиала для головного офиса."""
        from PyQt5.QtWidgets import QInputDialog
        branches = self.db_manager.get_session().query(Branch).order_by(Branch.name).all()
        items = [f"{b.id} — {b.name}" for b in branches]
        text, ok = QInputDialog.getItem(self, "Выбор филиала", "Филиал:", items, 0, False)
        if ok and text:
            return text.split(" — ")[0], True
        return None, ok


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

    register_change_tracking()

    db_manager = DatabaseManager(settings.db_url, app_dir)
    try:
        db_manager.create_tables()
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Ошибка инициализации БД")
        QMessageBox.critical(None, "Ошибка", STRINGS.msg_db_error.format(error=exc))
        return 1

    window = MainWindow(settings, db_manager)
    window.show()

    return app.exec_()
