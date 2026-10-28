"""Централизованное хранилище строковых ресурсов интерфейса.

Все пользовательские тексты (заголовки, метки, сообщения) описываются здесь
для упрощения будущей локализации.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AppStrings:
    """Строки приложения."""

    app_title: str = "Внутренняя корреспонденция"
    menu_file: str = "Файл"
    menu_settings: str = "Настройки..."
    menu_exit: str = "Выход"
    menu_data: str = "Данные"
    role_head_office: str = "Головной офис"
    role_branch: str = "Филиал"
    button_ok: str = "Ок"
    button_cancel: str = "Отмена"
    button_save: str = "Сохранить"
    button_add: str = "Добавить"
    button_edit: str = "Изменить"
    button_delete: str = "Удалить"
    dialog_settings_title: str = "Настройки"
    wizard_first_run_title: str = "Первый запуск"
    wizard_db_title: str = "Подключение к базе данных"
    wizard_db_subtitle: str = "Выберите тип базы данных и укажите параметры подключения."
    wizard_storage_title: str = "Файловое хранилище"
    wizard_storage_subtitle: str = "Выберите корневую директорию для хранения файлов, шаблонов и экспорта."
    wizard_role_title: str = "Роль приложения"
    wizard_role_subtitle: str = "Выберите, как будет использоваться приложение."
    msg_db_error: str = "Не удалось инициализировать базу данных:\n{error}"
    msg_settings_saved: str = "Настройки сохранены. Изменения в подключении к БД вступят в силу после перезапуска."


STRINGS = AppStrings()
