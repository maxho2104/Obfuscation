"""Мастер первого запуска приложения."""

from html import escape
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from internal_correspondence.core.constants import Role
from internal_correspondence.core.logging_config import get_logger
from internal_correspondence.core.settings import AppSettings
from internal_correspondence.gui.custom_title_bar import (
    TITLE_BAR_CONTENT_GAP_PROPERTY,
    WIZARD_CUSTOM_TITLE_BAR_PROPERTY,
)
from internal_correspondence.importexport.branch_import import (
    InitialBranchImport,
    read_archive_branches,
)
from internal_correspondence.orm.models import Branch
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("first_run_wizard")
FIRST_RUN_TITLE_BAR_CONTENT_GAP = 16
FIRST_RUN_PAGE_TITLE_SPACER = "<br><br><br>"


def load_branches(db_url: str) -> List[Tuple[str, str]]:
    """Возвращает список доступных филиалов (идентификатор, наименование) из БД.

    Если база данных недоступна или ещё не инициализирована, возвращается
    пустой список.
    """
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", "", 1))
        if not db_path.is_file():
            return []

    connect_args = {"connect_timeout": 3} if db_url.startswith("postgresql") else {}
    try:
        engine = create_engine(db_url, future=True, connect_args=connect_args)
        try:
            with Session(engine) as session:
                rows = session.query(Branch.id, Branch.name).order_by(Branch.id).all()
        finally:
            engine.dispose()
    except Exception:  # pylint: disable=broad-except
        logger.warning("Не удалось получить список филиалов из БД %s", db_url, exc_info=True)
        return []

    return [(row[0], row[1]) for row in rows]


class DatabasePage(QWizardPage):
    """Страница выбора типа и параметров подключения к БД."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.setTitle(STRINGS.wizard_db_title)
        self.setSubTitle(STRINGS.wizard_db_subtitle)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.sqlite_radio = QRadioButton(STRINGS.wizard_sqlite_local)
        self.sqlite_radio.setChecked(True)
        self.postgresql_radio = QRadioButton(STRINGS.wizard_postgresql_server)

        layout.addWidget(self.sqlite_radio)
        layout.addWidget(self.postgresql_radio)

        # SQLite group
        self.sqlite_group = QGroupBox(STRINGS.wizard_sqlite_params)
        sqlite_layout = QGridLayout(self.sqlite_group)
        sqlite_layout.addWidget(QLabel(STRINGS.label_db_file), 0, 0)
        self.sqlite_path = QLineEdit()
        self.sqlite_path.setPlaceholderText("internal_correspondence.db")
        sqlite_layout.addWidget(self.sqlite_path, 0, 1)
        self.sqlite_browse = QPushButton(STRINGS.button_browse)
        self.sqlite_browse.clicked.connect(self._browse_sqlite)
        sqlite_layout.addWidget(self.sqlite_browse, 0, 2)
        layout.addWidget(self.sqlite_group)

        # PostgreSQL group
        self.postgresql_group = QGroupBox(STRINGS.wizard_postgresql_params)
        pg_layout = QGridLayout(self.postgresql_group)
        pg_layout.addWidget(QLabel(STRINGS.label_host), 0, 0)
        self.pg_host = QLineEdit("localhost")
        pg_layout.addWidget(self.pg_host, 0, 1)
        pg_layout.addWidget(QLabel(STRINGS.label_port), 1, 0)
        self.pg_port = QLineEdit("5432")
        pg_layout.addWidget(self.pg_port, 1, 1)
        pg_layout.addWidget(QLabel(STRINGS.label_database), 2, 0)
        self.pg_database = QLineEdit()
        pg_layout.addWidget(self.pg_database, 2, 1)
        pg_layout.addWidget(QLabel(STRINGS.label_user), 3, 0)
        self.pg_user = QLineEdit()
        pg_layout.addWidget(self.pg_user, 3, 1)
        pg_layout.addWidget(QLabel(STRINGS.label_password), 4, 0)
        self.pg_password = QLineEdit()
        self.pg_password.setEchoMode(QLineEdit.Password)
        pg_layout.addWidget(self.pg_password, 4, 1)
        layout.addWidget(self.postgresql_group)
        self.postgresql_group.setEnabled(False)

        self.sqlite_radio.toggled.connect(self._on_db_type_changed)
        self.postgresql_radio.toggled.connect(self._on_db_type_changed)

        self.registerField("sqlite_path", self.sqlite_path)
        self.registerField("pg_host", self.pg_host)
        self.registerField("pg_database", self.pg_database)
        self.registerField("pg_user", self.pg_user)

    def _on_db_type_changed(self) -> None:
        is_sqlite = self.sqlite_radio.isChecked()
        self.sqlite_group.setEnabled(is_sqlite)
        self.postgresql_group.setEnabled(not is_sqlite)

    def _browse_sqlite(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            STRINGS.wizard_select_sqlite_file,
            self.sqlite_path.text().strip(),
            "SQLite (*.db *.sqlite *.sqlite3)",
            options=QFileDialog.DontConfirmOverwrite,
        )
        if not path:
            return

        if Path(path).exists():
            reply = QMessageBox.question(
                self,
                STRINGS.dialog_db_file,
                STRINGS.msg_db_file_exists.format(path=path),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return

        self.sqlite_path.setText(path)

    def validatePage(self) -> bool:
        if self.sqlite_radio.isChecked():
            path = self.sqlite_path.text().strip()
            if not path:
                path = "internal_correspondence.db"
            self.settings.db_url = f"sqlite:///{Path(path).as_posix()}"
        else:
            host = self.pg_host.text().strip()
            port = self.pg_port.text().strip() or "5432"
            database = self.pg_database.text().strip()
            user = self.pg_user.text().strip()
            password = self.pg_password.text()
            if not all([host, database, user]):
                return False
            self.settings.db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        return True


class StoragePage(QWizardPage):
    """Страница выбора расположения файлового хранилища."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.setTitle(STRINGS.wizard_storage_title)
        self.setSubTitle(STRINGS.wizard_storage_subtitle)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QGridLayout(self)
        layout.addWidget(QLabel(STRINGS.label_storage_path), 0, 0)
        self.path_edit = QLineEdit()
        layout.addWidget(self.path_edit, 0, 1)
        self.browse_btn = QPushButton(STRINGS.button_browse)
        self.browse_btn.clicked.connect(self._browse)
        layout.addWidget(self.browse_btn, 0, 2)
        self.registerField("storage_path", self.path_edit)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, STRINGS.wizard_select_storage)
        if path:
            self.path_edit.setText(path)

    def validatePage(self) -> bool:
        self.settings.storage_path = self.path_edit.text().strip()
        return True


