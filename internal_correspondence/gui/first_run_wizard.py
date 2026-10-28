"""Мастер первого запуска приложения."""

from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
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
from internal_correspondence.orm.models import Branch
from internal_correspondence.utils.string_resources import STRINGS

logger = get_logger("first_run_wizard")


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

        self.sqlite_radio = QRadioButton("SQLite (локальный файл)")
        self.sqlite_radio.setChecked(True)
        self.postgresql_radio = QRadioButton("PostgreSQL (сервер)")

        layout.addWidget(self.sqlite_radio)
        layout.addWidget(self.postgresql_radio)

        # SQLite group
        self.sqlite_group = QGroupBox("Параметры SQLite")
        sqlite_layout = QGridLayout(self.sqlite_group)
        sqlite_layout.addWidget(QLabel("Файл базы данных:"), 0, 0)
        self.sqlite_path = QLineEdit()
        self.sqlite_path.setPlaceholderText("internal_correspondence.db")
        sqlite_layout.addWidget(self.sqlite_path, 0, 1)
        self.sqlite_browse = QPushButton("Обзор...")
        self.sqlite_browse.clicked.connect(self._browse_sqlite)
        sqlite_layout.addWidget(self.sqlite_browse, 0, 2)
        layout.addWidget(self.sqlite_group)

        # PostgreSQL group
        self.postgresql_group = QGroupBox("Параметры PostgreSQL")
        pg_layout = QGridLayout(self.postgresql_group)
        pg_layout.addWidget(QLabel("Хост:"), 0, 0)
        self.pg_host = QLineEdit("localhost")
        pg_layout.addWidget(self.pg_host, 0, 1)
        pg_layout.addWidget(QLabel("Порт:"), 1, 0)
        self.pg_port = QLineEdit("5432")
        pg_layout.addWidget(self.pg_port, 1, 1)
        pg_layout.addWidget(QLabel("База данных:"), 2, 0)
        self.pg_database = QLineEdit()
        pg_layout.addWidget(self.pg_database, 2, 1)
        pg_layout.addWidget(QLabel("Пользователь:"), 3, 0)
        self.pg_user = QLineEdit()
        pg_layout.addWidget(self.pg_user, 3, 1)
        pg_layout.addWidget(QLabel("Пароль:"), 4, 0)
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
            "Выберите файл базы данных SQLite",
            self.sqlite_path.text().strip(),
            "SQLite (*.db *.sqlite *.sqlite3)",
            options=QFileDialog.DontConfirmOverwrite,
        )
        if not path:
            return

        if Path(path).exists():
            reply = QMessageBox.question(
                self,
                "Файл базы данных",
                f"Файл базы данных уже существует:\n{path}\n\nИспользовать этот файл?",
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
        layout.addWidget(QLabel("Путь к хранилищу:"), 0, 0)
        self.path_edit = QLineEdit()
        layout.addWidget(self.path_edit, 0, 1)
        self.browse_btn = QPushButton("Обзор...")
        self.browse_btn.clicked.connect(self._browse)
        layout.addWidget(self.browse_btn, 0, 2)
        self.registerField("storage_path", self.path_edit)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Выберите директорию хранилища")
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
        self.branch_combo.setPlaceholderText("Выберите или введите индекс филиала")
        layout.addWidget(QLabel("Филиал (для роли 'Филиал'):"))
        layout.addWidget(self.branch_combo)

        self.head_office_radio.toggled.connect(self._on_role_changed)
        self.branch_radio.toggled.connect(self._on_role_changed)

        self.registerField("role_head_office", self.head_office_radio)
        self.registerField("role_branch", self.branch_radio)

    def _on_role_changed(self) -> None:
        is_branch = self.branch_radio.isChecked()
        self.branch_combo.setEnabled(is_branch)

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
        self.setWindowTitle(STRINGS.wizard_first_run_title)
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.HaveHelpButton, False)
        self.setOption(QWizard.HaveFinishButtonOnEarlyPages, False)

        self.db_page = DatabasePage(settings)
        self.storage_page = StoragePage(settings)
        self.role_page = RolePage(settings)

        self.addPage(self.db_page)
        self.addPage(self.storage_page)
        self._role_page_id = self.addPage(self.role_page)
        self.currentIdChanged.connect(self._on_page_changed)

    def _on_page_changed(self, page_id: int) -> None:
        """Обновляет список филиалов при переходе на страницу выбора роли."""
        if page_id == self._role_page_id:
            self.role_page.set_branches(load_branches(self.settings.db_url))

    def set_available_branches(self, branch_ids: List[str]) -> None:
        """Устанавливает список филиалов для выбора по их идентификаторам."""
        self.role_page.set_branches([(branch_id, branch_id) for branch_id in branch_ids])


def run_first_run_wizard(
    parent=None,
    branch_ids: Optional[List[str]] = None,
) -> Optional[AppSettings]:
    """Запускает мастер первого запуска и возвращает настройки при успехе."""
    settings = AppSettings()
    wizard = FirstRunWizard(settings, parent)
    if branch_ids:
        wizard.set_available_branches(branch_ids)
    if wizard.exec_() == QWizard.Accepted:
        return settings
    return None
