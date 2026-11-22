# Код-ревью проекта «Внутренняя корреспонденция»

Дата: 2026-11-20. Ветка: `alex_develop` (head `0b34f81`). Предыдущее ревью: 2026-11-17 (`f762157`).
Объект: 83 модуля, ~27 000 строк кода (`internal_correspondence`), 43 тестовых файла.
Методика: pyflakes + vulture (каждая находка проверена вручную — ложные срабатывания
на переопределениях Qt и методах SQLAlchemy отфильтрованы), AST-анализ длин функций,
проверка обращений к ключам `AppStrings`, прогон тестов: **434 passed**.
Полное построчное чтение не выполнялось; новые модули последнего коммита
(`dashboard_widget`, `dashboard_service`, `imported_files_widget`, `exchange_dialogs`,
`oshm_element_charts`) просмотрены выборочно.

## Сводка

Проект остаётся в зрелом состоянии: инварианты AGENTS.md соблюдаются, ядро покрыто
тестами, критических архитектурных дефектов нет. От ревью 17.11 добавились **два
подтверждённых бага NameError** (потерянные импорты на редких путях), накопился
заметный пласт мёртвого кода (класс, ~15 функций, ~50 ключей строк, ~45 импортов)
и подтвердилась ресурсная утечка сессий БД в модальных диалогах.

## Баги (новые, подтверждённые)

1. **`gui/oshm_details_panel.py:503` — NameError при печати панели.** `QPainter` не
   импортирован (из QtGui импортирован только `QPixmap`). Путь: печать панели →
   нативный `QPrintDialog` принят → `painter = QPainter()` → падение. Импорт потерян
   при одном из коммитов печати.
2. **`gui/evaluation_import_dialog.py:851` — NameError в `RulesViewerDialog`.**
   `QDesktopServices` не импортирован; кнопка «открыть файл правил» падает по клику.
   Класс нигде не инстанцируется (см. мёртвый код), поэтому баг не всплывал.
3. **`gui/oshm_details_panel.py:580-581` — недостижимый код:** двойной `return True`
   подряд (остаток после слияния веток).

## Неиспользуемый код (подтверждено: 0 ссылок вне определения)

### Классы и функции

| Объект | Где | Комментарий |
|---|---|---|
| `ParticipatingEmployeesWidget` (весь класс, ~45 строк) | `gui/employee_picker.py:96` | Мёртв; дополнительно нарушает инвариант 1 (захардкоженные «Причастные сотрудники», тултипы) |
| `ParsingError` | `text_import/errors.py:44` | Нигде не поднимается и не ловится |
| `problem_at()` | `text_import/models.py:247` | — |
| `valid_count`, `duplicate_count` | `text_import/models.py:239,310` | Используются только в тестах |
| `node_label()` | `services/task_distribution_service.py:452` | — |
| `assigned_task_ids()` | `services/task_distribution_service.py:575` | — |
| `is_assigned()` | `services/task_distribution_service.py:582` | Только тесты |
| `reload()` | `services/task_distribution_service.py:571` | — |
| `is_leaf` (property) | `services/task_distribution_service.py:102` | — |
| `current_filters()` | `gui/document_list_widget.py:206` | — |
| `current_instance()` | `gui/edit_elements.py:455` | — |
| `_address_rows()` | `gui/edit_elements.py:698` | — |
| `current_employees` (property) | `orm/models.py:546` | — |
| `update_with_files()` ×2 | `services/document_service.py:222,258` | Только тесты; GUI правит документы через `service.create/update` |
| `create_with_files()` ×2 | `services/document_service.py:209,245` | Только тесты и один тест экспорта |
| `get_paginated()` | `services/base_service.py:45` | Только тест |
| `evaluation_share` (property) | `orm/models.py:978` | Только тесты; при этом `evaluation_display` дублирует её логику инлайн |
| `RulesViewerDialog` | `gui/evaluation_import_dialog.py:829` | Диалог определён, но нигде не создаётся |

### Ключи `AppStrings` (~50 шт.)

Ключи есть и в `string_resources.py`, и в пакете, но ни одного обращения
(`STRINGS.key` или `getattr`). Живые исключения — `import_problem_*` и `import_reason_*`:
они используются динамически (`getattr(STRINGS, f"import_problem_{code}")`,
`gui/evaluation_import_dialog.py:386-392`), удалять нельзя.

Мусор: блок `import_load`, `import_matches`, `import_errors`, `import_open_log`,
`import_no_schemes`, `import_no_rules`, `import_select_rule`, `import_file_loaded`,
`import_matched_count`, `import_unmatched_count`, `import_skipped_count`,
`import_rejected_count`, `import_rule`, `import_rule_invalid`,
`import_duplicate_skip`, `import_duplicate_update`, `import_apply_to_all`;
`status_active_m/f`, `status_inactive_dept/wg/emp/via_dept`, `oshm_col_status`;
`task_empty`, `task_no_periods`, `task_select_node`, `task_select_tasks`;
`file_new_suffix`, `msg_detach_confirm`, `msg_value_must_be_int/float`,
`button_ok`, `dialog_select_branch`, `tooltip_split_ratio`;
`dashboard_empty`, `dashboard_updated` (добавлены при работе над дашбордом,
в виджет не подключены).

