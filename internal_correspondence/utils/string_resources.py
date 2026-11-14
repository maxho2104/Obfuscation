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
    oshm_tree_structure: str = "Штатная структура"
    oshm_tree_workgroups: str = "Рабочие группы"
    oshm_col_element: str = "Элемент"
    oshm_select_branch_first: str = "Выберите филиал, в который нужно добавить отдел"
    oshm_tasks_section: str = "Назначенные задачи"
    oshm_membership_history: str = "прежняя группа"
    picker_tasks_title: str = "Выбор задач"
    button_hide: str = "Скрыть"
    button_statistics: str = "Статистика"
    value_yes: str = "Да"
    value_no: str = "Нет"
    oshm_col_status: str = "Статус"
    status_active_m: str = "Действующий"
    status_active_f: str = "Действующая"
    status_inactive_dept: str = "Сокращён"
    status_inactive_wg: str = "Упразднена"
    status_inactive_emp: str = "Неактивный"
    status_inactive_via_dept: str = "Неактивный (отдел сокращён)"
    action_add_entity: str = "Добавить {entity}"
    action_toggle_hide: str = "Скрыть/показать"
    msg_delete_element_confirm: str = "Удалить выбранный элемент?"
    msg_delete_elements_confirm: str = "Вы действительно хотите удалить выбранные записи ({count})?"
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
    label_subcategory: str = "Подкатегория:"
    subcategory_none: str = "—"
    label_chart_type: str = "Тип графика:"
    chart_type_bars: str = "Столбцы"
    chart_type_lines: str = "Линии"
    chart_type_pie: str = "Круговая"
    chart_by_totals: str = "{title}: итоги периода"
    stats_avg_score: str = "Средний балл: {value}"
    button_export_excel: str = "Экспорт в Excel"
    dialog_save_excel: str = "Сохранить результат в Excel"
    file_filter_excel: str = "Файлы Excel (*.xlsx)"

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

    # --- Модуль «Задачи» ---
    tab_tasks: str = "Задачи"
    task_period: str = "Период:"
    task_organization: str = "Организация"
    task_search: str = "Поиск..."
    task_assign: str = "Назначить выбранные задачи"
    task_unassign: str = "Снять выбранные задачи"
    task_create: str = "Создать задачу"
    task_import: str = "Загрузить задачи..."
    task_export: str = "Выгрузить задачи по регионам..."
    task_edit: str = "Изменить задачу..."
    task_delete: str = "Удалить задачу..."
    task_no_end: str = "Бессрочная"
    task_middle_title: str = "Задачи вышестоящего элемента"
    task_right_title: str = "Задачи элемента"
    task_empty: str = "Задачи не найдены"
    task_no_periods: str = "Нет задач за доступные периоды"
    task_select_node: str = "Выберите элемент дерева."
    task_select_tasks: str = "Выберите хотя бы одну задачу."
    task_assign_error: str = "Не удалось назначить задачи:\n{error}"
    task_unassign_error: str = "Не удалось снять задачи:\n{error}"
    task_unassign_confirm: str = "Снять выбранные задачи ({count}) с элемента «{node}»?"
    task_delete_confirm: str = "Удалить задачу «{name}»? Назначения задачи также будут удалены."
    task_import_done: str = (
        "Импорт задач завершён.\nСоздано: {created}\nОбновлено: {updated}\n"
        "Пропущено: {skipped}"
    )
    task_import_errors: str = "Ошибки импорта:"
    task_export_done: str = "Выгружено файлов: {count}.\nКаталог: {directory}"
    task_export_empty: str = "Нет задач, назначенных регионам за выбранный период."
    task_export_choose_dir: str = "Каталог выгрузки задач"
    task_import_choose_file: str = "Файл задач"
    task_create_title: str = "Новая задача"
    task_edit_title: str = "Изменение задачи"
    task_group_employee_hint: str = "Назначение сотруднику выполняется в его отделе."
    task_export_title: str = "Выгрузка задач"
    task_export_region: str = "Регион:"
    task_export_all_regions: str = "Все регионы"
    task_export_no_regions: str = "В справочнике нет регионов."
    task_export_choose_file: str = "Сохранить задачи региона"
    task_export_error: str = "Не удалось выгрузить задачи:\n{error}"
    task_code_required: str = "Не указан код задачи."
    task_name_required: str = "Не указано наименование задачи."
    task_threshold_order: str = "Частичное решение не может быть больше полного."

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

    # --- Импорт оценок из текстового файла ---
    menu_import_evaluations: str = "Импорт оценок из файла..."
    dialog_import_evaluations_title: str = "Импорт оценок из файла"
    import_step_file: str = "Файл и документ"
    import_step_check: str = "Проверка строк"
    import_step_match: str = "Сопоставление"
    import_step_result: str = "Результат"
    import_file_label: str = "Файл:"
    import_choose_file: str = "Выбрать файл..."
    import_drop_hint: str = "Перетащите файл .txt, .csv или .dat в окно"
    import_doc_no: str = "Номер документа:"
    import_doc_date: str = "Дата документа:"
    import_scheme: str = "Схема:"
    import_rule: str = "Правило:"
    import_load: str = "Загрузить"
    import_encoding: str = "Кодировка:"
    import_encoding_auto: str = "Автоопределение"
    import_preview: str = "Предпросмотр файла"
    import_validate: str = "Проверить"
    import_problems: str = "Проблемные строки"
    import_correct: str = "Исправить строку"
    import_reject: str = "Отклонить строку"
    import_unreject: str = "Вернуть строку"
    import_correct_title: str = "Исправление строки"
    import_correct_prompt: str = "Строка {row}:"
    import_matches: str = "Совпадения"
    import_match_status: str = "Статус"
    import_match_reason: str = "Причина"
    import_import: str = "Импортировать"
    import_dry_run: str = "Только проверить"
    import_counts: str = (
        "Строк: {total}; совпало: {matched}; не совпало: {unmatched}; "
        "пропущено: {skipped}; отклонено: {rejected}"
    )
    import_done: str = (
        "Импорт завершён.\nСовпало: {matched}\nНе совпало: {unmatched}\n"
        "Пропущено: {skipped}\nОтклонено: {rejected}\nФайл: {stored_path}"
    )
    import_duplicate_file: str = (
        "Этот файл уже импортировался {started_at} (журнал № {import_id})."
    )
    import_duplicate_question: str = "Продолжить импорт дубликата файла?"
    import_duplicate_skip: str = "Пропустить"
    import_duplicate_update: str = "Обновить"
    import_apply_to_all: str = "Применить ко всем совпадениям"
    import_errors: str = "Ошибки импорта"
    import_scheme_editor: str = "Редактор схемы"
    import_scheme_name: str = "Название схемы:"
    import_scheme_mode: str = "Разметка:"
    import_scheme_mode_fixed: str = "Фиксированная ширина"
    import_scheme_mode_delimited: str = "Разделитель"
    import_scheme_delimiter: str = "Разделитель:"
    import_scheme_header: str = "Строка заголовка:"
    import_scheme_header_skip: str = "Пропускать"
    import_scheme_header_names: str = "Брать имена полей"
    import_scheme_fields: str = "Поля"
    import_scheme_add_field: str = "Добавить поле"
    import_scheme_remove_field: str = "Удалить поле"
    import_scheme_save: str = "Сохранить схему"
    import_field_name: str = "Имя"
    import_field_type: str = "Тип"
    import_field_start: str = "Начало"
    import_field_length: str = "Длина"
    import_field_required: str = "Обязательное"
    import_field_date_format: str = "Формат даты"
    import_field_regex: str = "Регулярное выражение"
    import_field_default: str = "Значение по умолчанию"
    import_rules_viewer: str = "Правила сопоставления"
    import_open_log: str = "Открыть журнал"
    import_error_title: str = "Ошибка импорта"
    import_error_generic: str = "Не удалось выполнить импорт: {error}"
    import_no_schemes: str = "В каталоге схем нет ни одной схемы."
    import_no_rules: str = "Не загружены правила сопоставления."
    import_select_scheme: str = "Выберите схему."
    import_select_rule: str = "Выберите правило."
    import_file_loaded: str = "Файл загружен: {count} строк, кодировка {encoding}."
    import_rows_total: str = "Всего строк: {count}"
    import_matched_count: str = "Совпало: {count}"
    import_unmatched_count: str = "Не совпало: {count}"
    import_skipped_count: str = "Пропущено: {count}"
    import_rejected_count: str = "Отклонено: {count}"
    import_log_saved: str = "Журнал импорта: № {log_id}"
    import_scheme_saved: str = "Схема сохранена: {path}"
    import_scheme_invalid: str = "Схема содержит ошибки: {errors}"
    import_rule_invalid: str = "Правило содержит ошибки: {errors}"
    import_duplicate_eval: str = "Уже есть оценка"
    import_action_skip: str = "Пропустить"
    import_action_update: str = "Обновить"
    import_close: str = "Закрыть"
    import_back: str = "Назад"
    import_next: str = "Далее"
    import_page_of: str = "Шаг {page} из {pages}"
    msg_import_head_office_only: str = "Импорт оценок доступен только в головном офисе."
    import_status_error: str = "ошибка"
    import_status_rejected: str = "отклонена"
    import_status_matched: str = "совпало"
    import_status_unmatched: str = "не совпало"
    import_no_errors: str = "Ошибок нет"
    import_scheme_header_none: str = "Нет"
    import_file_filter: str = "Текстовые файлы (*.txt *.csv *.dat);;Все файлы (*)"
    import_rule_column: str = "Правило"
    import_entity_column: str = "Сущность"
    import_table_column: str = "Таблица"
    import_conditions_column: str = "Условия"
    import_clear: str = "Очистить"
    import_create_scheme: str = "Создать новую схему"
    import_scheme_detected: str = "Схема определена: {title}"
    import_scheme_length: str = " (длина {length})"
    import_scheme_not_detected: str = "Схема не определена: выберите файл."
    import_scheme_not_found_for_length: str = (
        "Для длины строки {length} нет подходящей схемы. Создайте новую схему."
    )
    import_evaluation_presence: str = "Имеется оценка"
    import_has_evaluation: str = "Есть оценка"
    import_no_evaluation: str = "Нет оценки"
    import_value_not_set: str = "Оценка не указана"
    import_stats_evaluations: str = "Получено оценок: {count}"
    import_stats_by_value: str = "По видам оценок: {values}"
    import_stats_reupdated: str = (
        "Переоценено документов: {documents}, материалов: {materials}"
    )
    import_problem_line_length: str = "Длина строки не соответствует схеме."
    import_problem_line_empty: str = "Пустая строка."
    import_problem_field_required: str = "Не заполнено обязательное поле."
    import_problem_field_type: str = "Некорректное числовое значение."
    import_problem_field_date: str = "Некорректная дата."
    import_problem_field_regex: str = "Значение не соответствует формату."
    import_problem_field_start: str = "В схеме не задано начало поля."
    import_problem_field_count: str = "Неверное количество полей."
    import_reason_key_empty: str = "Не удалось собрать код филиала."
    import_reason_year_month_invalid: str = "Некорректный отчётный месяц."
    import_reason_document_not_found: str = "Документ не найден."
    import_reason_document_ambiguous: str = "Найдено несколько документов."
    import_reason_rule_not_selected: str = "Не выбрано правило."
    import_reason_scheme_not_selected: str = "Не выбрана схема."


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
