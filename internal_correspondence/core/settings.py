"""Управление настройками приложения через INI-файл."""

import configparser
import os
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional

from internal_correspondence.core.constants import CONFIG_FILE_NAME, Role


@dataclass
class AppSettings:
    """Настройки приложения, сохраняемые в INI-файле."""

    # База данных
    db_url: str = "sqlite:///internal_correspondence.db"

    # Файловое хранилище
    storage_path: str = ""

    # Роль
    role: str = Role.BRANCH.value

    # Идентификатор филиала (для роли branch)
    branch_id: str = ""

    # Язык интерфейса
    language: str = "ru"

    # Тема оформления (light/dark)
    theme: str = "light"

    # Путь к внешнему пакету предметной области (пусто — встроенный)
    domain_pack: str = ""

    def storage_path_obj(self) -> Path:
        """Возвращает путь к файловому хранилищу."""
        if self.storage_path:
            return Path(self.storage_path)
        return Path(self.default_storage_root())

    @staticmethod
    def default_storage_root() -> str:
        """Возвращает корневую директорию хранилища по умолчанию."""
        if os.name == "nt":
            return os.path.dirname(os.path.abspath(sys.argv[0]))
        return os.path.expanduser("~")


class SettingsManager:
    """Чтение и запись настроек приложения."""

    def __init__(self, app_dir: Optional[Path] = None) -> None:
        self.app_dir = app_dir or Path(os.path.dirname(os.path.abspath(__file__))).parent.parent
        self.config_path = self.app_dir / CONFIG_FILE_NAME
        # strict=False: ручная правка INI с продублированными ключами
        # не должна ронять запуск приложения (побеждает последнее значение)
        self._config = configparser.ConfigParser(strict=False)

    @property
    def exists(self) -> bool:
        """Проверяет существование INI-файла настроек."""
        return self.config_path.exists()

    def load(self) -> AppSettings:
        """Загружает настройки из INI-файла."""
        settings = AppSettings()
        if not self.exists:
            return settings

        self._config.read(self.config_path, encoding="utf-8")
        section = "Application"
        if not self._config.has_section(section):
            return settings

        for fld in fields(settings):
            if self._config.has_option(section, fld.name):
                value = self._config.get(section, fld.name)
                # pylint: disable=protected-access
                setattr(settings, fld.name, value)
        return settings

    def save(self, settings: AppSettings) -> None:
        """Сохраняет настройки в INI-файл."""
        self._config.clear()
        section = "Application"
        self._config.add_section(section)
        for fld in fields(settings):
            value = getattr(settings, fld.name)
            self._config.set(section, fld.name, str(value))

        with open(self.config_path, "w", encoding="utf-8") as f:
            self._config.write(f)

