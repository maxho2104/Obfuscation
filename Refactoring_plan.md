# План рефакторинга

Дата: 2026-11-20. Основание: `CODE_REVIEW.md` (head `0b34f81`).
Каждый этап — отдельный коммит (или серия коммитов) с зелёными тестами:
`.venv/Scripts/python.exe -m pytest tests -q` и проверкой импорта GUI
`PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"`.
После каждого этапа — запись в `WORK_NOTES.md`.

## Этап 1. Исправление багов (полдня, риск ≈ 0)

1. **`gui/oshm_details_panel.py`** — добавить `QPainter` в импорт из `PyQt5.QtGui`
   (строка 17): `from PyQt5.QtGui import QPainter, QPixmap`.
   Проверка: ручной прогон печати панели (нативный диалог — только вручную;
   компилируемость и импорт проверяются тестами).
2. **`gui/evaluation_import_dialog.py`** — добавить `QDesktopServices` в импорт из
   `PyQt5.QtGui` (строка 10). Проверка: импорт модуля + открытие
   `RulesViewerDialog` (см. Этап 2 — класс удаляется; если удалим, этот пункт
   снимается вместе с ним).
3. **`gui/oshm_details_panel.py:581`** — удалить второй подряд `return True`
   (недостижимый код).

> Порядок важен: пункты 1–3 сначала, т.к. дальнейшие этапы трогают те же файлы.

## Этап 2. Удаление неиспользуемых импортов (1–2 часа)

1. Прогнать `python -m pyflakes internal_correspondence`, убрать все
   «imported but unused» кроме реэкспортов в `__init__.py` (проверить каждый).
2. Удалить неиспользуемую локальную переменную `current_reported`
   (`reports/report_service.py:431`).
3. Добавить pyflakes в регулярные проверки (pre-commit или команда в
   AGENTS.md рядом с pytest) — иначе мусор накопится снова.
4. Добавить `pyflakes`/`vulture` в `requirements-dev.txt` (создать, если нет).

## Этап 3. Очистка ключей `AppStrings` (полдня, требует внимательности)

1. Удалить ~50 мёртвых ключей из `internal_correspondence/utils/string_resources.py`
   (список — в `CODE_REVIEW.md`, раздел «Ключи AppStrings»).
2. **Не трогать** `import_problem_*` и `import_reason_*` — они живы через
   `getattr(STRINGS, f"import_problem_{code}")` (`evaluation_import_dialog.py:386-392`).
   Проверка после удаления: `grep -rn "getattr(STRINGS" internal_correspondence`.
3. Запустить `scripts_dev/update_pack_strings.py` — перегенерирует секцию `strings`
   в `core/domain_pack.default.json`.
4. Проверить: тесты пакета (секция strings синхронна с `AppStrings`), импорт GUI.

## Этап 4. Удаление мёртвых классов и функций (1 день)

### 4.1. Безусловно мёртвое (удалить вместе с тестами, если тесты только на них)

| Объект | Файл |
|---|---|
| `ParticipatingEmployeesWidget` (+ приватные методы) | `gui/employee_picker.py:96` |
| `ParsingError` | `text_import/errors.py:44` |
| `problem_at()` | `text_import/models.py:247` |
| `node_label()` | `services/task_distribution_service.py:452` |
| `reload()` | `services/task_distribution_service.py:571` |
| `assigned_task_ids()` | `services/task_distribution_service.py:575` |
| `current_filters()` | `gui/document_list_widget.py:206` |
| `current_instance()` | `gui/edit_elements.py:455` |
| `_address_rows()` | `gui/edit_elements.py:698` |
| `WorkingGroup.current_employees` | `orm/models.py:546` |
| `RulesViewerDialog` | `gui/evaluation_import_dialog.py:829` |

> `ParticipatingEmployeesWidget` дополнительно нарушает инвариант 1
> (захардкоженные русские строки) — удаление закрывает и это.

### 4.2. API, живущее только в тестах — решить судьбу по каждому пункту

| Объект | Решение |
|---|---|
| `DocumentFilesMixin.create_with_files` / `update_with_files` (после поднятия в миксин, см. Этап 5) | **Оставить и перевести GUI**: `gui/document_list_widget.py:383` должен создавать/править документ с файлами через эти методы, а не через голый `create/update` + отдельное прикрепление |
| `BaseService.get_paginated` | Либо использовать в GUI там, где списки грузятся целиком (поиск кандидатов: `reference_editor.py`, `evaluation_lists_dialog.py`), либо удалить вместе с `tests/test_base_service.py:80` |
| `ImportReport.valid_count` / `Preview.duplicate_count` (`text_import/models.py`) | Использовать в `evaluation_import_dialog.py` при формировании сводки импорта, либо удалить вместе с ассертами тестов |
| `TaskDistributionService.is_assigned` | Использовать в `task_distribution_widget.py` вместо ручной проверки членства, либо удалить вместе с `tests/test_task_distribution.py:179-180` |
| `EvaluationMixin.evaluation_share` | Оживёт автоматически при дедупликации `evaluation_display` (Этап 5, п. 3) |

