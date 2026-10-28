"""Диалог настроек приложения."""

from pathlib import Path

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from internal_correspondence.core.constants import Role
from internal_correspondence.core.settings import AppSettings
from internal_correspondence.utils.string_resources import STRINGS


class SettingsDialog(QDialog):
    """Диалог изменения настроек приложения."""

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(STRINGS.dialog_settings_title)
        self.setMinimumWidth(500)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # База данных
        self.db_group = QGroupBox("База данных")
        db_layout = QGridLayout(self.db_group)
        self.sqlite_radio = QRadioButton("SQLite")
        self.postgresql_radio = QRadioButton("PostgreSQL")
        db_layout.addWidget(self.sqlite_radio, 0, 0)
        db_layout.addWidget(self.postgresql_radio, 0, 1)

        self.sqlite_path = QLineEdit()
        self.sqlite_browse = QPushButton("Обзор...")
        self.sqlite_browse.clicked.connect(self._browse_sqlite)
        db_layout.addWidget(QLabel("Файл:"), 1, 0)
        db_layout.addWidget(self.sqlite_path, 1, 1)
        db_layout.addWidget(self.sqlite_browse, 1, 2)

        self.pg_host = QLineEdit()
        self.pg_port = QLineEdit("5432")
        self.pg_database = QLineEdit()
        self.pg_user = QLineEdit()
        self.pg_password = QLineEdit()
        self.pg_password.setEchoMode(QLineEdit.Password)
        db_layout.addWidget(QLabel("Хост:"), 2, 0)
        db_layout.addWidget(self.pg_host, 2, 1)
        db_layout.addWidget(QLabel("Порт:"), 3, 0)
        db_layout.addWidget(self.pg_port, 3, 1)
        db_layout.addWidget(QLabel("БД:"), 4, 0)
        db_layout.addWidget(self.pg_database, 4, 1)
        db_layout.addWidget(QLabel("Пользователь:"), 5, 0)
        db_layout.addWidget(self.pg_user, 5, 1)
        db_layout.addWidget(QLabel("Пароль:"), 6, 0)
        db_layout.addWidget(self.pg_password, 6, 1)

        self.sqlite_radio.toggled.connect(self._on_db_type_changed)
        self.postgresql_radio.toggled.connect(self._on_db_type_changed)
        layout.addWidget(self.db_group)

        # Хранилище
        self.storage_path = QLineEdit()
        self.storage_browse = QPushButton("Обзор...")
        self.storage_browse.clicked.connect(self._browse_storage)
        storage_layout = QGridLayout()
        storage_layout.addWidget(QLabel("Путь к хранилищу:"), 0, 0)
        storage_layout.addWidget(self.storage_path, 0, 1)
        storage_layout.addWidget(self.storage_browse, 0, 2)
        layout.addLayout(storage_layout)

        # Роль
        self.role_combo = QComboBox()
        self.role_combo.addItem(STRINGS.role_head_office, Role.HEAD_OFFICE.value)
        self.role_combo.addItem(STRINGS.role_branch, Role.BRANCH.value)
        self.branch_id = QLineEdit()
        form.addRow("Роль:", self.role_combo)
        form.addRow("Филиал:", self.branch_id)
        layout.addLayout(form)

        # Кнопки
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self._on_save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _on_db_type_changed(self) -> None:
        is_sqlite = self.sqlite_radio.isChecked()
        self.sqlite_path.setEnabled(is_sqlite)
        self.sqlite_browse.setEnabled(is_sqlite)
        self.pg_host.setEnabled(not is_sqlite)
        self.pg_port.setEnabled(not is_sqlite)
        self.pg_database.setEnabled(not is_sqlite)
        self.pg_user.setEnabled(not is_sqlite)
        self.pg_password.setEnabled(not is_sqlite)

    def _browse_sqlite(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Файл базы данных SQLite",
            "",
            "SQLite (*.db *.sqlite *.sqlite3)",
        )
        if path:
            self.sqlite_path.setText(path)

    def _browse_storage(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Директория хранилища")
        if path:
            self.storage_path.setText(path)

    def _load_settings(self) -> None:
        url = self.settings.db_url
        if url.startswith("sqlite"):
            self.sqlite_radio.setChecked(True)
            prefix = "sqlite:///"
            self.sqlite_path.setText(url[len(prefix):] if url.startswith(prefix) else "")
        elif url.startswith("postgresql"):
            self.postgresql_radio.setChecked(True)
            # Упрощённый парсинг URL
            rest = url.replace("postgresql://", "")
            auth, _, host_db = rest.partition("@")
            user, _, password = auth.partition(":")
            host_port, _, database = host_db.partition("/")
            host, _, port = host_port.partition(":")
            self.pg_host.setText(host)
            self.pg_port.setText(port or "5432")
            self.pg_database.setText(database)
            self.pg_user.setText(user)
            self.pg_password.setText(password)

        self.storage_path.setText(self.settings.storage_path)
        index = self.role_combo.findData(self.settings.role)
        if index >= 0:
            self.role_combo.setCurrentIndex(index)
        self.branch_id.setText(self.settings.branch_id)
        self._on_db_type_changed()

    def _on_save(self) -> None:
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
            self.settings.db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

        self.settings.storage_path = self.storage_path.text().strip()
        self.settings.role = self.role_combo.currentData()
        self.settings.branch_id = self.branch_id.text().strip()
        self.accept()
