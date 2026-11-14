"""Диалог настроек приложения."""

from pathlib import Path
from typing import List, Optional, Tuple

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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from internal_correspondence.core.constants import (
    DEFAULT_CHANGES_RETENTION_DAYS,
    Role,
)
from internal_correspondence.core.database import DatabaseManager
from internal_correspondence.core.settings import AppSettings
from internal_correspondence.gui.first_run_wizard import load_branches
from internal_correspondence.orm.models import Branch
from internal_correspondence.utils.string_resources import STRINGS


class SettingsDialog(QDialog):
    """Диалог изменения настроек приложения.

    Поля подключения PostgreSQL («Хост», «Порт», «БД», «Пользователь»,
    «Пароль») скрываются при выборе SQLite и показываются при выборе
    PostgreSQL; поле «Файл» SQLite — наоборот. Поле «Филиал» отображается
    только для роли «Филиал» и заполняется наименованиями филиалов из
    таблицы «Филиалы».
    """

    def __init__(
        self,
        settings: AppSettings,
        db_manager: Optional[DatabaseManager] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self._db_manager = db_manager
        self.setWindowTitle(STRINGS.dialog_settings_title)
        self.setMinimumWidth(500)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # База данных
        self.db_group = QGroupBox(STRINGS.settings_db_group)
        db_layout = QGridLayout(self.db_group)
        self.sqlite_radio = QRadioButton("SQLite")
        self.postgresql_radio = QRadioButton("PostgreSQL")
        db_layout.addWidget(self.sqlite_radio, 0, 0)
        db_layout.addWidget(self.postgresql_radio, 0, 1)

        self.sqlite_path = QLineEdit()
        self.sqlite_browse = QPushButton(STRINGS.button_browse)
        self.sqlite_browse.clicked.connect(self._browse_sqlite)
        self._sqlite_rows: List[Tuple[QWidget, ...]] = [
            (QLabel(STRINGS.label_db_file), self.sqlite_path, self.sqlite_browse)
        ]
        db_layout.addWidget(self._sqlite_rows[0][0], 1, 0)
        db_layout.addWidget(self.sqlite_path, 1, 1)
        db_layout.addWidget(self.sqlite_browse, 1, 2)

        self.pg_host = QLineEdit()
        self.pg_port = QLineEdit("5432")
        self.pg_database = QLineEdit()
        self.pg_user = QLineEdit()
        self.pg_password = QLineEdit()
        self.pg_password.setEchoMode(QLineEdit.Password)
        self._pg_rows: List[Tuple[QWidget, ...]] = [
            (QLabel(STRINGS.label_host), self.pg_host),
            (QLabel(STRINGS.label_port), self.pg_port),
            (QLabel(STRINGS.label_database), self.pg_database),
            (QLabel(STRINGS.label_user), self.pg_user),
            (QLabel(STRINGS.label_password), self.pg_password),
        ]
        for row_index, (label, editor) in enumerate(self._pg_rows, start=2):
            db_layout.addWidget(label, row_index, 0)
            db_layout.addWidget(editor, row_index, 1)

        self.sqlite_radio.toggled.connect(self._on_db_type_changed)
        self.postgresql_radio.toggled.connect(self._on_db_type_changed)
        layout.addWidget(self.db_group)

        # Хранилище
        self.storage_path = QLineEdit()
        self.storage_browse = QPushButton(STRINGS.button_browse)
        self.storage_browse.clicked.connect(self._browse_storage)
        storage_layout = QGridLayout()
        storage_layout.addWidget(QLabel(STRINGS.settings_storage_label), 0, 0)
        storage_layout.addWidget(self.storage_path, 0, 1)
        storage_layout.addWidget(self.storage_browse, 0, 2)
        layout.addLayout(storage_layout)

        # Роль
        self.role_combo = QComboBox()
        self.role_combo.addItem(STRINGS.role_head_office, Role.HEAD_OFFICE.value)
        self.role_combo.addItem(STRINGS.role_branch, Role.BRANCH.value)
        form.addRow(STRINGS.label_role, self.role_combo)

        # Филиал: выбор из справочника филиалов (только для роли «Филиал»)
        self.branch_label = QLabel(STRINGS.label_branch)
        self.branch_combo = QComboBox()
        form.addRow(self.branch_label, self.branch_combo)
        self._branch_rows: Tuple[QWidget, ...] = (
            self.branch_label,
            self.branch_combo,
        )
        self.role_combo.currentIndexChanged.connect(self._on_role_changed)

        # Срок хранения журнала изменений
        self.changes_retention = QSpinBox()
        self.changes_retention.setRange(0, 3650)
        self.changes_retention.setSpecialValueText(STRINGS.settings_retention_forever)
        form.addRow(STRINGS.settings_changes_retention, self.changes_retention)
        layout.addLayout(form)

        # Кнопки
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self._on_save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _on_db_type_changed(self) -> None:
        """Показывает поля выбранного типа БД и скрывает остальные."""
        is_sqlite = self.sqlite_radio.isChecked()
        for row in self._sqlite_rows:
            for widget in row:
                widget.setVisible(is_sqlite)
        for row in self._pg_rows:
            for widget in row:
                widget.setVisible(not is_sqlite)

    def _on_role_changed(self) -> None:
        """Показывает поле «Филиал» только для роли «Филиал»."""
        is_branch = self.role_combo.currentData() == Role.BRANCH.value
        for widget in self._branch_rows:
            widget.setVisible(is_branch)

    def _browse_sqlite(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            STRINGS.settings_sqlite_file_dialog,
            "",
            STRINGS.settings_sqlite_filter,
        )
        if path:
            self.sqlite_path.setText(path)

    def _browse_storage(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, STRINGS.settings_storage_dialog
        )
        if path:
            self.storage_path.setText(path)

    def _load_branches(self) -> None:
        """Заполняет комбобокс филиалов наименованиями из таблицы «Филиалы»."""
        if self._db_manager is not None:
            session = self._db_manager.get_session()
            try:
                rows = session.query(Branch.id, Branch.name).order_by(Branch.name).all()
                branches = [(row[0], row[1]) for row in rows]
            except Exception:  # pylint: disable=broad-except
                branches = []
            finally:
                session.close()
        else:
            branches = load_branches(self.settings.db_url)

        self.branch_combo.clear()
        for branch_id, name in branches:
            self.branch_combo.addItem(f"{branch_id} — {name}", branch_id)
        # Текущее значение настройки должно отображаться даже если
        # филиал отсутствует в справочнике
        current = self.settings.branch_id
        if current:
            index = self.branch_combo.findData(current)
            if index < 0:
                self.branch_combo.addItem(current, current)
                index = self.branch_combo.count() - 1
            self.branch_combo.setCurrentIndex(index)

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
        self._load_branches()
        try:
            retention = int(self.settings.changes_retention_days)
        except (TypeError, ValueError):
            retention = DEFAULT_CHANGES_RETENTION_DAYS
        self.changes_retention.setValue(max(0, retention))
        self._on_db_type_changed()
        self._on_role_changed()

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
        self.settings.branch_id = self.branch_combo.currentData() or ""
        self.settings.changes_retention_days = self.changes_retention.value()
        self.accept()