Принцип: публичный API сервисов, который никто не зовёт, — это не «про запас»,
а долг. Либо находим реального потребителя (лучше), либо удаляем.

## Этап 5. Дедупликация (1–2 дней, всё под тестами)

### 5.1. Сервисы документов

- Поднять `create_with_files` / `update_with_files` из `ScientificMaterialService`
  и `TelegramService` в `DocumentFilesMixin` (`services/document_service.py:30`).
  Тип возврата — `BaseService.model` (дженерик). После этого каждый сервис —
  это `_files_dir_key` + `__init__` (~10 строк).
- Обновить вызовы в тестах (`tests/test_document_service.py`,
  `tests/test_export_import.py:482`) — имена методов сохраняются, правки минимальны.
- Перевести `gui/document_list_widget.py` на `create_with_files`/`update_with_files`
  (здесь же решается Этап 4.2, строка 1 таблицы).

### 5.2. Колонки таблиц

- В `gui/application.py` вынести общий хвост `material_columns`/`telegram_columns`
  (задачи, входящие реквизиты, оценка, участники) в `_common_document_columns()`.
  Каждая функция — только свои специфичные поля + вызов общей.

### 5.3. Оценка документа

- `EvaluationMixin.evaluation_display` (`orm/models.py:990`): заменить инлайн-расчёт
  `share = 1.0 / documents_count` на `self.evaluation_share`.
  Тесты: `tests/test_evaluation_display.py`, `tests/test_evaluation_service.py:327`.

### 5.4. Разбиение `_ensure_tree`

- `services/task_distribution_service.py:220` (177 строк) →
  `_load_entities()` (5 запросов), `_build_indexes()` (7 словарей),
  `_assemble_tree()` (сборка узлов). Поведение не меняется;
  тесты: `tests/test_task_distribution.py`.

### 5.5. Уменьшение `application.py` (фоновая задача, не одним коммитом)

- Текущий размер 1416 строк. По мере ближайших правок выносить:
  колонки таблиц → `gui/column_defs.py`; работу с отчётами → в сервис/диалог;
  следить, чтобы новые фичи не добавлялись в `application.py`, а жили
  в своих модулях (по образцу `exchange_dialogs.py`).

## Этап 6. Утечка сессий БД (самое важное архитектурно, 1–2 дня)

**Проблема:** модальные диалоги (`OSHMDialog`, `ReportDialog`, `ReferenceEditorDialog`,
`EvaluationImportDialog`) и долгоживущие виджеты получают `db_manager.get_session()`
и никогда не закрывают. Новый код (`exchange_dialogs.py`) показывает правильный
паттерн: `try/finally/session.close()`.

**Решение — вариант Б (рекомендуется):**

1. `MainWindow` создаёт **одну сессию приложения** (`self.app_session =
   db_manager.get_session()`) и передаёт её всем вкладкам, док-виджету и модальным
   диалогам. Диалоги её не закрывают — она живёт столько, сколько главное окно.
2. `closeEvent` главного окна закрывает `app_session` (и ничего больше).
3. Фоновые операции (импорт/экспорт) по-прежнему создают свои сессии внутри
   воркеров — объект сессии SQLAlchemy нельзя шарить между потоками.
4. Убрать размножение `get_session()` в `application.py` (сейчас ~15 точек):
   оставить один вызов.

**Альтернатива — вариант А (если вариант Б отклонён):** закрывать сессию
в `closeEvent`/`done()` каждого диалога, получающего `get_session()`. Меньше
правок, но оставляет размножение соединений (7+ сессий одновременно).

**Проверка:** тест с подсчётом `len(db_manager.engine.pool.checkedout())`
до/после открытия-закрытия диалога; ручной сценарий «открыть ОШС 20 раз».

## Этап 7. После рефакторинга

1. Обновить `WORK_NOTES.md` (что изменено по файлам, результаты pytest).
2. Обновить `README.md`, если изменится поведение (не планируется) или
   список проверок в AGENTS.md (добавление pyflakes).
3. Прогнать полный чек-лист AGENTS.md: pytest, импорт GUI, пакет strings.
4. Обновить `CODE_REVIEW.md` (отметить закрытые пункты).

## Порядок работ и оценка

| Этап | Трудоёмкость | Риск | Коммиты |
|---|---|---|---|
| 1. Баги | 0.5 дня | нулевой | 1 |
| 2. Импорты | 0.2 дня | нулевой | 1 |
| 3. Ключи AppStrings | 0.5 дня | низкий (динамика getattr!) | 1 |
| 4. Мёртвый код | 1 день | низкий | 2–4 |
| 5. Дедупликация | 1–2 дня | средний (трогает GUI/сервисы) | 3–5 |
| 6. Сессии | 1–2 дня | средний (трогает все диалоги) | 2–3 |
| 7. Финал | 0.2 дня | — | — |

Этапы 1–4 независимы друг от друга и могут идти параллельно/в любом порядке.
Этап 5.1 желательно до 4.2 (чтобы решение по `create_with_files` принималось
уже после дедупликации). Этап 6 — последним из крупных: он касается подписей
конструкторов, которые меняются в 5.2/5.5.
