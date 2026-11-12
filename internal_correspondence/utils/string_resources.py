"""Централизованное хранилище строковых ресурсов интерфейса.

Все пользовательские тексты (заголовки, метки, сообщения) описываются здесь
для упрощения будущей локализации.

Активный пакет предметной области (``core/domain_pack.py``) может
переопределять любые строки через секцию ``strings`` — переопределения
применяются вызовом :func:`reload_strings` после смены пакета.
"""

from dataclasses import dataclass, fields

from internal_correspondence.core.domain_pack import get_domain_pack
from internal_correspondence.core.logging_config import get_logger

logger = get_logger("string_resources")


@dataclass
class AppStrings:
    """Строки приложения (значения по умолчанию)."""

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
    settings_changes_retention: str = "Срок хранения журнала изменений (дней):"
    settings_retention_forever: str = "бессрочно"
    wizard_first_run_title: str = "Первый запуск"
    wizard_db_title: str = "Подключение к базе данных"
    wizard_db_subtitle: str = "Выберите тип базы данных и укажите параметры подключения."
    wizard_storage_title: str = "Файловое хранилище"
    wizard_storage_subtitle: str = "Выберите корневую директорию для хранения файлов, шаблонов и экспорта."
    wizard_role_title: str = "Роль приложения"
    wizard_role_subtitle: str = "Выберите, как будет использоваться приложение."
    msg_db_error: str = "Не удалось инициализировать базу данных:\n{error}"
    msg_settings_saved: str = "Настройки сохранены. Изменения в подключении к БД вступят в силу после перезапуска."

    # --- Главное окно: вкладки, меню, действия ---
    tab_statistics: str = "Статистика"
    menu_view: str = "Вид"
    menu_theme: str = "Оформление"
    action_export: str = "Экспорт..."
    action_import: str = "Импорт..."
    action_import_primary: str = "Загрузка первичных данных..."
    action_import_actual: str = "Загрузка актуальных данных..."
    action_oshm: str = "ОШС"
    action_domain_pack: str = "Пакет предметной области..."

    # --- Заголовки диалогов ---
    title_error: str = "Ошибка"
    title_export: str = "Экспорт"
    title_import: str = "Импорт"
    title_oshm: str = "ОШС"
    title_confirm: str = "Подтверждение"
    title_attention: str = "Внимание"
    title_domain_pack: str = "Пакет предметной области"

    # --- Экспорт/импорт ---
    msg_export_done: str = "Экспорт завершён:\n{output}"
    msg_export_error: str = "Не удалось выполнить экспорт:\n{error}"
    msg_import_error: str = "Не удалось выполнить импорт:\n{error}"
    msg_import_result: str = (
        "Импортировано: {imported}\nУдалено: {deleted}\n"
        "Пропущено: {skipped}\nКонфликтов: {conflicts}"
    )
    msg_import_warnings: str = "Предупреждения:"
    msg_import_done: str = "Импорт завершён:\n{results}"
    dialog_select_export_file: str = "Выберите экспортный файл"
    dialog_primary_data_file: str = "Файл первичных данных"
    dialog_actual_data_file: str = "Файл актуальных данных"

    # --- Пакет предметной области ---
    dialog_domain_pack_save: str = "Выгрузить пакет предметной области"
    msg_pack_save_error: str = "Не удалось сохранить файл:\n{error}"
    msg_pack_saved_use: str = (
        "Пакет сохранён:\n{path}\n\nИспользовать этот файл как активный пакет?\n"
        "(изменение вступит в силу после перезапуска приложения)"
    )
    msg_pack_load_error: str = (
        "Не удалось загрузить пакет '{path}':\n{error}\n\n"
        "Будет использован встроенный пакет по умолчанию."
    )
    msg_unknown_codes_in_db: str = (
        "В базе данных есть значения, отсутствующие в активном пакете:\n\n"
    )

    # --- ОШС ---
    msg_no_branch_selected: str = "Не выбран филиал в настройках."
    dialog_select_branch: str = "Выбор филиала"
    label_branch: str = "Филиал:"
    oshm_window_title: str = "ОШС филиала {branch_id}"
    oshm_col_element: str = "Элемент"
    oshm_col_status: str = "Статус"
    status_active_m: str = "Действующий"
    status_active_f: str = "Действующая"
    status_inactive_dept: str = "Сокращён"
    status_inactive_wg: str = "Упразднена"
    status_inactive_emp: str = "Неактивный"
    action_add_entity: str = "Добавить {entity}"
    action_toggle_hide: str = "Скрыть/показать"
    msg_delete_element_confirm: str = "Удалить выбранный элемент?"
    oshm_new_m: str = "Новый {title}"
    oshm_new_f: str = "Новая {title}"
    button_clear_dates: str = "Очистить даты"
    date_not_set: str = "не задано"

    # --- Статистика ---
    label_object: str = "Объект:"
    label_criterion: str = "Критерий:"
    label_period: str = "Период:"
    label_year: str = "Год:"
    check_financial_year: str = "Финансовый год (окт–сен)"
    button_calculate: str = "Рассчитать"
    tooltip_split_ratio: str = "Соотношение размеров таблицы и графика"
    half_year_1: str = "I полугодие"
    half_year_2: str = "II полугодие"
    quarter_label: str = "{roman} квартал"
    msg_calc_error: str = "Не удалось выполнить расчёт:\n{error}"
    stats_period_prefix: str = "Период: {label}"
    header_total: str = "Итого"
    row_grand_total: str = "ИТОГО"
    chart_by_months: str = "{title}: по месяцам"
    chart_no_data: str = "Нет данных для отображения"
    axis_count: str = "Количество"

    # --- Список документов ---
    button_refresh: str = "Обновить"
    button_filter: str = "Фильтр"
    button_filter_count: str = "Фильтр ({count})"
    tooltip_filter_setup: str = "Настроить фильтрацию записей"
    tooltip_filter_applied: str = "Применено фильтров: {count}"
    label_page: str = "страница"
    page_of: str = "из {total}"
    tooltip_page_number: str = "Номер страницы (Enter — перейти)"
    msg_create_error: str = "Не удалось создать запись:\n{error}"
    msg_update_error: str = "Не удалось обновить запись:\n{error}"
    msg_delete_error: str = "Не удалось удалить записи:\n{error}"

    # --- Удаление записей (orm/labels) ---
    msg_delete_records_one: str = "Вы действительно хотите удалить запись о {entity}?"
    msg_delete_records_many: str = "Вы действительно хотите удалить {records} о {entity}?"

    # --- Прикреплённые файлы ---
    tooltip_add_files: str = "Добавить файлы"
    tooltip_remove_files: str = "Открепить выбранные файлы"
    tooltip_file_missing: str = "Файл отсутствует в хранилище: {path}"
    file_new_suffix: str = "(новый)"
    dialog_select_files: str = "Выберите файлы"
    msg_detach_confirm: str = "Открепить выбранные файлы ({count})?"

    # --- Элементы редактирования и базовый диалог редактирования ---
    button_more: str = "Больше"
    button_less: str = "Меньше"
    tooltip_add_items: str = "Добавить записи"
    tooltip_remove_items: str = "Удалить выбранные записи"
    placeholder_search: str = "Поиск..."
    dialog_pick_title: str = "Выбор: {entity}"
    msg_required_field: str = "Не заполнено обязательное поле «{label}»."
    msg_invalid_field: str = "Поле «{label}» заполнено некорректно: {error}"
    msg_value_must_be_int: str = "ожидается целое число"
    msg_value_must_be_float: str = "ожидается число"
    msg_number_date_together: str = "номер и дата должны быть заполнены вместе"
    msg_duplicate_fields: str = "Запись с таким сочетанием полей ({fields}) уже существует."
    msg_record_hidden_by_filters: str = (
        "Запись сохранена, но не отображается в таблице: "
        "она не попадает под действующие фильтры."
    )

    # --- Диалог фильтров ---
    dialog_add_filter_title: str = "Добавить фильтр"
    dialog_edit_filter_title: str = "Изменить фильтр"
    label_field: str = "Поле:"
    label_condition: str = "Условие:"
    label_value: str = "Значение:"
    placeholder_filter_value: str = "Введите значение"
    button_add_filter: str = "Добавить фильтр"
    filters_applied_caption: str = "Примененные фильтры:"
    filters_none: str = "Фильтры не заданы."
    tooltip_remove_filter: str = "Удалить фильтр"

    # --- Прикреплённые файлы (док-виджет) ---
    files_label_material: str = "Файлы к научному материалу № {number} от {date}"
    files_label_telegram: str = "Файлы к телеграмме № {number} от {date}"
    files_no_selection: str = "Выберите запись, чтобы увидеть прикреплённые файлы."
    files_no_outgoing: str = (
        "У выбранной записи не заданы исходящий номер и дата. "
        "Прикрепление файлов невозможно."
    )
    files_copy_progress: str = "Копирование {name} из {source} в {target}"
    files_conflict_text: str = (
        "Файл «{name}» уже существует в папке назначения.\n"
        "Заменить его или сохранить новый файл под другим именем?"
    )
    files_replace: str = "Заменить"
    files_rename_new: str = "Новое имя"
    files_skip: str = "Пропустить"
    files_rename_title: str = "Переименовать файл"
    files_rename_prompt: str = "Новое имя файла:"
    files_rename_many: str = "Переименовать {count} файлов?"
    files_detach_confirm: str = (
        "Открепить выбранные файлы ({count})?\n"
        "Файлы, не прикреплённые к другим записям, будут удалены с диска."
    )
    files_add_error: str = "Не удалось прикрепить файлы:\n{error}"
    files_attached_info: str = "Прикреплено файлов: {count}"
    action_rename: str = "Переименовать"
    action_reveal: str = "Расположение файла"
    action_assign_evaluation: str = "Выставить оценку"
    dialog_assign_evaluation_title: str = "Выставить оценку"
    label_evaluation_value: str = "Оценка:"
    label_evaluation_date: str = "Дата выставления:"
    msg_evaluation_assigned: str = "Оценка выставлена для {count} записей."

    # --- Диалог настроек ---
    settings_db_group: str = "База данных"
    settings_sqlite_file_dialog: str = "Файл базы данных SQLite"
    settings_sqlite_filter: str = "SQLite (*.db *.sqlite *.sqlite3)"
    settings_storage_label: str = "Путь к хранилищу:"
    settings_storage_dialog: str = "Директория хранилища"
    label_role: str = "Роль:"
    label_db_file: str = "Файл:"
    label_host: str = "Хост:"
    label_port: str = "Порт:"
    label_database: str = "БД:"
    label_user: str = "Пользователь:"
    label_password: str = "Пароль:"
    button_browse: str = "Обзор..."


STRINGS = AppStrings()


def reload_strings() -> None:
    """Применяет переопределения строк из активного пакета предметной области.

    Неизвестные ключи секции ``strings`` игнорируются с предупреждением
    в журнале. Вызывается после загрузки/смены пакета.
    """
    overrides = get_domain_pack().strings()
    defaults = AppStrings()
    known = {fld.name for fld in fields(defaults)}
    for key in overrides:
        if key not in known:
            logger.warning("Пакет переопределяет неизвестную строку: %s", key)
    for name in known:
        setattr(STRINGS, name, overrides.get(name, getattr(defaults, name)))