class RolePage(QWizardPage):
    """Страница выбора роли и филиала."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.setTitle(STRINGS.wizard_role_title)
        self.setSubTitle(STRINGS.wizard_role_subtitle)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.head_office_radio = QRadioButton(STRINGS.role_head_office)
        self.branch_radio = QRadioButton(STRINGS.role_branch)
        self.branch_radio.setChecked(True)

        layout.addWidget(self.head_office_radio)
        layout.addWidget(self.branch_radio)

        self.branch_combo = QComboBox()
        self.branch_combo.setEditable(True)
        self.branch_combo.setPlaceholderText(STRINGS.wizard_branch_placeholder)
        layout.addWidget(QLabel(STRINGS.label_branch_for_role))
        layout.addWidget(self.branch_combo)

        # Первоначальная загрузка из архива головного офиса: доступна
        # только филиалу и только при пустой базе (set_archive_allowed).
        self.archive_group = QGroupBox(STRINGS.wizard_archive_group)
        archive_layout = QVBoxLayout(self.archive_group)
        archive_hint = QLabel(STRINGS.wizard_archive_hint)
        archive_hint.setWordWrap(True)
        archive_layout.addWidget(archive_hint)
        archive_row = QHBoxLayout()
        self.archive_button = QPushButton(STRINGS.wizard_archive_browse)
        self.archive_button.clicked.connect(self._browse_archive)
        archive_row.addWidget(self.archive_button)
        self.archive_label = QLabel(STRINGS.wizard_archive_not_selected)
        self.archive_label.setWordWrap(True)
        archive_row.addWidget(self.archive_label, 1)
        archive_layout.addLayout(archive_row)
        layout.addWidget(self.archive_group)
        self.archive_group.setVisible(False)
        self._archive_allowed = False
        self._archive_path: Optional[Path] = None

        self.head_office_radio.toggled.connect(self._on_role_changed)
        self.branch_radio.toggled.connect(self._on_role_changed)

        self.registerField("role_head_office", self.head_office_radio)
        self.registerField("role_branch", self.branch_radio)

    def _on_role_changed(self) -> None:
        is_branch = self.branch_radio.isChecked()
        self.branch_combo.setEnabled(is_branch)
        self.archive_group.setVisible(is_branch and self._archive_allowed)

    def set_archive_allowed(self, allowed: bool) -> None:
        """Включает выбор архива головного офиса (пустая база филиала)."""
        self._archive_allowed = allowed
        if not allowed:
            self._reset_archive()
        self.archive_group.setVisible(
            allowed and self.branch_radio.isChecked()
        )

    def _browse_archive(self) -> None:
        """Читает филиалы из выбранного экспортного архива в список."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            STRINGS.wizard_archive_browse,
            "",
            STRINGS.wizard_archive_filter,
        )
        if not path:
            return
        try:
            branches = read_archive_branches(Path(path))
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.warning(
                self,
                STRINGS.title_attention,
                STRINGS.wizard_archive_error.format(error=exc),
            )
            return
        if not branches:
            QMessageBox.warning(
                self, STRINGS.title_attention, STRINGS.wizard_archive_no_branches
            )
            return
        self._archive_path = Path(path)
        self.archive_label.setText(Path(path).name)
        self.branch_combo.setEditable(False)
        self.set_branches(branches)

    def _reset_archive(self) -> None:
        """Сбрасывает выбор архива и возвращает ручной ввод филиала."""
        self._archive_path = None
        self.archive_label.setText(STRINGS.wizard_archive_not_selected)
        self.branch_combo.setEditable(True)

    @property
    def archive_path(self) -> Optional[Path]:
        """Путь выбранного экспортного архива головного офиса."""
        return self._archive_path

    def set_branches(self, branches: List[Tuple[str, str]]) -> None:
        """Заполняет список доступных филиалов парами (идентификатор, наименование)."""
        selected = self.branch_combo.currentData()
        self.branch_combo.clear()
        for branch_id, name in branches:
            self.branch_combo.addItem(f"{branch_id} — {name}", branch_id)
        if selected is not None:
            index = self.branch_combo.findData(selected)
            if index >= 0:
                self.branch_combo.setCurrentIndex(index)
        if self.branch_combo.currentIndex() < 0 and self.branch_combo.count():
            self.branch_combo.setCurrentIndex(0)

    def validatePage(self) -> bool:
        if self.head_office_radio.isChecked():
            self.settings.role = Role.HEAD_OFFICE.value
            self.settings.branch_id = ""
        else:
            self.settings.role = Role.BRANCH.value
            branch_id = self.branch_combo.currentData()
            self.settings.branch_id = str(branch_id or self.branch_combo.currentText()).strip()
            if not self.settings.branch_id:
                return False
        return True