### Неиспользуемые импорты (~45) и переменные

pyflakes: `logging_config.py` (`os`), `settings.py` (`dataclasses.field`),
`dashboard_widget.py` (`calendar`, `QTimer`, `QPen`), `models.py` (`sqlalchemy.Float`),
`change_tracking.py` (`uuid`), `avatar_service.py` (`shutil`),
`document_dialogs.py` (`TelegramType`, `entity_label`),
`document_list_widget.py` (`DEFAULT_PAGE_SIZE`, `SqlAlchemyTableModel`, `Telegram`),
`dashboard_service.py` (`calendar`, `Decimal`, `Iterable`, `Department`),
`report_service.py` (`WorkingGroup`) и др. Локальная переменная `current_reported`
(`reports/report_service.py:431`) присваивается, но не используется.

## Что можно упростить (дублирование)

1. **`ScientificMaterialService` / `TelegramService` — полное дублирование (~60 строк ×2).**
   `create_with_files`/`update_with_files` идентичны с точностью до типа сущности.
   Уже существует `DocumentFilesMixin` — оба метода естественно поднять туда
   (возврат через `BaseService.model`), классы сервисов схлопнутся до `_files_dir_key`
   и `__init__`.
2. **`material_columns` / `telegram_columns` (`gui/application.py`)** — общий хвост
   (задачи, входящие реквизиты, оценка, участники) собирается дважды; вынести
   в `_common_document_columns()`.
3. **`EvaluationMixin.evaluation_display`** пересчитывает `1.0 / documents_count`
   вместо вызова `self.evaluation_share` — дублирование логики; вызов свойства
   оживит его и для прода.
4. **`_ensure_tree` (177 строк, `services/task_distribution_service.py:220`)** —
   самая длинная функция проекта: загрузка 5 сущностей + построение 7 индексов +
   сборка дерева. Расписать на `_load_entities()` / `_build_indexes()` / `_assemble_tree()`.
5. **`gui/application.py` — 1416 строк** (было 1058 три дня назад). Кандидаты на вынос
   по образцу `exchange_dialogs.py`: описания колонок таблиц, генерация отчётов
   (`_generate_report` + меню-обвязка).

## Подтверждения ревью 17.11

- **Утечка сессий БД — актуальна.** Новый код (`exchange_dialogs.py`, воркеры потоков,
  `settings_dialog`) закрывает сессии корректно (`try/finally/session.close()`),
  но модальные диалоги — нет: `OSHMDialog`, `ReportDialog`, `ReferenceEditorDialog`,
  `EvaluationImportDialog`, а также вкладки и док-виджет (`DocumentListWidget`,
  `AttachedFilesWidget`, дашборд, статистика, задачи) получают `get_session()` и никогда
  не закрывают. `closeEvent`/`__del__` с закрытием есть только в `application.py` и
  `evaluation_lists_dialog.py`. Каждое открытие справочника/ОШС — минус одно соединение пула.
- Инвариант change tracking в норме: множество таблиц `_TRACKED_TABLES` совпадает
  с множеством классов `ChangeTrackedMixin` (20 шт., расхождений нет).
- Пакет: ключи `AppStrings` синхронизированы с `domain_pack.default.json` в обе
  стороны; проблема — не рассинхронизация, а ~50 мёртвых ключей (см. выше).
- Захардкоженные строки вне `AppStrings` — не проверялись заново (backlog
  ревью 17.11 сохраняется; `ParticipatingEmployeesWidget` добавляет к нему свои).

## Что НЕ трогать

- Месяцы и римские цифры в статистике — осознанное исключение (локализация, не домен).
- Глобальные реестры (`domain_pack`, `STRINGS`, тема) — безопасны при однопоточной модели.
- Автотесты Qt drag&drop — зафиксированное ограничение.
- Ключи `import_problem_*` / `import_reason_*` — живы через динамический `getattr`.

## Рекомендации (сводно, подробный план — в Refactoring_plan.md)

1. Исправить баги NameError и недостижимый код (полдня).
2. Удалить неиспользуемые импорты; добавить pyflakes в проверки.
3. Почистить мёртвые ключи `AppStrings`, перегенерировать секцию `strings`.
4. Удалить мёртвые классы/функции; решить судьбу API, живущего только в тестах.
5. Дедупликация: сервисы документов, колонки, `evaluation_display`.
6. Разбить `_ensure_tree`; планомерно уменьшать `application.py`.
7. Устранить утечку сессий — единый принцип владения сессией (вариант Б:
   одна сессия приложения для GUI, новые сессии только в фоновых воркерах).