class FirstRunWizard(QWizard):
    """Мастер первого запуска для настройки приложения."""

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setProperty(WIZARD_CUSTOM_TITLE_BAR_PROPERTY, True)
        self.setProperty(
            TITLE_BAR_CONTENT_GAP_PROPERTY,
            FIRST_RUN_TITLE_BAR_CONTENT_GAP,
        )
        self.setWindowTitle(STRINGS.wizard_first_run_title)
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.HaveHelpButton, False)
        self.setOption(QWizard.HaveFinishButtonOnEarlyPages, False)

        self.db_page = DatabasePage(settings)
        self.storage_page = StoragePage(settings)
        self.role_page = RolePage(settings)
        self.setTitleFormat(Qt.RichText)
        for page in (self.db_page, self.storage_page, self.role_page):
            page.setTitle(
                FIRST_RUN_PAGE_TITLE_SPACER + escape(page.title())
            )

        self.addPage(self.db_page)
        self.addPage(self.storage_page)
        self._role_page_id = self.addPage(self.role_page)
        self.currentIdChanged.connect(self._on_page_changed)

    def _on_page_changed(self, page_id: int) -> None:
        """Обновляет список филиалов при переходе на страницу выбора роли."""
        if page_id == self._role_page_id:
            branches = load_branches(self.settings.db_url)
            self.role_page.set_branches(branches)
            self.role_page.set_archive_allowed(not branches)

    def initial_import(self) -> Optional[InitialBranchImport]:
        """Возвращает план первоначальной загрузки из архива ГО (если выбран)."""
        if self.settings.role != Role.BRANCH.value:
            return None
        archive_path = self.role_page.archive_path
        branch_id = self.role_page.branch_combo.currentData()
        if archive_path is None or branch_id is None:
            return None
        return InitialBranchImport(archive_path=archive_path, branch_id=str(branch_id))

    def set_available_branches(self, branch_ids: List[str]) -> None:
        """Устанавливает список филиалов для выбора по их идентификаторам."""
        self.role_page.set_branches([(branch_id, branch_id) for branch_id in branch_ids])


def run_first_run_wizard(
    parent=None,
    branch_ids: Optional[List[str]] = None,
) -> Tuple[Optional[AppSettings], Optional[InitialBranchImport]]:
    """Запускает мастер первого запуска.

    Returns:
        Пара (настройки, план первоначальной загрузки). Настройки — None,
        если пользователь отказался от настройки.
    """
    settings = AppSettings()
    wizard = FirstRunWizard(settings, parent)
    if branch_ids:
        wizard.set_available_branches(branch_ids)
    if wizard.exec_() == QWizard.Accepted:
        return settings, wizard.initial_import()
    return None, None
