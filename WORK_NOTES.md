# Рабочие заметки по проекту «Внутренняя корреспонденция»

Файл ведётся ассистентом: здесь фиксируются обсуждённые правки, проделанная работа и планы на следующие шаги.

---

## 2026-11-09 — Старт работы

### Контекст
- Прочитаны README.md, main.py, pyproject.toml, requirements.txt, settings.ini, структура пакета `internal_correspondence` (~11,4 тыс. строк с тестами).
- Проект: PyQt5 + SQLAlchemy 2.x + Alembic, SQLite (филиал) / PostgreSQL (головной офис), сборка PyInstaller.
- Текущие настройки (`settings.ini`): роль `branch`, филиал `BR-002`, БД `sqlite:///D:/Projects/Obfuscation/123.db`, тёмная тема.

### План (обсуждается)
- [ ] Этап 1: обсуждение правок и исправлений с пользователем — перечень изменений пока не зафиксирован.
- [ ] Этап 2: выполнение согласованных правок.
- [ ] Этап 3: проверка (запуск тестов, ручная верификация).

### Сделано
- Создан этот файл заметок.

### Следующие шаги
- Дождаться от пользователя перечня правок, зафиксировать их здесь с приоритетами и деталями реализации.

---

## 2026-11-09 — Обсуждение 1: хранение перечислений и отделение значений от логики

### Запрос пользователя
Вынести соответствие «код ↔ значение» перечислений из кода в отдельный файл; в БД хранить компактные коды. Стратегическая цель — white-label: одна программа, разные предметные области (вузы, больницы…) за счёт настроечных файлов.

### Текущее состояние кода
- Перечисления хранятся в БД как короткие кириллические коды в `String(50)` (`"С"`, `"ДОК"`, `"ОХР"`, `"Б"`…): `ScientificMaterial.type`, `Telegram.type`, `Telegram.report_type`, `Evaluation.value`, `Source.type`, `ScientificTask.type`.
- Коды/метки/веса зашиты в `internal_correspondence/core/constants.py`: Python-Enum + `*_LABELS` словари + `EVALUATION_WEIGHTS`.

### Выводы обсуждения
- Сжатие БД не аргумент: экономия 2–5 байт/строку на фоне UUID (16 байт) — доли процента. Ценность — в отделении значений от логики.
- Правила безопасности конфиг-файла: коды неизменяемы (deprecated вместо переиспользования); у пакета значений есть `id`+`version`, версия пишется в экспортный ZIP и проверяется при импорте; валидация значений при старте и в сервисном слое (нет FK на уровне СУБД).
- Вариант A (рекомендован): «пакет предметной области» — JSON-конфиг с перечислениями/метками/весами, реестр, семантические ключи в логике, без миграции БД, дефолтный пакет как фолбэк.
- Вариант B (числовые/char-коды + Alembic-миграция): отклонён как неоправданный (миграция баз, нечитаемый raw-SQL, риски обмена).
- Вариант C (стратегия): полный white-label — в пакет выносить также метки сущностей/полей, имена директорий, строки UI. Этапами поверх A.

### Статус
Решено: вариант **C** (полный white-label, поэтапно поверх A) + замена UUID на простые id в малых таблицах.

---

## 2026-11-09 — Обсуждение 2: UUID → простые id, этапность варианта C

### Факты (проверено по коду)
- `change_tracking.py::_TRACKED_TABLES` — в обмен уходят все 17 таблиц, включая ОШС, файлы, оценки, адресации.
- UUID на PK: `changes`, `departments`, `working_groups`, `employees`, `file_records`, `scientific_materials`, `telegrams`, `report_addresses`, `evaluation_lists`, `evaluations`.
- UUID у ОШС — защита от коллизий при слиянии данных филиалов в головном офисе (README: «UUID формируются с привязкой к филиалу»). Простой автоинкремент сломает слияние.

### Предложение (ожидает подтверждения)
- `changes` → int autoincrement: таблица локальная и транзитная, рисков нет — делать.
- ОШС: либо оставить UUID, либо префиксные id вида `BR-002-000042` (String вместо PGUUID, явная привязка к филиалу, миграция FK и ассоциативных таблиц).
- `scientific_materials`, `telegrams`, `file_records`, `evaluations`, `evaluation_lists`, `report_addresses` — оставить UUID.

### Этапность варианта C
- C1: реестр перечислений + JSON-пакет предметной области (коды, метки, веса; семантические ключи; дефолт-пакет фолбэк). Без миграции БД.
- C2: в пакет — метки сущностей и полей (`__entity_label__`, `info={"label": ...}`, `string_resources.py`).
- C3: в пакет — имена директорий хранилища, строки UI; `id`/`version` пакета в экспортном ZIP, проверка при импорте.

### Открытые вопросы
1. ~~ОШС: префиксные id `BR-002-000042` или оставить UUID?~~ → **Решено: ОШС остаётся на UUID.**
2. ~~Порядок: C1 → правка id или наоборот?~~ → **Решено: сначала правка id (`changes` → int), затем C1.**

---

## План реализации (согласован)

1. ~~**Шаг 1:** `changes.id` UUID → Integer autoincrement; `ChangeTrackedMixin.change_id` PGUUID → Integer FK.~~ **ВЫПОЛНЕНО 2026-11-09.**
2. **Шаг 2 (C1, следующий):** реестр перечислений + JSON-пакет предметной области (коды, метки, веса; семантические ключи; дефолт-пакет фолбэк).
3. **Шаг 3 (C2):** в пакет — метки сущностей и полей.
4. **Шаг 4 (C3):** в пакет — имена директорий, строки UI; `id`/`version` пакета в экспортном ZIP + проверка при импорте.

---

## 2026-11-09 — Шаг 1 выполнен: changes.id UUID → Integer

### Изменения
- `internal_correspondence/orm/models.py`:
  - `Change.id` — `Integer, primary_key=True, autoincrement=True` (был UUID).
  - `ChangeTrackedMixin.change_id` — `Integer FK -> changes.id` (был PGUUID), затрагивает все 17 отслеживаемых таблиц.
- Новая миграция `alembic/versions/b7c4d2f0a1e9_changes_int_pk.py`:
  - upgrade **сохраняет данные**: старые UUID → новые int через временную колонку `old_id`, ссылки `change_id` переносятся, FK пересоздаются (`fk_<table>_change_id`, `ON DELETE SET NULL`).
  - downgrade потерьный (очищает транзитную таблицу `changes`) — задокументировано в миграции.
- Подводный камень, найденный при проверке: `rename_table` уносит индексы `ix_changes_*` на `changes_old` — перед созданием новых индексов старые удаляются; FK в SQLite создаётся отдельным batch-шагом после rename колонки (иначе не применяется).

### Проверка
- Создано окружение `.venv` (Python 3.12, PyQt5, SQLAlchemy 2.0.57, alembic, pytest, faker…; PyInstaller не ставился).
- `pytest`: **107/107 passed**.
- Миграция проверена на БД старой схемы (SQLite): данные сохранены, `change_id` перенесён, типы `INTEGER`, FK → `changes`; downgrade отрабатывает. Реальная БД `123.db` не затрагивалась — применить через `alembic upgrade head` при необходимости.

### Следующий шаг
- Шаг 2 (C1): реестр перечислений + JSON-пакет предметной области.

---

## 2026-11-09 — Шаг 2 выполнен: пакет предметной области (C1)

### Изменения
- **Новое:** `internal_correspondence/core/domain_pack.py` — реестр пакета предметной области:
  - `EnumValue` (key/code/label/weight/deprecated), `EnumDef`, `DomainPack` с валидацией (обязательные поля, уникальность ключей и кодов, тип weight);
  - загрузка внешнего JSON (`load_domain_pack`), встроенный фолбэк (`default_domain_pack`), глобальный реестр (`get/set/init_domain_pack`) и модульные аксессоры (`enum_label`, `enum_labels`, `enum_codes`, `enum_weight`, `enum_code_of`);
  - устаревшие значения (`deprecated`) скрыты из выбора, но их метки остаются доступными для старых записей БД.
- **Новое:** `internal_correspondence/core/domain_pack.default.json` — встроенный пакет `scientific-network v1.0.0`, 7 перечислений (material_type, research_type, evaluation_value с весами 0–3, scientific_task_type, telegram_type, telegram_report_type, source_type).
- `core/settings.py`: новая настройка `domain_pack` (путь к внешнему JSON; пусто — встроенный).
- `gui/application.py`: загрузка пакета при старте; при ошибке — предупреждение и фолбэк на встроенный.
- Рефакторинг потребителей на аксессоры реестра: `reports/statistics_service.py`, `gui/document_dialogs.py`, `gui/reference_dialogs.py`.
- `core/constants.py`: удалены словари `*_LABELS` и не использовавшийся `EVALUATION_WEIGHTS` (метки и веса теперь в пакете). Enum-классы оставлены как семантические ключи со значениями-кодами по умолчанию (используются в tests/seed_data.py).

### Проверка
- Новые тесты `tests/test_domain_pack.py` (18 шт.): дефолтный пакет, валидация ошибок, реестр, deprecated, внешний пакет.
- `pytest`: **125/125 passed**; импорт `gui.application` и работа реестра проверены.

### Отложено (backlog)
- Валидация кодов БД против активного пакета при старте (предупреждения о неизвестных кодах).
- C2: метки сущностей/полей в пакет; C3: директории, строки UI, `id`/`version` пакета в экспортном ZIP + проверка при импорте.

### Следующий шаг
- Шаг 3 (C2): в пакет — метки сущностей и полей.

---

## 2026-11-09 — Шаг 3 выполнен: метки сущностей и полей в пакете (C2)

### Изменения
- `core/domain_pack.py`: новая секция пакета `entities` — `EntityDef` (label, label_plural, label_prepositional(_plural), fields{label, short, required}); методы `entity_label`, `entity_label_prepositional`, `entity_field_info`; валидация секции при загрузке. Секция опциональна — пакеты формата C1 остаются валидными.
- `orm/labels.py`: разрешение меток теперь двухуровневое — **пакет переопределяет**, метаданные моделей (`__entity_label__`, `info`, `__field_labels__`) остаются встроенным дефолтом. `field_required` тоже учитывает переопределение `required` из пакета.
- `core/domain_pack.default.json`: сгенерирована секция `entities` — полное зеркало метаданных моделей (18 сущностей, 109 полей), готовый шаблон для авторов внешних пакетов.

### Проверка
- 6 новых тестов (зеркало моделей, переопределение меток сущности/поля/required, предложный падеж, фолбэк на модель, валидация секции).
- `pytest`: **131/131 passed**.

### Следующий шаг
- Шаг 4 (C3): имена директорий хранилища и строки UI в пакет; `id`/`version` пакета в экспортный ZIP + проверка при импорте; валидация кодов БД при старте (из backlog).

---

## 2026-11-09 — Шаг 4 выполнен: директории, строки UI, meta.json, валидация кодов (C3)

### Изменения
- `core/domain_pack.py`: новые опциональные секции пакета — `directories` (имена служебных директорий) и `strings` (строки интерфейса); аксессоры `DomainPack.directory()`, `DomainPack.strings()`, модульная функция `dir_name()`; дефолты директорий в `DEFAULT_DIRECTORIES`.
- `core/domain_pack.default.json`: добавлены зеркальные секции `directories` (5) и `strings` (23).
- `utils/string_resources.py`: `STRINGS` стал изменяемым; `reload_strings()` накладывает переопределения пакета (неизвестные ключи — предупреждение в лог). Вызывается при старте после загрузки пакета.
- Директории переведены на пакет: `document_service` (ключи `material_files`/`telegram_files`, корень `files`), `export_service` (`export`), `application` (`files`/`templates`/`export`), `import_service` (`files`/«Импорт»).
- Экспорт/импорт: в ZIP пишется `meta.json` (`app`, `pack_id`, `pack_version`, `exported_at`); при импорте несовпадение `pack_id`/`pack_version` → предупреждение в результате (`warnings`) и в сообщении оператору; архивы без `meta.json` (старый формат) импортируются без замечаний.
- Новое: `services/enum_validation.py` — при старте сверяет DISTINCT-коды enum-колонок БД с активным пакетом (deprecated-коды считаются известными); расхождения — в лог и предупреждение оператору.

### Проверка
- Новый `tests/test_domain_pack_integration.py` (12 тестов): директории, строки, meta.json (запись/совпадение/чужой пакет/legacy), валидация кодов (неизвестный/известный/deprecated).
- `pytest`: **143/143 passed**; импорт `gui.application` проверен.

### Статус плана
Все согласованные шаги выполнены: 1 (changes→int), C1, C2, C3. White-label: перечисления, метки сущностей/полей, директории и строки UI полностью выносимы во внешний JSON-пакет (`domain_pack` в settings.ini).

### Возможные дальнейшие шаги (не согласованы)
- ~~Редактор/экспорт текущего пакета из UI (выгрузить встроенный пакет в файл для правки).~~ **ЧАСТИЧНО ВЫПОЛНЕНО 2026-11-09** — выгрузка активного пакета в JSON из меню «Данные» → «Пакет предметной области...» с предложением назначить файл активным (применяется после перезапуска). Полноценный редактор пакета в UI — отдельная задача.
- ~~Секция `strings` для остальных захардкоженных строк (меню «Вид», «Статистика», «ОШС», сообщения экспорта/импорта и др.).~~ **ВЫПОЛНЕНО 2026-11-09** — см. запись ниже; `AppStrings` вырос до 107 ключей. Остаток за пределами согласованного объёма: `first_run_wizard.py`, `reference_editor.py`, `filter_dialog.py`, `settings_dialog.py`, `table_model.py`, `employee_picker.py`, `document_dialogs.py`, `reference_dialogs.py`, `evaluation_delegate.py`, `theme.py`, `i18n.py`, `filter_model.py` (в основном формы справочников и мастер первого запуска); месяцы в статистике осознанно оставлены (локализация, не домен).
- ~~README: документировать формат пакета предметной области.~~ **ВЫПОЛНЕНО 2026-11-09** — раздел «Пакет предметной области» в README: структура секций, правила совместимости, пример для учебного заведения (пример проверен загрузчиком).

---

## 2026-11-09 — Выгрузка пакета предметной области из UI

### Изменения
- `core/domain_pack.py`: `to_dict()` у `EnumDef`, `EntityDef`, `DomainPack` + `save_domain_pack()` — сериализация пакета обратно в JSON.
- `gui/application.py`: пункт меню «Данные» → «Пакет предметной области...» — выгрузка активного пакета в файл; предложение назначить файл активным (настройка `domain_pack`, применяется после перезапуска).
- README: строка о выгрузке пакета через меню.

### Проверка
- 2 новых теста сериализации (круговой оборот дефолтного пакета, сохранение/перезагрузка файла).
- `pytest`: **145/145 passed**; импорт `gui.application` проверен.

---

## 2026-11-09 — Вынос остальных строк UI в пакет (white-label завершён)

### Изменения
- `utils/string_resources.py`: `AppStrings` расширен с 23 до **107 ключей** (дефолты = прежние литералы дословно). Группы: главное окно/меню/действия, заголовки диалогов, экспорт/импорт, пакет предметной области, ОШС, статистика, список документов, подтверждения удаления, прикреплённые файлы. Шаблоны — с именованными плейсхолдерами (`{error}`, `{count}`, `{entity}`, `{records}`, `{path}` и т.д.).
- `gui/application.py`: меню, вкладка «Статистика», экспорт/импорт/справочники, диалоги пакета, ОШС, выбор филиала, ошибки/предупреждения → `STRINGS.*`.
- `gui/oshm_dialog.py`: заголовок окна, шапка дерева, статусы элементов, контекстное меню, подтверждение удаления, подписи «Новый/Новая», кнопки → `STRINGS.*`.
- `gui/statistics_widget.py`: лейблы, чекбокс фин. года, кнопка расчёта, полугодия/кварталы, префикс периода, «Итого»/«ИТОГО», заголовки и ось графика, ошибка расчёта → `STRINGS.*`. Месяцы осознанно оставлены (локализация, не домен).
- `gui/document_list_widget.py`: кнопки тулбара, фильтр (вкл. счётчик), пагинация («страница», «из N», тултип), сообщения создания/обновления/удаления → `STRINGS.*`.
- `gui/attached_files_widget.py`: тултипы кнопок, «файл отсутствует», суффикс «(новый)», диалог выбора, подтверждение открепления → `STRINGS.*`.
- `orm/labels.py`: `deletion_confirmation_text` переведён на шаблоны `msg_delete_records_one/many` (дефолты дают прежние строки дословно).
- `core/domain_pack.default.json`: секция `strings` регенерирована из `AppStrings` (107 ключей) скриптом `scripts_dev/update_pack_strings.py` — повторно запускать после добавления ключей.

### Проверка
- `pytest`: **145/145 passed** (в т.ч. дословная проверка текстов удаления в `test_entity_labels.py`); импорт `gui.application`, `document_list_widget`, `attached_files_widget` проверен.

---

## План на будущее (backlog, не согласовано)

- **Привести раздел «Использование» README к фактической реализации** (проверено 2026-11-09): экспорт/импорт уехали в меню «Файл» (в README — «Данные»); «Расположение файлового хранилища» и «Роль» — в мастере первого запуска и «Файл»→«Настройки...» (не пункты меню «Данные»); справочники — прямо в меню «Данные» (не подменю «Изменение»); «Прикрепляемые файлы» — встроенный виджет под таблицей (не док-виджет из меню «Вид», без drag&drop); прогресс-бары и потоки для длительных операций не реализованы. Решить: править README под реализацию или реализацию под ТЗ.
- **Применить миграцию `c4a8f1b2d3e4` к реальной базе**: файл `D:/Projects/Obfuscation/123.db` (из `settings.ini`) на этом компьютере отсутствует — каталога `D:\Projects` нет. Отложено пользователем 2026-11-09. При появлении базы: скопировать в `real_db/`, бэкап, `alembic upgrade head`, проверка.
- **Довынос строк UI в пакет**: `first_run_wizard.py` (мастер первого запуска), `reference_editor.py`, `filter_dialog.py`, `settings_dialog.py`, `table_model.py`, `employee_picker.py`, `document_dialogs.py`, `reference_dialogs.py`, `evaluation_delegate.py`, `theme.py`, `i18n.py`, `filter_model.py`. После добавления ключей в `AppStrings` регенерировать секцию `strings` пакета скриптом `scripts_dev/update_pack_strings.py`.
- **Редактор пакета предметной области в UI** (сейчас есть только выгрузка в JSON).

---

## 2026-11-09 — Связь с задачами N-N и адресация доклада телеграмм

### Изменения
- **Модель (`orm/models.py`):** связь «документ — научная задача» переведена с FK `task_id` (1-N) на ассоциативные таблицы `material_tasks` и `telegram_tasks` (N-N); у `ScientificMaterial` и `Telegram` вместо `task_id`/`task` — связь `tasks` (метка «Задачи»). Документ — владелец связи (первая колонка ассоциативной таблицы), поэтому change-tracking и экспорт/импорт работают обобщённо без правок. У `Telegram` появилась связь `report_addresses` (cascade delete-orphan) — таблица «Адресация доклада» («кому доложено и когда») наконец подключена к модели.
- **Миграция `alembic/versions/c4a8f1b2d3e4_tasks_many_to_many.py`:** создаёт обе ассоциативные таблицы, переносит существующие `task_id` и удаляет колонки; downgrade возвращает колонки с одной (минимальной по коду) задачей на документ. Проверена на SQLite скриптом `scripts_dev/test_migration_tasks_nn.py` (upgrade → перенос данных → downgrade → повторный upgrade).
- **Интерфейс (`gui/document_dialogs.py`):** комбобокс «Задача» заменён на `TaskSelectWidget` — список задач с чекбоксами (в обоих диалогах); в диалоге телеграммы добавлен `ReportAddressesWidget` — список «руководитель — дата доклада» с добавлением/удалением; существующие записи адресации сохраняют идентичность (лишние DELETE/INSERT не генерируются).
- **Статистика (`reports/statistics_service.py`):** критерий «Задача» перебирает `document.tasks` — документ с несколькими задачами учитывается в каждой (как «Источник»).
- **Пакет (`core/domain_pack.default.json`):** поле `task_id` («Задача») заменено на `tasks` («Задачи») у обеих сущностей; у `Telegram` добавлено `report_addresses` («Адресация доклада»).
- **seed_data.py:** документам назначается случайный набор из 1–2 задач; адресация заполнялась и раньше — теперь через подключённую связь.
- **README:** описания полей «Задачи» материала и телеграммы — отношение n-n.

### Проверка
- Новый `tests/test_document_tasks_reports.py` (6 тестов): N-N в обе стороны, переназначение, трекинг `tasks` в Change, каскад и delete-orphan адресации, статистика по каждой задаче.
- Дымовой тест экспорта/импорта: `tasks` и `report_addresses` переносятся через ZIP корректно.
- `pytest`: **151/151 passed**.

---

## 2026-11-11 — AGENTS.md: правила доработки для агентов

### Изменения
- Создан `AGENTS.md` — инструкция для агентов/разработчиков, дополняющая README (README = ТЗ и предметка, AGENTS.md = инварианты, которые нельзя сломать):
  - чек-лист перед сдачей (pytest, импорт GUI, миграция, регенерация `strings`, README/WORK_NOTES);
  - инвариант пакета предметной области: коды перечислений неизменяемы, строки только через `AppStrings`/`STRINGS` + `scripts_dev/update_pack_strings.py`, метки через `orm/labels.py`, директории через `dir_name()`;
  - инвариант change tracking: `_TRACKED_TABLES`, правило владельца N-N связи (первая колонка ассоциативной таблицы), `meta.json`;
  - инвариант схемы БД: миграции с переносом данных, batch-режим SQLite, соглашение по типам PK;
  - совместимость СУБД/ОС, стиль кода, оформление результата в WORK_NOTES.

---

## 2026-11-12 — Модуль «Задачи»: распределение по иерархии организации

### Изменения
- **Спецификация:** `tasks.md` в корне — согласованная постановка v3 (иерархия с виртуальным
  корнем «Организация» для ГО, группы под отделами, таблица `added_tasks`, периоды,
  права, интерфейс, импорт/выгрузка по регионам).
- **Модель (`orm/models.py`):** удалены `task_employee_association`,
  `ScientificTask.employees` и `Employee.tasks`; добавлен `AddedTask` (`added_tasks`:
  UUID PK, `task_id` FK CASCADE, `node_type`, `node_id`, unique-тройка, индексы) с
  `ChangeTrackedMixin`/`VersionedMixin`; у `ScientificTask` — `added_tasks`
  (cascade delete-orphan). `orm/__init__.py`, `_TRACKED_TABLES`, пакет предметной области
  и секция `strings` обновлены.
- **Миграция `alembic/versions/f3b1c9d2e4a7_task_distribution.py`:** создаёт `added_tasks`,
  удаляет `task_employees`; downgrade пересоздаёт `task_employees`. Проверена скриптом
  `scripts_dev/test_migration_task_distribution.py` (upgrade → downgrade → повторный upgrade).
- **Сервисы:** `services/task_distribution_service.py` — `FinancialPeriod`, дерево узлов,
  назначение/снятие с проверкой строгой иерархии, прав роли и потомков, автоназначение
  региона филиалом, `add_region_assignments` для импорта; `ScientificTaskService` —
  `create_task/update_task/delete_task` с валидацией кода, типа, дат и порогов.
- **Импорт/экспорт:** `importexport/task_import.py` (upsert задач из листа «Научные задачи»),
  `importexport/task_export.py` (один XLSX на регион), в `ImportService` — проверка узла
  `AddedTask` (тип, существование/активность, область филиала, дубликат, импорт узла из
  того же пакета).
- **Интерфейс:** `gui/task_dialog.py`, `gui/task_table_model.py`,
  `gui/task_distribution_widget.py`; вкладка «Задачи» между «Телеграммами» и «Статистикой»;
  розовый цвет нераспределённых строк в `Theme`; ~30 строк в `AppStrings`; обновление
  вкладки при импорте и смене темы.
- **Документация:** README — сущность «Назначение задачи», раздел «Распределение научных
  задач», особенности модуля.

### Проверка
- `pytest`: **158 passed** (включая новые `tests/test_task_distribution.py` — 7 тестов и
  `tests/test_task_widget.py` — 1 дымовой тест).
- `scripts_dev/test_migration_task_distribution.py`: upgrade/downgrade/повторный upgrade OK.
- `python -m py_compile` изменённых модулей; импорт `gui.application` — OK.
- `scripts_dev/update_pack_strings.py`: 147 ключей.

### Отложено
- Ленивое построение дерева (сейчас строится целиком; для ожидаемых объёмов приемлемо).
- Привязка назначений к финансовому году не делается — назначение глобально для задачи.
- Отдельная обработка удаления узлов ОШС (назначения на удалённые узлы не чистятся).
- Драг-н-дроп реализован, но автоматическим тестом не покрыт.

---

## 2026-11-12 — Виртуальное окружение проекта

### Изменения
- Создано локальное окружение `.venv` (Python 3.15.2, pip 26.3); каталог уже в `.gitignore`.
- Установлены зависимости из `requirements.txt` (PyQt5/PyQtChart, SQLAlchemy, Alembic, psycopg2-binary, openpyxl, python-docx, odfpy, PyInstaller, pytest, faker).

### Проверка
- `pip check` — No broken requirements found.
- `pytest tests` — **159 passed**.
- `scripts_dev/test_migration_task_distribution.py` — upgrade/downgrade/повторный upgrade OK.
- Импорт `internal_correspondence.gui.application` и библиотек — OK.

---

## 2026-11-13 — Модуль «Задачи»: drag&drop, геометрия и состав групп по периоду

### Изменения
- **Drag&drop (`gui/task_table_model.py`, `gui/task_distribution_widget.py`):**
  `TaskTableModel` отдаёт собственный MIME-тип
  `application/x-internal-correspondence-task-ids` (`mimeTypes/mimeData/
  supportedDragActions`); `_TaskTableView` переопределяет `dragEnterEvent`,
  `dragMoveEvent` и `dropEvent`, принимая перетаскивание только из соседней
  таблицы задач и только при наличии этого MIME-типа. Раньше drag не начинался:
  базовый `QAbstractItemView` отклонял данные, так как модель не умела
  `canDropMimeData`.
- **Геометрия (`gui/task_distribution_widget.py`):** кнопки `>>>`/`<<<` вынесены
  в фиксированную панель шириной 52 px внутри центральной области
  (`middle + buttons`); `QSplitter` стал трёхпанельным (`tree | center | right`),
  все панели несворачиваемые, у средней и правой задана минимальная ширина.
  При изменении ширины средней колонки кнопки остаются прижатыми к правой
  таблице, а правая таблица меняет ширину вместе с центральной панелью.
- **Период и дерево (`services/task_distribution_service.py`):**
  `build_tree(period)` строит дерево для выбранного финансового года и
  сбрасывает кэш при смене периода; membership сотрудника в рабочей группе
  определяется пересечением `[workgroup_start_date, workgroup_end_date]` с
  `[period.start, period.end]` (а не только датой `today`). Вкладка перестраивает
  дерево при смене периода и после создания/редактирования/удаления/импорта задач.
  Неактивные сотрудники и упразднённые группы по-прежнему показываются серыми:
  на них могут оставаться назначения, поэтому скрывать их нельзя.

### Проверка
- `pytest tests` — **162 passed** (добавлены тесты membership по периоду,
  MIME-данных drag&drop и фиксированной ширины панели кнопок).
- `scripts_dev/test_migration_task_distribution.py` — upgrade/downgrade/повторный
  upgrade OK.
- `python -m py_compile` изменённых модулей; импорт `gui.application` — OK.

### Отложено
- Автоматический тест именно Qt-перетаскивания (покрыты MIME-данные и логика
  приёма; сам жест мышью проверяется вручную).

---

## 2026-11-13 — Слияние main и test, исправление регрессий

### Что сделано
- `git fetch origin --prune`: `origin/main` = 62174bc (PR #6 from test),
  `origin/test` = 3153545. Локальный `main` был на a638288, `test` — на 3a57502.
- `git checkout main`, `git pull --ff-only origin main` — fast-forward до 62174bc.
  `git merge test` сообщил «Already up to date»: main уже содержал test через PR #6.
  Локальный `test` обновлён до `origin/test` (3153545).
- После слияния полный прогон тестов выявил несовместимости с изменениями main
  (IntEnum, удаление `VersionedMixin`/`TimestampMixin`, `TaskEntityLink`,
  `task_employee_association`).

### Исправления
- **`orm/models.py`:** `AddedTask` больше не наследует удалённый `VersionedMixin`
  (`class AddedTask(Base, ChangeTrackedMixin)`); восстановлены
  `task_employee_association`, `Employee.tasks`, `ScientificTask.employees` —
  на них опираются панель ОШС и статистика main. Восстановлен `TaskEntityLink`
  (`task_entity_links`) для совместимости с `orm/__init__.py` и тестами main.
- **`alembic/versions/f3b1c9d2e4a7_task_distribution.py`:** `down_revision`
  переведён с c4a8f1b2d3e4 на b1d2e3f4a5c6 (устранён второй head); убраны
  колонки `row_version/created_at/updated_at` и удаление `task_employees`.
  Единственный head — `f3b1c9d2e4a7`.
- **`services/reference_service.py`:** `ScientificTaskService._as_task_type`
  принимает `ScientificTaskType`, int, код пакета, метку или имя; тип хранится
  как IntEnum.
- **`gui/task_dialog.py`:** комбобокс типа заполняется `int(member)` и
  восстанавливает значение через `findData(int(task.type))`.
- **`tests/test_task_distribution.py`:** фикстура создаёт отдел/сотрудника/
  группу с явными `branch_id`/`department_id` и промежуточными `flush()`
  (change tracking не видит FK, выставленный через связь до flush).
- **`scripts_dev/test_migration_task_distribution.py`:** проверяет ревизию
  `b1d2e3f4a5c6`, отсутствие `row_version` и сохранение `task_employees`.

### Проверка
- `pytest tests -q` — **253 passed** (62,73 с).
- `scripts_dev/test_migration_task_distribution.py` — upgrade/downgrade/повторный
  upgrade OK; `alembic heads` — единственный `f3b1c9d2e4a7`.
- `py_compile` изменённых модулей; импорт `gui.application` — OK.

---

## 2026-11-13 — Проверка запуска и обновление рабочей БД

### Симптом
Запуск `main.py` завершался с кодом 1:
- `sqlite3.OperationalError: no such column: changes.exported_at`;
- `no such column: scientific_materials.permit_date`;
- `validate_enum_codes`: `ValueError: invalid literal for int() with base 10: 'ТДОК'`.

### Причина
База `D:/Projects/Obfuscation/123.db` была создана старой версией через
`create_all` и не имела таблицы `alembic_version`; схема отставала от моделей
на несколько миграций (строковые коды перечислений, отсутствующие колонки).

### Что сделано
- Резервная копия: `D:/Projects/Obfuscation/123.db.bak-2026-11-13`.
- Добавлен `scripts_dev/upgrade_real_db.py`: добавляет недостающие колонки
  (`changes.operation_type/exported_at`, `scientific_materials.permit_date`,
  `evaluations.date`), переносит маркер `__DELETED__` в `operation_type=2`,
  переводит строковые коды перечислений в целые числа и ставит ревизию
  `f3b1c9d2e4a7` (единственный head).
- Рабочая БД обновлена; `alembic_version` = `f3b1c9d2e4a7`.

### Проверка
- `main.py` под `QT_QPA_PLATFORM=offscreen` запускается без ошибок в логе.
- Дымовая проверка `MainWindow`: 4 вкладки, материалы — 40 (фильтр по
  филиалу BR-001), телеграммы — 20, периодов задач — 2, корень дерева — 1.
- В `Logs/app.log` после обновления нет `ERROR`/`WARNING`.
- Предупреждения Qt об отсутствии каталога шрифтов относятся к offscreen-режиму
  и на работу приложения не влияют.

### Отложено
- В БД остались старые колонки `row_version`, `created_at`, `updated_at`,
  `country_id` — модели их не используют, на работу не влияют.
- Полная история миграций на этой БД не проигрывалась (схема собрана старой
  версией); для новых баз использовать `alembic upgrade head`.



## 2026-11-11 — Удаление миксинов VersionedMixin и TimestampMixin

### Изменения
- **Модель (`orm/base.py`):** удалены классы `VersionedMixin` (`row_version`) и `TimestampMixin` (`created_at`/`updated_at`); убраны неиспользуемые импорты (`Column`, `DateTime`, `Integer`, `timezone`).
- **Модель (`orm/models.py`):** наследование обоих миксинов убрано у всех 18 классов (у `Change` остаётся собственное `changed_at`).
- **`orm/__init__.py`:** убран реэкспорт миксинов.
- **Миграция `alembic/versions/d5b9e3c4f6a7_drop_service_columns.py`:** удаляет `row_version` из 17 таблиц и `created_at`/`updated_at` из `changes` (batch-режим, работает и на SQLite, и на PostgreSQL). Удалённые колонки — чисто служебные, бизнес-данные не затронуты, перенос не требуется; downgrade возвращает колонки (значения не восстанавливаются, с явным комментарием).
- **Сервисы:** `change_tracking.py` и `import_service.py` — `_SERVICE_FIELDS` сокращён до `{"change_id"}`; из `import_service.py` удалён бамп `row_version` при обновлении сущности.
- **Тесты:** `tests/test_entity_labels.py` — `SERVICE_FIELDS` сокращён до `{"change_id"}`. `scripts_dev/test_migration_tasks_nn.py` не менялся: вставки идут в схему ревизии `b7c4d2f0a1e9`, где `row_version` ещё существует.
- **Документация:** README (убран пункт про оптимистичный контроль версий, добавлен про `change_id`), AGENTS.md (инвариант 2: наследовать только `ChangeTrackedMixin`).

### Проверка
- `scripts_dev/test_migration_tasks_nn.py` — upgrade/downgrade новой миграции на SQLite проходят.
- `pytest`: **156/156 passed**; импорт GUI (`internal_correspondence.gui.application`) — OK.

---

## 2026-11-11 — Change: тип операции, дата экспорта, дельта-обмен и срок хранения

### Изменения
- **Модель (`orm/models.py`):** у `Change` новые поля — `operation_type` (SmallInteger, 0 — создание, 1 — изменение, 2 — удаление; `IntEnum ChangeOperation` в `core/constants.py`) и `exported_at` (DateTime, nullable — дата записи в экспортный файл). Миксин-маркер `DELETION_MARKER` удалён из констант, трекинга и экспорта.
- **Миграция `alembic/versions/e6ca04d5a7b8_change_operation_type.py`:** добавляет обе колонки; переносит данные: записи с `__DELETED__` в `changed_fields` → `operation_type=2` с очищенным множеством полей (LIKE с ESCAPE, работает на SQLite и PostgreSQL), downgrade возвращает маркер. Проверена в обе стороны, включая перенос данных.
- **Трекинг (`services/change_tracking.py`):** переработан `_mark_change` → `_mark_created`/`_mark_updated`/`_mark_deleted`.
  - Создание: ищется Change по паре (entity_name, entity_pk) — при пересоздании сущности старая запись перезаписывается как создание (id сохраняется); `changed_fields` = поля, которым заданы значения.
  - Изменение: если `exported_at` пустое — объединение множеств полей; иначе — `operation_type=1`, только поля после последнего экспорта, `exported_at` сбрасывается.
  - Удаление: если создание не экспортировалось (`operation_type=0` и `exported_at` пустое) — запись Change удаляется; иначе — `operation_type=2`, поля очищаются. Отклонение от исходной формулировки: созданное, но УЖЕ экспортированное удаляется не молча, а фиксируется как удаление — иначе приёмник никогда не узнал бы о пропавшей сущности.
  - После экспорта `change_id` у сущности сбрасывается (подсветка в таблицах работает без изменений), запись Change ищется по паре (сущность, ключ).
- **Экспорт (`importexport/export_service.py`):** выгружает только Change с пустым `exported_at`; удаления определяются по `operation_type`; после упаковки архива записи помечаются `exported_at` (не удаляются), затем вызывается чистка по сроку хранения. Новый параметр конструктора `retention_days`.
- **Срок хранения:** `purge_expired_changes(session, retention_days)` в `change_tracking.py` удаляет только экспортированные записи старше срока (неэкспортированные не трогает; <= 0 — бессрочно). Настройка `changes_retention_days` в `settings.ini` (default 30, диалог настроек, спинбокс со значением «бессрочно»); чистка — при старте приложения и после экспорта. Строки диалога — через `AppStrings` (секция `strings` пакета регенерирована скриптом).
- **Пакет (`core/domain_pack.default.json`):** у сущности Change добавлены метки полей `operation_type` («Тип операции») и `exported_at` («Дата экспорта»).
- **README:** архитектурные решения (дельта-обмен, retention), структура данных «Изменение», раздел особенностей.

### Проверка
- Новые тесты: жизненный цикл Change (создание/объединение/удаление до экспорта, дельта после экспорта, удаление после экспорта, пересоздание, purge), экспорт/импорт дельты и удалений.
- `pytest`: **165/165 passed**; импорт GUI и диалога настроек — OK; миграция — upgrade/downgrade на SQLite с проверкой переноса маркера.

### Backlog
- **Запрос недостающих данных приёмной стороной.** Дельта-обмен делает архивы зависимыми от цепочки: потерянный архив = потерянные изменения. Идея: служебный тип сообщения в том же ZIP (например, `{"Request": {"Entity": pk}}` или запрос полного снимка сущности по известному ключу); приёмник формирует запрос — отправитель отвечает полными данными. Потребует дополнения формата обмена (обратная совместимость: неизвестные ключи при импорте игнорируются).

---

## 2026-11-11 — Перечисления как IntEnum: хранение целыми числами

### Изменения
- **Константы (`core/constants.py`):** MaterialType, EvaluationValue, ScientificTaskType, TelegramType, TelegramReportType, SourceType переведены с str-Enum на IntEnum (значения 0, 1, 2... в прежнем порядке объявления; имена членов = ключи пакета в верхнем регистре). ResearchType удалён (нигде не использовался); секция research_type удалена из пакета `domain_pack.default.json`.
- **Реестр (`core/enum_registry.py`, новый):** PACK_ENUMS (имя перечисления пакета ↔ IntEnum) и хелперы: `pack_enum_key` (число → ключ), `pack_enum_display` (число → краткий код пакета), `pack_enum_choices` (наполнение комбобоксов «метка (код)», deprecated-значения исключаются). Отдельный модуль — чтобы избежать циклического импорта constants ↔ domain_pack.
- **ORM (`orm/base.py`):** TypeDecorator `IntEnumType` — в БД целое (SmallInteger), в Python IntEnum; неизвестные числа отдаются как есть (предупреждение формирует validate_enum_codes).
- **Модель (`orm/models.py`):** колонки scientific_materials.type, telegrams.type, telegrams.report_type, scientific_tasks.type, sources.type, evaluations.value — на IntEnumType с типизацией Mapped[Enum]. EvaluationMixin.evaluation_display показывает краткий код пакета.
- **Миграция `alembic/versions/f7db15e6b8c9_enum_codes_to_int.py`:** 6 колонок VARCHAR → SMALLINT через временную колонку и CASE-маппинг (портабельно SQLite/PostgreSQL); неизвестные коды → NULL (в NOT NULL колонках миграция прервётся с ошибкой — требуется ручная чистка). Downgrade возвращает строковые коды (числа вне диапазона → NULL). Проверена в обе стороны с данными; скрипт `scripts_dev/test_migration_tasks_nn.py` поправлен (невалидный код 'ДК' → 'Т').
- **Сервисы:** `enum_validation` сверяет числа БД с пакетом по ключам (число → IntEnum → ключ); `statistics_service` группирует оценки по значениям IntEnum, метки через пакет; `reference_import` преобразует строковые коды из XLSX в числа (неизвестный тип — строка пропускается с warning).
- **GUI:** комбобоксы типов наполняются через pack_enum_choices (userData — int); findData приводится к int; форматтеры колонок «Тип»/«Тип доклада» в таблицах показывают краткий код пакета; делегат оценок keyed by EvaluationValue.
- **Тесты:** значения type/value в тестах переведены на членов IntEnum; тесты неизвестных/устаревших кодов переписаны под целочисленные значения; новый `tests/test_enum_int_storage.py` (хранение int, экспорт int, отображение, выбор без deprecated).
- **README:** правила совместимости пакета (ключи неизменяемы, коды — краткий текст, БД хранит числа), удалён раздел «Тип научного изыскания», в разделе перечислений — примечание о числовом хранении.

### Проверка
- Миграция: upgrade/downgrade на SQLite с проверкой переноса всех 6 колонок.
- `pytest`: **169/169 passed**; импорт GUI — OK.

### Отложено
- Архивы, созданные прежними версиями (строковые коды в export.json), новой версией не импортируются — принято осознанно (синхронное обновление обеих сторон). При необходимости — добавить конвертацию строк→числа на импорте.

---

## 2026-11-11 — Связь научной задачи с сущностью (TaskEntityLink)

### Изменения
- **Модель (`orm/models.py`):** новый класс `TaskEntityLink` (таблица `task_entity_links`): `id` Integer autoincrement PK, `task_id` FK → scientific_tasks.id (ON DELETE CASCADE), `entity_name` String(100), `entity_pk` String(255); составной индекс (entity_name, entity_pk). Закладка под механизм распределения научных задач — change tracking и обмен подключать вместе с механизмом (пока сущность не редактируется через UI).
- **Миграция `alembic/versions/f8cc27a9d0e1_task_entity_links.py`:** create/drop таблицы и индекса. Проверена в обе стороны на SQLite (скрипт test_migration_tasks_nn.py).
- **`orm/__init__.py`:** реэкспорт TaskEntityLink.
- **Пакет (`domain_pack.default.json`):** секция entities → метки сущности и полей (id, task_id, entity_name, entity_pk).
- **README:** раздел «Связь задачи с сущностью» в структуре данных.
- **Тесты (`tests/test_orm_and_changes.py`):** test_task_entity_link — сохранение/чтение связи и каскадное удаление при удалении задачи (FK-pragma SQLite включена в DatabaseManager).

### Проверка
- `pytest`: **170/170 passed**; импорт GUI — OK.

---

## 2026-11-11 — Связь документов со странами 1-N -> N-N

### Изменения
- **Модель (`orm/models.py`):** у ScientificMaterial и Telegram убраны `country_id`/`country`; добавлены ассоциативные таблицы `material_countries` и `telegram_countries` и связи `countries` (владелец — документ, первая колонка ассоциативной таблицы). У Country обратные связи переведены на secondary. Change-tracking и экспорт/импорт работают обобщённо — отдельных правок не потребовалось.
- **Миграция `alembic/versions/a9de48b1c2f3_countries_many_to_many.py`:** создаёт ассоциативные таблицы, переносит существующие country_id, удаляет колонки; downgrade возвращает колонки с одной (минимальной по коду) страной на документ. Проверена в обе стороны на SQLite с данными.
- **Интерфейс (`gui/document_dialogs.py`):** комбобокс «Страна» заменён на `CountrySelectWidget` — список стран с чекбоксами (в обоих диалогах); get_data отдаёт «countries».
- **Пакет (`domain_pack.default.json`):** у ScientificMaterial и Telegram поле country_id заменено на countries («Страны»).
- **seed_data.py:** документам назначается случайная страна через связь countries.
- **README:** описания полей «Страны» материала и телеграммы — отношение n-n.

### Проверка
- Новые тесты в test_export_import.py: N-N стран трекается в Change и экспортируется; импорт восстанавливает связь.
- `pytest`: **172/172 passed**; импорт GUI — OK.

---

## 2026-11-11 — Переработка формы ОШС (по README)

### Изменения
- `gui/oshm_dialog.py` — полная переработка `OSHMDialog`:
  - выпадающий список филиалов: головной офис видит все филиалы (режим просмотра, read_only), филиал — только свой (список заблокирован); сигнатура конструктора: `(session, branch_id, role)`;
  - два дерева одно под другим (вертикальный сплиттер): «Штатная структура» (филиал → отделы → сотрудники, без рабочих групп) и «Рабочие группы» (филиал → отделы → группы → состав групп);
  - кнопки «+»/«−» (добавление с учётом выбранного узла, для отдела — всплывающее меню группа/сотрудник; «−» — скрыть/показать выбранное);
  - множественный выбор (Shift/Ctrl): групповое скрытие и удаление, текст подтверждения с количеством;
  - drag&drop (`OSHMTreeWidget`, стандартный DnD перехвачен): в дереве структуры сотрудник → отдел = смена отдела; в дереве групп сотрудник → группа = включение в состав; недопустимые цели игнорируются;
  - неактивные элементы выделяются серым; сотрудник сокращённого отдела показывается как «Неактивный (отдел сокращён)»;
  - обработка операций унифицирована через `_apply` (commit/rollback + сообщение).
- `gui/application.py`: `_open_oshm` передаёт роль в диалог; удалён мёртвый `_select_branch` (выбор филиала теперь в самом диалоге).
- `gui/employee_picker.py`: в выборе сотрудников только действующие сотрудники действующих отделов (скрытие отдела скрывает его сотрудников); убран суффикс «(неактивен)».
- `utils/string_resources.py`: новые ключи `oshm_tree_structure`, `oshm_tree_workgroups`, `status_inactive_via_dept`, `msg_delete_elements_confirm`; пакет регенерирован (111 ключей).
- README: раздел «Изменение ОШС» приведён к новой форме (список филиалов, два дерева, drag&drop на отдел и на группу).

### Проверка
- Новый `tests/test_oshm_dialog.py` (10 тестов): видимость филиалов по ролям, структура двух деревьев, отображение неактивных, скрытие, drag&drop (отдел/группа/недопустимая цель), групповое удаление, фильтрация выбора сотрудников.
- `pytest`: **161/161 passed**.


---

## 2026-11-11 — ОШС, итерация 2: деревья от роли, без выбора филиала и без статуса

### Изменения
- `gui/oshm_dialog.py` — диалог перестроен по уточнённым требованиям:
  - выпадающий список филиалов убран; деревья строятся от элемента, от которого открыто приложение: филиал — корень его собственный узел, головной офис — корень «Головной офис» (`role_head_office`) со всеми филиалами внутри (режим просмотра, read_only);
  - колонка «Статус» убрана: деревья одноколоночные; неактивные элементы по-прежнему серым (`INACTIVE_COLOR`), сотрудник сокращённого отдела — тоже;
  - по умолчанию развёрнут только корневой узел, остальные уровни раскрываются щелчком («выпадают»);
  - кнопки «+»/«−», мультивыбор, контекстное меню и drag&drop переподчинения — без изменений.
- `tests/test_oshm_dialog.py` — обновлены проверки ролей (корень «Головной офис» с двумя филиалами / корень-филиал без чужих узлов) и подсветки неактивных (сравнение с `QColor(150,150,150)` вместо текста статуса).
- README: раздел «Изменение ОШС» — убраны упоминания списка филиалов и статуса; описано построение деревьев от роли и раскрытие узлов по щелчку.
- Пакет предметной области регенерирован (111 ключей, изменений состава нет — `role_head_office` уже существовал).

### Проверка
- `pytest tests/test_oshm_dialog.py`: 10/10 passed.
- `pytest tests`: **161/161 passed**.

### Планируется
- Визуальная приёмка пользователем: свёрнутость по умолчанию, отсутствие статуса, вид от головного офиса.


---

## 2026-11-11 — ОШС, итерация 3: головной офис редактирует структуру, но не людей

### Изменения
- `gui/oshm_dialog.py`: снят режим read_only для головного офиса; вместо него — `can_edit_people` (False для ГО):
  - ГО может добавлять/изменять/скрывать/удалять отделы и рабочие группы в любом филиале;
  - ГО не может добавлять/изменять/скрывать/удалять сотрудников и перетаскивать их (drag&drop): пункты меню скрыты, обработчики (`_add_employee`, `_edit_item`, `_toggle_selected`, `_delete_selected`, `_on_nodes_dropped`) игнорируют сотрудников, узлы сотрудников не перетаскиваемы;
  - добавление отдела от ГО: филиал берётся из выбранного узла филиала (`_branch_id_for_add`); если выбран корень «Головной офис» — подсказка «Выберите филиал, в который нужно добавить отдел» (новый ключ `oshm_select_branch_first`, пакет регенерирован — 112 ключей);
  - контекстное меню и кнопки «+»/«−» активны для обеих ролей, состав пунктов зависит от роли.
- `tests/test_oshm_dialog.py`: +3 теста (ГО не трогает сотрудников; ГО скрывает структуру; выбор филиала для добавления отдела), проверки ролей переведены на `can_edit_people`.
- README: раздел «Изменение ОШС» — ГО редактирует структуру, но не сотрудников.

### Проверка
- `pytest tests`: **164/164 passed**.


---

## 2026-11-11 — ОШС, итерация 4: панель сведений об элементе

### Изменения
- Новый модуль `gui/oshm_details_panel.py`:
  - `ElementDetailsPanel` — выдвижная правая панель диалога ОШС (двойной щелчок по элементу дерева): все данные элемента (метки полей — через `field_label`), для сотрудника — таблица назначенных задач (код, наименование, начало, окончание) с кнопками «+»/«−» (назначить/снять, N-N `task_employee_association`);
  - `TaskPickerDialog` — выбор ещё не назначенных задач (мультивыбор);
  - кнопки панели: «Скрыть» (закрывает панель), «Изменить» (окно редактирования элемента через сигнал `edit_requested`), «Статистика» (заглушка);
  - права: ГО видит данные сотрудника, но «Изменить» и кнопки задач недоступны; для филиала и корня ГО «Изменить» недоступно (ведутся в справочниках).
- `gui/oshm_dialog.py`: двойной щелчок переведён с редактирования на панель сведений; `_edit_item` разделён на `_edit_item`/`_edit_node`; панель в горизонтальном сплиттере справа от деревьев, скрыта по умолчанию; `_refresh_details_panel` после перестройки деревьев (панель скрывается, если элемент удалён).
- `utils/string_resources.py`: новые ключи `oshm_tasks_section`, `picker_tasks_title`, `button_hide`, `button_statistics`, `value_yes`, `value_no`; пакет регенерирован (118 ключей).
- README: описание панели сведений в разделе «Изменение ОШС».

### Проверка
- `tests/test_oshm_dialog.py`: +6 тестов (панель сотрудника с задачами, панель отдела без задач, ограничения ГО, кнопка «Скрыть», снятие назначения, скрытие панели после удаления элемента).
- `pytest tests`: **170/170 passed**.

### Планируется
- Кнопка «Статистика» на панели — реализовать переход к статистике по элементу (пока заглушка).


### Принятое решение (2026-11-11)
- Назначение научных задач сотрудникам в форме ОШС — прерогатива **филиала**: у головного офиса кнопки «+»/«−» в панели задач сотрудника намеренно неактивны. Это часть правила «ГО редактирует всё, кроме людей».


---

## 2026-11-12 — Доработка вкладки «Статистика»

### Изменения
- `reports/statistics_service.py`:
  - новый критерий `CRITERION_BRANCH` («Филиалы») — сравнение филиалов для головного офиса;
  - подкатегории (`StatisticsQuery.subcriterion`, карта `SUBCRITERIA`): строки элементов группируются по значениям критерия с итогами групп; допустимые пары — филиал→{отдел, сотрудник}, отдел→{группа, сотрудник}, группа→сотрудник; элемент засчитывается в группу, только если документ причастен к группе; итог группы = сумма её элементов; общие итоги считаются по строкам верхнего уровня;
  - `StatisticsRow` получила `key` и `is_group`; `StatisticsResult` — поле `summary`;
  - для критерия «Полученные оценки» считается средний балл по весам значений пакета (`enum_weight`).
- `gui/statistics_widget.py` (переписан):
  - комбобокс подкатегории (виден только у критериев с подкатегориями); критерий «Филиалы» скрыт у филиала;
  - переключатель типа графика: столбцы (с подписями значений) / линии (динамика) / круговая (доли по итогам периода);
  - лучшее/худшее значения критерия подсвечиваются (зелёный/красный, полупрозрачно); при группировке сравниваются итоги групп;
  - строка `summary` (средний балл) под подписью периода;
  - групповые строки — жирным, элементы — с отступом; ключ строки сохраняется в данных ячейки;
  - публичный `show_element(node)` — установка критерия и выделение строки элемента (для перехода из ОШС).
- `gui/oshm_details_panel.py`: кнопка «Статистика» теперь испускает сигнал `statistics_requested(node)` (была заглушкой).
- `gui/application.py`: сигнал панели ОШС закрывает диалог и открывает вкладку статистики с выделенной строкой элемента (`_on_oshm_statistics`).
- `utils/string_resources.py`: ключи `label_subcategory`, `subcategory_none`, `label_chart_type`, `chart_type_bars/lines/pie`, `chart_by_totals`, `stats_avg_score`; пакет регенерирован (126 ключей).
- README: раздел «Статистические подсчеты» в «Использовании»; описание кнопки «Статистика» панели ОШС.

### Проверка
- `tests/test_statistics_service.py`: +7 тестов (критерий «Филиалы», группировка отдел→сотрудники и группа→сотрудники, средний балл, видимость критерия по ролям, подкатегория и типы графиков в виджете, выбор строки через `show_element`).
- `pytest tests`: **177/177 passed**; импорт GUI проверен.

### Отложено
- Выгрузка результатов в отчёт по шаблону (подсистема отчётов) и экспорт таблицы в Excel.
- SQL-фильтрация документов вместо загрузки в память; расчёт в потоке с прогресс-баром (README §539).


### Дополнение (2026-11-12, вечер) — статистика: компоновка и подкатегории
- Селектор типа графика перенесён из строки действий в панель над самим графиком.
- Соотношение «таблица ↔ график»: вертикальный `QSlider` заменён на привычный перетаскиваемый `QSplitter` (`content_splitter`).
- Новые подкатегории: «Филиалы → Рабочие группы», «Научные задачи → Сотрудники» (по назначениям N-N); `_parent_link` заменён на `_parent_links` с поддержкой нескольких родителей (сотрудник с несколькими задачами засчитывается в каждую свою задачу).
- График при выбранной подкатегории: выводятся элементы групп (без строк-итогов) оттенками цвета своей группы (`_member_color`: чередование светлее/темнее с нарастающим шагом), во всех трёх типах диаграмм.
- Тесты: `test_grouped_by_task_and_employees`, `test_widget_grouped_chart_shades`; старый тест виджета переведён со слайдера на сплиттер. `pytest tests`: **179/179 passed**.


### Дополнение 2 (2026-11-12, вечер) — статистика: экспорт в Excel и компоновка
- Новый модуль `reports/statistics_export.py`: `export_statistics()` сохраняет результат в xlsx (заголовок, период, средний балл, таблица с итогами; группы жирным, элементы с отступом; изображение графика под таблицей).
- `gui/statistics_widget.py`: кнопка «Экспорт в Excel» (снимок графика через `chart_view.grab()` во временный PNG); заголовок первой колонки включает подкатегорию («Отделы / Сотрудники»).
- Компоновка: заголовок/период/средний балл объединены в одну строку, уменьшен вертикальный интервал (`setSpacing(4)`), пустая сводка скрывается — убран лишний зазор между панелью параметров и таблицей/графиком.
- Новые строки: `button_export_excel`, `dialog_save_excel`, `file_filter_excel`; пакет регенерирован (129 ключей).
- Тесты: `test_excel_export` (структура xlsx через openpyxl). `pytest tests`: **180/180 passed**.


### Слияние с main (2026-11-12, вечер) — PR #3 «Изменение схемы данных»
- Подтянут `origin/main` (b7ecac8) в `alex_develop`; stash с незакоммиченными правками возвращён, конфликты разрешены (`WORK_NOTES.md` — обе истории; `settings.ini` — версия main с новыми ключами; `statistics_service.py` — объединение импортов и адаптация `_evaluation_summary` под int-значения перечислений).
- Ключевые изменения main: перечисления хранятся как int (`core/constants.py` IntEnum + `core/enum_registry.py`, коды отображения через `pack_enum_display`); `VersionedMixin`/`TimestampMixin` удалены (только `ChangeTrackedMixin`); у `Change` появились `operation_type` и `exported_at`, чистка по `changes_retention_days` (по умолчанию 30 дней); миграции `a9de48b1c2f3` (страны N-N), `f8cc27a9d0e1` (связи задача-сущность), `d5b9e3c4f6a7` (удаление служебных колонок), `f7db15e6b8c9` (перечисления в int).
- Адаптация нашего кода: в `tests/test_oshm_dialog.py` фикстура создаёт задачи с `ScientificTaskType.MAIN/ADDITIONAL` вместо строковых типов; `_evaluation_summary` берёт код через `pack_enum_display` и вес через `enum_weight` по строковому коду.
- Stash-запись удалена. `pytest tests`: **201/201 passed** (наши 180 + новые тесты main: `test_window_state.py`, `test_enum_int_storage.py` и др.).
- Изменения пока не закоммичены: в рабочем дереве наши правки ОШС/статистики поверх свежего main.


## 2026-11-12 — Этап 0 плана my_plan.md: подготовка схемы БД к новым диалогам редактирования

### Изменения
- **Модель (`orm/models.py`):**
  - `ScientificMaterial.permit_date` — новая колонка `Date`, nullable («Дата разрешительного документа», пара к `permit_number`).
  - `ReportAddress.report_date` — теперь nullable: пустая дата = «ещё не доложено» (будет суффикс «+» в интерфейсе).
  - `Evaluation.date` — новая колонка `Date`, NOT NULL («Дата выставления»); `evaluation_list_id` стал nullable (оценка может быть ручной, без списка).
  - `EvaluationMixin.latest_evaluation` — «последняя» оценка определяется по `Evaluation.date` (раньше — по дате списка); фильтр «только со списком» снят.
- **Миграция `alembic/versions/b1d2e3f4a5c6_editing_dialogs_schema.py`:** все 4 изменения в одной миграции; перенос данных — `evaluations.date` заполняется из `evaluation_lists.date`. Downgrade с явными потерями (задокументированы в docstring): оценки без списка удаляются вместе со связями, пустые даты доклада заполняются текущей датой. Проверена в обе стороны на SQLite новым скриптом `scripts_dev/test_migration_editing_stage.py` (upgrade → перенос → downgrade → повторный upgrade).
- **Пакет (`domain_pack.default.json`):** в секции `entities` добавлены поля `permit_date` («Дата разрешительного документа») у ScientificMaterial и `date` («Дата выставления») у Evaluation.
- **README:** описания полей «Дата разрешительного документа», «Дата доклада» (про пустое значение), «Дата выставления» и необязательность «Список оценок».
- **Тесты/данные:** `Evaluation(...)` в `seed_data.py`, `test_evaluation_display.py`, `test_statistics_service.py` — обязательный `date`; новые тесты: ручная оценка без списка, «последняя» по дате выставления (а не списка), пустая `report_date`.
- План в `current_plans/my_plan.md` уточнён по итогам обсуждения (видимость полей по типу через семантические ключи IntEnum, стили меток, валидация по «Сохранить», хранение фильтров и др.).

### Проверка
- `scripts_dev/test_migration_editing_stage.py` — upgrade/downgrade/повторный upgrade на SQLite, включая проверку переноса `evaluations.date`.
- `pytest`: **175/175 passed**; импорт GUI — OK.

### Следующий шаг
- Этап 1: элементы редактирования и базовый диалог (см. `current_plans/my_plan.md`).

---

## 2026-11-12 — Этап 1 плана my_plan.md: элементы и диалоги редактирования

### Изменения
- **Новое: `gui/edit_elements.py`** — элементы редактирования полей сущностей:
  - Базовый `EditElement` (метка с выделением: обязательные — жирным со «*» красным, уникальные — подчёркнутым; `validate()`/`load_value()`/`collect_data()`);
  - простые элементы (строка, текст, целое, float, дата, время, дата-время, bool, перечисление пакета);
  - `FkComboEditElement` (1→N: QComboBox, нулевое значение сверху, QCompleter при >10 вариантов);
  - `ManyToManyEditElement` (N→N: QListWidget + «+/−», диалог выбора с мультивыбором и фильтрацией, без уже добавленных);
  - `ReportAddressesEditElement` (расширенная таблица связности: QTableWidget «Руководитель (ИД+)/Дата доклада», дата может быть пустой — «ещё не доложено»);
  - `NumberDateEditElement` (пара «номер и дата» в одной строке; дата активна при заполненном номере);
  - фабрика `create_element()` по типу колонки/связи.
- **Новое: `gui/entity_edit_dialog.py`** — базовый диалог редактирования сущности: сетка «метка — редактор», «Сохранить»/«Отмена», кнопка «Больше» для доп. полей (обязательные незаполненные показываются и свёрнутыми); валидация при сохранении обходом элементов сверху вниз (QMessageBox + фокус на проблемный); проверка дублей по UniqueConstraint до записи в БД; автоматическая обработка `branch_id` (филиал: фиксирован, редактор скрыт; головной офис: редактируемый combobox для ручного ввода при сбое обмена); правила условной видимости полей (драйвер + предикаты).
- **`gui/document_dialogs.py`** — переписан на базовом диалоге: наборы полей по ролям из плана; видимость «Серийный номер»/«Год выпуска»/«Номер и даты разрешительного» для `PRODUCT_SAMPLE`/`TECHNICAL_DOCUMENT`, «Стоимость» — только `PRODUCT_SAMPLE` (семантические ключи IntEnum); «Исходящий номер и дата» — обязательные; выбор сотрудников ограничен филиалом (роль филиал). Старые виджеты списков с чекбоксами удалены.
- **`gui/reference_dialogs.py`** — диалоги справочников стали тонкими обёртками базового диалога (поля строятся по умолчанию из колонок модели).
- **`orm/labels.py`** — новый хелпер `field_unique()` (из UniqueConstraint/unique=True).
- **`orm/models.py`** — у связей `employees` материала и телеграммы метка «Сотрудники» (info + зеркало в пакете).
- **`gui/document_list_widget.py`** — виджет файлов из диалогов исключён (переезд в док-виджет — Этап 3); создание/обновление через `service.create/update`; роль пробрасывается в диалоги. `application.py` передаёт роль вкладкам.
- **`utils/string_resources.py`** — новые ключи (кнопки «Больше»/«Меньше», сообщения валидации, дубли, пара «номер и дата»); секция `strings` пакета регенерирована (121 ключ).

### Проверка
- Новый `tests/test_edit_dialog.py` (14 тестов, QT_QPA_PLATFORM=offscreen): фабрика элементов, пары «номер и дата», адресация (сохранение идентичности, «+», формат «L1, L2+»), диалог справочника (дефолтные поля, FK-комбобокс, дубль по уникальному ограничению), видимость полей материала по типу, роли, «Больше».
- `pytest`: **189/189 passed**; импорт GUI — OK.

### Отложено
- Прикрепление файлов недоступно до Этапа 3 (док-виджет) — осознанно.

---

## 2026-11-12 — Этап 2 плана my_plan.md: отображение таблиц документов

### Изменения
- **`gui/table_model.py`:** `SqlAlchemyTableModel` — новый параметр `branch_id` (ограничение выборки и счётчика филиалом; работает и в DB-пагинации, и в памяти); новый подкласс `DocumentsTableModel` — выделяет цветом строки без входящего номера (приоритет у цвета неэкспортированных изменений).
- **`gui/theme.py`:** у темы новый цвет `no_incoming_row` (светлая `#E3EDF7`, тёмная `#2F3B4C` — мягче `modified_row`).
- **`gui/application.py`:** колонки таблиц стали ролевыми — `material_columns(role)`/`telegram_columns(role)` (константы MATERIAL_COLUMNS/TELEGRAM_COLUMNS сохранены как вариант для роли «филиал»); порядок по плану: филиал/отделы/сотрудники в зависимости от роли; новые форматтеры: страны через запятую, адресация доклада («ИД+» через запятую); заголовки по-прежнему из меток info (краткая метка).
- **`gui/document_list_widget.py`:** используется `DocumentsTableModel`; для роли «филиал» выборка ограничена его строками.
- Примечание: фильтрация по колонкам связей (страны, адресация) работает по строковому представлению списка — осознанное ограничение.

### Проверка
- Новый `tests/test_document_table_model.py` (3 теста): фильтр филиала, выделение строк без входящего номера, приоритет цвета изменённых строк.
- `pytest`: **192/192 passed**; импорт GUI — OK.

---

## 2026-11-12 — Этап 3 плана my_plan.md: UX (видимость записи, фильтры, файлы, оценки)

### Изменения
- **Видимость созданной (изменённой) записи** (`gui/table_model.py`, `gui/document_list_widget.py`): `SqlAlchemyTableModel.page_of(pk)` (страница записи с учётом сортировки/фильтров/филиала; фильтрация в памяти выделена в `_filtered_items`) и `row_of(pk)`; `DocumentListWidget.reveal_record()` — переход на страницу, выделение и прокрутка; после создания/редактирования запись выделяется автоматически; если фильтры её скрывают — QMessageBox без снятия фильтров.
- **Фильтры** (`gui/filter_dialog.py`, `gui/filter_model.py`, `core/settings.py`, `application.py`): строки условий — QFrame(QFrame.Box), «×» выровнен по центру строки, двойной щелчок открывает диалог изменения (`AddFilterDialog` умеет предзаполнение); сериализация `serialize_filters`/`deserialize_filters` (JSON, валидация колонок/операторов, мусор отбрасывается); два набора (`material_filters`/`telegram_filters` в settings.ini) хранятся раздельно, сохраняются при закрытии, восстанавливаются при открытии; сброс фильтров очищает сохранённое; строки фильтров выведены в `AppStrings` (секция `strings` регенерирована).
- **Файлы — док-виджет** (`gui/attached_files_widget.py` переписан, новое `services/file_service.py`, `services/document_service.py`): `AttachedFilesWidget` — QDockWidget, привязан к текущей записи активной вкладки (сигнал `DocumentListWidget.currentDocumentChanged`, синхронизация в MainWindow); заголовок «Файлы к научному материалу/телеграмме № … от …»; кнопки «+/−» справа от списка, по верхнему краю; копирование в отдельном потоке (`CopyFilesWorker` + QThread) с QProgressDialog и отменой; сначала копирование, затем привязка в БД; файлы внутри хранилища — только связь; конфликты имён — вопрос «Заменить / Новое имя / Пропустить» (имена вида file(1).doc); drag&drop из проводника и наружу (mimeData с URL файлов); двойной щелчок — открытие средствами ОС; контекстное меню: «Переименовать» (несколько — с подтверждением), «Расположение файла» (explorer /select на Windows, иначе открытие папки); открепление удаляет неразделённые файлы с диска и пустые папки вплоть до корневой типа документа (`cleanup_empty_dirs` с защитой от выхода за пределы дерева).
- **Ручные оценки** (`gui/evaluation_dialog.py`, `gui/document_list_widget.py`): контекстное меню таблицы «Выставить оценку» для выделенных строк; диалог с комбобоксом значения и датой; одна Evaluation (без списка, `date` из диалога) привязывается ко всем выделенным записям.
- План `current_plans/my_plan.md` отмечен выполненным.

### Проверка
- Новые/переписанные тесты: `test_filters_persistence.py` (4), `test_attached_files_widget.py` (10: примитивы, привязка/отвязка, разделённые файлы, док, поток), `test_evaluation_assign.py` (2).
- `pytest`: **207/207 passed**; импорт GUI — OK.

### Замечания
- Миграцию `b1d2e3f4a5c6` к рабочей БД применять через `alembic upgrade head` (файл 123.db вне проекта — не трогал).
- README раздел «Прикрепление файлов» описывал док-виджет как в ТЗ — теперь реализация совпала.

---

## 2026-11-12 — Доработка диалога настроек (по запросу пользователя)

### Изменения
- **`gui/settings_dialog.py`** (переписан):
  - Поля подключения PostgreSQL («Хост», «Порт», «БД», «Пользователь», «Пароль») скрываются при выборе SQLite и показываются при выборе PostgreSQL; поле «Файл» SQLite — наоборот (раньше поля только блокировались).
  - Поле «Филиал» скрывается при роли «Головной офис» и показывается при роли «Филиал».
  - Редактор филиала — QComboBox с наименованиями из таблицы «Филиалы» (сортировка по наименованию, формат «Индекс — Наименование», userData — идентификатор); текущее значение настройки отображается даже при отсутствии филиала в справочнике. Список читается из сессии приложения (`db_manager`), при его отсутствии — через `load_branches(db_url)`.
  - Строки диалога выведены в `AppStrings` (секция `strings` пакета регенерирована, 167 ключей).
- **`gui/application.py`**: `MainWindow._open_settings` передаёт `db_manager` в диалог настроек.
- **`tests/test_settings_dialog.py`** (новый, 4 теста): видимость полей БД по типу, наполнение комбобокса из таблицы филиалов, видимость поля «Филиал» по роли, сохранение идентификатора из комбобокса.
- **`tests/test_attached_files_widget.py`**: устранена зависимость теста док-виджета от порядка строк списка (порядок выборки из БД не гарантирован) — флакующий тест.

### Проверка
- `pytest`: **211/211 passed** (двойной прогон); импорт GUI — OK.

---

## 2026-11-12 — Исправление падения при открытии диалога настроек

### Причина
`MainWindow._open_settings` передавал в `SettingsDialog` несуществующий атрибут `self._db_manager` (атрибут окна называется `self.db_manager`) — при открытии диалога возникал `AttributeError` и программа завершалась аварийно.

### Изменения
- `gui/application.py`: исправлено на `self.db_manager`.
- `tests/test_settings_dialog.py`: регрессионный тест — конструирование `MainWindow` и открытие диалога настроек из него.

### Проверка
- `pytest`: **212/212 passed**.

---

## 2026-11-12 — Исправление «Расположение файла» (проводник открывал не ту папку)

### Причина
`subprocess.Popen(["explorer", f"/select,{path}"])`: при пути с пробелами subprocess заключает в кавычки весь аргумент целиком (`explorer "/select,C:\путь с пробелами"`), проводник не распознаёт ключ `/select,` и открывает папку по умолчанию (Документы).

### Изменения
- `gui/attached_files_widget.py`: команда формируется хелпером `_explorer_select_command(path)` в канонической форме `explorer /select,"<путь>"` (ключ вне кавычек, путь внутри); при `OSError` — фолбэк на открытие папки через `QDesktopServices`.
- `tests/test_attached_files_widget.py`: тест формирования команды (путь с пробелами).

### Проверка
- `pytest`: **213/213 passed**.

---

## 2026-11-14 — Модуль «Импорт оценок из текстового файла»

### Изменения
- **`internal_correspondence/text_import/`** (новый пакет): конфигурация, ошибки, модели схем/правил/результатов, чтение файла с автоопределением кодировки, разбор fixed/delimited, загрузка и автоопределение схем, декларативный матчер, репозиторий журнала/staging-строк, копирование файла в хранилище и оркестратор `Importer`.
- **`internal_correspondence/services/evaluation_import_writer.py`** (новый): поиск/создание `EvaluationList` по номеру и дате, создание/обновление `Evaluation`, привязка к научному материалу или телеграмме.
- **`internal_correspondence/gui/evaluation_import_dialog.py`** (новый): мастер из четырёх страниц (файл и документ, проверка строк, совпадения, результат), drag&drop, редактор схем; просмотр правил позже убран из меню.
- **`internal_correspondence/gui/application.py`**: пункт меню «Данные» → «Импорт оценок из файла...» (только головной офис), передача `app_dir` в `MainWindow`.
- **`internal_correspondence/utils/string_resources.py`**: строки модуля; секция `strings` пакета регенерирована (324 ключа).
- **`internal_correspondence/core/domain_pack.py`**, **`domain_pack.default.json`**: директория `import` («Импорт»).
- **`alembic/versions/a7d4e2f6b9c1_import_tables.py`** (новый): `import_log`, `import_rows`, представление `import_matches`, индексы; downgrade удаляет объекты.
- **`schemes/evaluation_fixed.json`**, **`schemes/evaluation_delimited.json`**, **`matcher_rules.json`**: примеры схем и правил.
- **`tests/test_text_import.py`**, **`tests/test_evaluation_import_dialog.py`**, **`scripts_dev/test_migration_import_tables.py`** (новые).
- **`requirements.txt`**, **`pyproject.toml`**: зависимость `charset-normalizer`.
- **`README.md`**: описание сущностей журнала/строк импорта, порядка работы и особенностей.

### Проверка
- `pytest tests`: **259 passed**; `tests/test_text_import.py` — 4 passed, `tests/test_evaluation_import_dialog.py` — 2 passed.
- `scripts_dev/test_migration_import_tables.py`: upgrade/downgrade/повторный upgrade — OK.
- `compileall` и импорт GUI — OK.
- Рабочая БД `D:/Projects/Obfuscation/123.db` обновлена до `a7d4e2f6b9c1` (резервная копия `123.db.bak-import-2026-11-14`); проверены `import_log`, `import_rows` и представление `import_matches`.
- Дымовая проверка `MainWindow` (роль головного офиса): 4 вкладки, пункт «Импорт оценок из файла...» присутствует.

### Отложено
- Автоматическая проверка кодировки на реальных файлах заказчика (нужны образцы).
- Открытие журнала импорта из диалога показывает номер записи; отдельный просмотрщик журнала не реализован.
- Импорт выполняется синхронно (по требованию), без фонового потока и прогрессбара.

---

## 2026-11-14 — Предпросмотр импорта оценок по столбцам схемы

### Изменения
- **`internal_correspondence/gui/evaluation_import_dialog.py`**:
  - поле предпросмотра заменено с `QPlainTextEdit` на `QTableWidget`: строки файла
    разбиваются по полям выбранной схемы, заголовки столбцов — имена полей схемы,
    номера строк — в вертикальном заголовке; проблемные строки подсвечены, причина
    показывается в подсказке;
  - предпросмотр обновляется при загрузке файла, смене схемы, проверке и после
    исправления/отклонения строки;
  - удалена кнопка «Загрузить» на первом шаге; загрузка файла выполняется кнопкой
    «Далее» (выбор файла и drag&drop только заполняют путь);
  - кнопка «Далее» активируется сразу после выбора пути к файлу.
- **`internal_correspondence/text_import/parsing.py`**: добавлена `split_fields()` —
  разбиение строки по полям схемы без преобразования типов (для предпросмотра
  проблемных строк).
- **`tests/test_evaluation_import_dialog.py`**: тест предпросмотра — заголовки из схемы,
  подсветка/исправление проблемной строки, отсутствие кнопки «Загрузить».
- **`README.md`**: уточнён порядок работы с предпросмотром.

### Проверка
- `pytest tests`: **260 passed**.

---

## 2026-11-14 — Проверка импорта по реальному файлу и очистка устаревших колонок

### Изменения
- **`internal_correspondence/text_import/matcher.py`**: `_parse_year_month()` принимает
  и `ГГГГММ`, и `ММГГГГ` (в файле заказчика период записан как `112025`).
- **`alembic/versions/c8f1a3d5e7b9_cleanup_legacy_service_columns.py`** (новая миграция):
  идемпотентно удаляет оставшиеся от старых баз `row_version` во всех таблицах и
  `changes.created_at`/`updated_at`. Downgrade возвращает колонки с `DEFAULT 1`
  (прежние значения не восстанавливаются — служебные).
- **`scripts_dev/test_migration_legacy_columns.py`** (новый): имитирует старую схему,
  проверяет upgrade/downgrade/повторный upgrade.
- **`tests/test_text_import.py`**: параметризованный тест на оба порядка года-месяца.
- **`schemes/evaluation_telegram_fixed.json`**, **`matcher_rules.json`**: схема и правило
  для файла заказчика (филиал `BR` + номер, период `ММГГГГ`).
- **`README.md`**: оба формата года-месяца и порядок обновления старых баз.

### Проверка
- `pytest tests`: **268 passed**.
- `scripts_dev/test_migration_legacy_columns.py`: OK.
- Реальная БД `D:/Projects/Obfuscation/123.db` обновлена до `c8f1a3d5e7b9`
  (резервная копия `123.db.bak-legacy-cleanup-2026-11-14`).
- Импорт файла `C:/Users/User/Documents/тест — копия.txt` в реальную БД:
  `imported=2, matched=2`; созданы оценки `П` (2) для `ТЛГ-00008` от 21.12.2025 и
  `И` (1) для `ТЛГ-00010` от 10.11.2026, список оценок `1` от 14.11.2026;
  файл скопирован в `<хранилище>/Импорт`.

### Отложено
- Отдельный просмотрщик журнала импорта.

---

## 2026-11-14 — Импорт оценок: автоопределение схемы, «Эффект» и статистика

### Изменения
- **`internal_correspondence/text_import/models.py`**: `LayoutScheme.record_length` и
  `line_length`; тип поля `number`; `MatchResult.effect`; в `ImportCounts` добавлены
  `evaluations_received`, `by_value`, `documents_reupdated`, `materials_reupdated`,
  `telegrams_reupdated`.
- **`internal_correspondence/text_import/scheme.py`**: `detect_scheme_by_length()` —
  выбор схемы по длине строки (139/101) и разбор первых строк.
- **`internal_correspondence/text_import/matcher.py`**: `match_auto()` ищет документ
  одновременно в научных материалах и телеграммах по филиалу, исходящему номеру и
  месяцу исходящей даты; добавлены `_auto_branch_code()` и `_auto_effect()`.
- **`internal_correspondence/text_import/service.py`**: автоопределение схемы при загрузке,
  импорт без выбора правила, статистика переоценки, имя копии файла с номером и датой
  документа.
- **`internal_correspondence/orm/models.py`**, **`alembic/versions/d2f4a6c8e0b1_evaluation_effect.py`**:
  поле `Evaluation.effect` (`Numeric(15,2)`); миграция применена к рабочей БД.
- **`internal_correspondence/services/evaluation_import_writer.py`**: сохранение эффекта
  в оценке и в `ScientificMaterial.cost`; подсчёт переоценённых документов.
- **`internal_correspondence/gui/evaluation_import_dialog.py`**: шаг 1 без выбора схемы и
  правила, кнопки «Выбрать файл»/«Очистить»/«Создать новую схему»; предпросмотр по
  столбцам; на шаге совпадений — «Есть оценка»/«Нет оценки» и русские причины; итоговая
  статистика.
- **`schemes/evaluation_data_139.json`**, **`schemes/effect_101.json`**: схемы форматов
  «Оценочные данные» и «Эффект».
- **`tests/test_text_import.py`**, **`tests/test_evaluation_import_dialog.py`**: тесты
  автоопределения схемы, неоднозначного совпадения, эффекта и обновления стоимости,
  автоопределения в диалоге.
- **`README.md`**: новый порядок импорта, описание поля «Эффект» и статистики.

### Проверка
- `pytest tests`: **273 passed**.
- `scripts_dev/test_migration_import_tables.py`: upgrade/downgrade/повторный upgrade OK,
  колонка `evaluations.effect` присутствует.
- `scripts_dev/update_pack_strings.py`: 351 ключ; `compileall` и импорт GUI — OK.
- Рабочая БД `D:/Projects/Obfuscation/123.db` обновлена до `d2f4a6c8e0b1`
  (резервная копия `123.db.bak-effect-2026-11-14`).

### Отложено
- Поле «Оценка_количество» сохраняется в staging, но в бизнес-логике пока не используется.
- Отдельный просмотрщик журнала импорта.

---

## 2026-11-14 — Правки окна импорта оценок

### Изменения
- **`internal_correspondence/gui/evaluation_import_dialog.py`**:
  - при выборе файла через диалог или drag&drop файл сразу загружается, поэтому подпись
    «Схема:» обновляется без дополнительного нажатия «Далее»;
  - окно при открытии занимает 40% ширины и 40% высоты доступной области экрана
    и центрируется (`_apply_initial_geometry()`);
  - в таблице совпадений столбец называется «Имеется оценка»; для существующей оценки
    показывается её код (`П`, `И`, `Б`, `В`), для новой — «Нет оценки».
- **`internal_correspondence/text_import/models.py`**, **`service.py`**: `MatchResult.existing_value`
  заполняется кодом существующей оценки через `enum_codes("evaluation_value")`.
- **`internal_correspondence/gui/application.py`**: из меню «Данные» удалён пункт
  «Правила сопоставления» и метод `_view_import_rules()`; просмотр правил больше не
  требуется, так как сопоставление автоматическое.
- **`tests/test_evaluation_import_dialog.py`**: тесты обновления подписи схемы при выборе
  файла, геометрии окна (40% и центр) и отображения кода существующей оценки.
- **`README.md`**: уточнён столбец «Имеется оценка» и код оценки.

### Проверка
- `tests/test_evaluation_import_dialog.py`: 7 passed.
- Полный `pytest tests`: 276 passed.
- `compileall` и импорт GUI — OK.
- `scripts_dev/update_pack_strings.py`: 351 ключ (значение `import_evaluation_presence` изменено).

### Отложено
- Просмотр правил сопоставления из интерфейса удалён; файл `matcher_rules.json`
  остаётся для обратной совместимости и тестов.

---

## 2026-11-14 — Слияние с alex_develop: история участия в рабочих группах

### Изменения
- Ветка `alex_develop` (7708a19) слита с локальной `main` (3eb3282) в отдельном
  worktree `D:\indus\obfs-merge-check`; конфликты только в `WORK_NOTES.md` и
  `internal_correspondence/services/reference_service.py` (объединены импорты).
- **`internal_correspondence/orm/models.py`:** `Employee.current_membership`
  учитывает плановое окончание — участие действует, пока `start_date <= today`
  и `end_date` пуст или не раньше сегодня. `assign_working_group()` закрывает
  текущее участие датой перевода и запрещает начало нового раньше начала текущего.
- **`internal_correspondence/services/reference_service.py`:** `EmployeeService._validate_period()`
  не принимает окончание раньше начала (исключение из группы, изменение той же
  группы, открытие нового участия).
- **`internal_correspondence/reports/statistics_service.py`:** подкатегория
  «Рабочие группы → Сотрудники» относит сотрудника к группе, действовавшей на дату
  документа (`Employee.workgroup_on(document_date)`), а не к текущей.
- **`internal_correspondence/services/task_distribution_service.py`:** при выборе
  финансового периода учитываются все участия, пересекающиеся с периодом
  (`_groups_during`), а не только текущее.
- **`alembic/versions/c7e2a1b9d3f5_workgroup_memberships.py`:** перецеплена на
  `d2f4a6c8e0b1` (единственная голова); `scripts_dev/test_migration_legacy_columns.py`
  допускает её как head.
- **`tests/test_statistics_service.py`:** историческая группа на дату документа.
- **`tests/test_participants.py`:** плановое окончание и валидация дат.
- **`tests/test_task_distribution.py`**, **`tests/test_task_widget.py`:** переведены
  на `assign_working_group()`.

### Проверка
- `pytest tests`: **280 passed**.
- Миграционные скрипты участий, legacy-колонок, импорта и задач — OK.
- `alembic heads` — `c7e2a1b9d3f5`.
- Рабочая БД `D:/Projects/Obfuscation/123.db` обновлена до `c7e2a1b9d3f5`
  (резервная копия `123.db.bak-memberships-2026-11-14`); перенесено 28 участий
  для 51 сотрудника, старые колонки `working_group_id`/дат удалены.
- Дымовой запуск `MainWindow` (offscreen): 4 вкладки, дерево задач строится,
  корень «Организация» с тремя регионами; ошибок в логе нет.

### Отложено
- README обновлён по участию и исторической статистике.

---

## 2026-11-14 — Зависимость Pillow

### Изменения
- `requirements.txt`, `pyproject.toml`: добавлен `Pillow>=10.0` — без него
  библиотеки, читающие изображения (например, python-docx/openpyxl), падают с
  `ImportError: You must install Pillow to fetch image objects`.

### Проверка
- В `.venv` установлен Pillow 13.0.0; `python -c "import PIL"` — OK.
- `pip check` — No broken requirements found.

### Отложено
- Нет.

---

## 2026-11-14 — Документация схемы базы данных

### Изменения
- `scripts_dev/schema_docs/model.py`: интроспекция `Base.metadata` и Core-таблиц
  импорта (40 таблиц), русские метки, домены, описания сущностей и полей,
  перечень 17 ассоциативных таблиц.
- `scripts_dev/schema_docs/diagrams.py`: пять диаграмм на Pillow без Graphviz —
  обзор доменов, справочники/ОШС, документы, оценки/импорт, задачи/распределение.
- `scripts_dev/schema_docs/docx_builder.py`: сборка DOCX (титул, содержание,
  разделы по доменам, таблицы полей, связи, индексы, ассоциативные таблицы,
  сводка внешних ключей, служебный раздел, порядок сопровождения); альбомные
  страницы для диаграмм, повтор заголовков таблиц, запрет разрыва строк.
- `scripts_dev/dump_schema.py`: CLI генерации `docs/database.docx` и диаграмм.

### Проверка
- Собрано 40 таблиц, 26 таблиц DOCX (23 бизнес-таблицы + 2 импорта + ассоциативные
  и сводная), 5 диаграмм, 25 страниц.
- PDF-версия проверена постранично: титул, содержание, обзор, справочники, ОШС,
  документы, задачи, оценки, импорт, обмен, служебные объекты, ассоциативные
  таблицы, внешние ключи, сопровождение.
- `python -m compileall scripts_dev` — OK.

### Отложено
- Описания части полей оставлены «—»: они берутся из метаданных и дополняются
  вручную в `scripts_dev/schema_docs/model.py` по мере необходимости.

---

## 2026-11-14 — Док прикреплённых файлов: меню «Вид» и запоминание положения

### Запрос пользователя
Связать отображение/скрытие док-виджета AttachedFilesWidget с пунктом меню
«Вид» → «Прикреплённые файлы»; при закрытии приложения запоминать в настройках
положение дока (сторона стыковки, а для откреплённого отдельным окном — его
геометрию) и восстанавливать его при следующем запуске.

### Изменения
- `internal_correspondence/utils/string_resources.py`: новая строка
  `menu_attached_files` («Прикреплённые файлы»); секция `strings` пакета
  перегенерирована скриптом `scripts_dev/update_pack_strings.py`.
- `internal_correspondence/core/settings.py`: в `AppSettings` добавлены поля
  `files_dock_visible`, `files_dock_area` (значение Qt.DockWidgetArea),
  `files_dock_floating`, `files_dock_geometry` (Base64 от saveGeometry).
- `internal_correspondence/gui/application.py`:
  - в меню «Вид» добавлен переключаемый пункт `files_dock_action`
    (toggled → dock.setVisible, dock.visibilityChanged → setChecked);
  - `_save_files_dock_state()` — вызывается из `_save_ui_state()` при закрытии:
    видимость (через isHidden, не зависит от показа окна), область стыковки
    (только когда док не плавающий — плавающий не привязан к области),
    признак «откреплён отдельным окном», геометрия;
  - `_restore_files_dock_state()` — вызывается из `_restore_ui_state()`:
    addDockWidget в сохранённую область, setFloating, restoreGeometry,
    setVisible из настроек; пункт меню синхронизируется явно, т.к.
    visibilityChanged не приходит, пока главное окно не показано;
  - хелперы `_parse_bool()` и `_parse_dock_area()` (устойчивы к мусору в INI).
- `tests/test_window_state.py`: 5 новых тестов — переключение видимости
  пунктом меню, сохранение области/видимости при закрытии, восстановление
  области и видимости из настроек, roundtrip геометрии плавающего окна.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 285 passed, без исключений.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.
- Ручной прогон сценария не выполнялся (offscreen-окружение): поведение меню
  и перетаскивания дока проверены тестами на QWidget API.

### Отложено
- Нет.

---

## 2026-11-14 — Правки диалогов документов и отображения дат

### Запрос пользователя
- EntityEditDialog: при открытии должны быть видны все поля без полосы прокрутки.
- MaterialEditDialog/TelegramEditDialog: максимальная дата QDateEdit — сегодня;
  при создании новой записи дата по умолчанию — сегодня.
- Метки пар «номер и дата»: «Номер и дата исходящего (входящего) документа».
- Даты в таблице — в формате ДД.ММ.ГГГГ.

### Изменения
- `gui/entity_edit_dialog.py`: `_fit_to_content()` — высота диалога вычисляется
  явно по sizeHint контейнера + рамки/отступы (adjustSize для окон урезает
  рост, из-за чего скролл появлялся всегда); вызов в конце __init__ и при
  раскрытии «Больше». Скролл остаётся запасным вариантом при нехватке
  высоты экрана (ограничение availableGeometry).
- `gui/edit_elements.py`:
  - NumberDateEditElement: setMaximumDate(сегодня), умолчание новой записи —
    сегодня (load_value сущности перезаписывает), редактор даты неактивен, пока
    пуст номер; `_current_date()` — дата учитывается только при заполненном
    номере (иначе «сегодня» по умолчанию ломало необязательные пары правилом
    «номер и дата вместе»); collect_data/validate переведены на неё;
  - ReportAddressesEditElement: максимальная дата доклада — сегодня.
- `gui/document_dialogs.py`: метки пар исходящего/входящего/разрешительного —
    из STRINGS (`label_outgoing_number_date`, `label_incoming_number_date`,
    `label_permit_number_date` в `utils/string_resources.py`, пакет
    перегенерирован — 356 ключей).
- `gui/table_model.py`: `_format_value` форматирует date/datetime как
  «ДД.ММ.ГГГГ [ЧЧ:ММ]» (сортировка по строке остаётся хронологической,
  фильтры сравнивают типизированные значения — не затронуты).
- Тесты: `test_edit_dialog.py` — обновлён required/optional валидация пары,
    +границы «сегодня», +пустая пара при пустом номере, +метки диалогов,
    +подгон высоты; `test_document_table_model.py` — +формат ДД.ММ.ГГГГ.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 290 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.
- Offscreen-замеры: малый диалог (TerritorialUnit) — без скролла; объёмный
  MaterialEditDialog ограничивается высотой экрана. Ширина контейнера в
  offscreen завышена артефактом шрифта Helvetica — на экране не воспроизводится.

### Отложено
- Нет.

---

## 2026-11-14 — Экспорт ReportAddress: потеря telegram_id и тест прогона

### Запрос пользователя
Похоже, сломался экспорт ReportAddress — не экспортируется telegram_id;
сделать тест прогона экспорта/импорта.

### Причина
`_mark_created` (services/change_tracking.py) формировал changed_fields
новой записи только из колонок, непустых на момент before_flush. Внешний
ключ telegram_id у адресации новой телеграммы назначается в ходе flush
(синхронизация связи «телеграмма → адресация»), то есть после события, —
поэтому в Change он не попадал, экспортный JSON шёл без telegram_id, и
импорт не мог восстановить связь (конфликт, адресация терялась). Та же
лака для обязательных колонок со значениями по умолчанию, назначаемыми
при вставке.

### Изменения
- `services/change_tracking.py`: новая функция `_created_fields()` — в поля
  создания входят заполненные колонки, колонки NOT NULL и колонки-FK (к
  моменту экспорта значения уже в БД, to_dict читает их оттуда);
  `_mark_created` использует её.
- `tests/test_export_import.py`:
  - `test_report_address_export_contains_telegram_id` — регрессия: CREATE
    адресации новой телеграммы даёт Change с telegram_id, архив содержит
    его (до исправления падает);
  - `test_report_address_export_import_roundtrip` — полный прогон
    экспорт→импорт в чистую БД: телеграмма с двумя адресатами (одна без
    даты доклада) восстанавливается со связями, без конфликтов, без
    служебных Change в приёмной БД.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 292 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.
- Воспроизведение до исправления: Change ReportAddress ['id', 'leader_id',
  'report_date'] — telegram_id отсутствует; после — в changed_fields и в
  архиве, roundtrip-импорт восстанавливает связь.

### Отложено
- Нет.

---

## 2026-11-14 — Прогресс-диалог копирования файлов

### Запрос пользователя
1. Прогресс-бар при копировании не двигается — показывать процент
   скопированного к общему объёму; копировать блоками по 4 Кб.
2. Слишком длинные строки источника/приёмника: сокращать по границам
   каталогов («...\Directory_5»), раскрывать хвост при растягивании диалога.

### Изменения
- `gui/attached_files_widget.py`:
  - CopyFilesWorker: `progressed` теперь отдаёт (имя, источник, приёмник)
    отдельными частями; `step` — накопительные скопированные байты;
    копирование блоками COPY_DIALOG_CHUNK_SIZE = 4 Кб (on_chunk даёт
    позицию внутри файла, к ней добавляется база уже скопированных файлов);
  - CopyProgressLabel: метка прогресс-диалога; пути источника и приёмника
    сокращает по границам каталогов под текущую ширину (_elide_path),
    бюджет на путь — половина ширины минус скелет сообщения, не меньше
    «... + последний компонент»; пересчёт в resizeEvent/showEvent;
  - `_run_copy_thread`: диалог получает метку через setLabel, диапазон
    0..суммарный размер файлов (_safe_file_size).
- `tests/test_attached_files_widget.py`: +тест байтового прогресса
  (монотонность, финал = общий объём, шаги внутри файла), +тест границ
  сокращения _elide_path, +тест адаптации метки к ширине.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 295 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.
- Нюанс окружения: offscreen ограничивает показанные окна экраном 800x600
  и использует широкий запасной шрифт, поэтому широкие состояния метки
  проверены на скрытом виджете с прямым пересчётом.

### Отложено
- Нет.

---

## 2026-11-14 — Исправление OverflowError в прогресс-диалоге копирования

### Проблема
`QProgressDialog.setRange` принимает 32-битные C int, а после перевода
прогресса на байты диапазон стал суммарным объёмом файлов: при копировании
свыше ~2 ГиБ — OverflowError, прикрепление файлов не стартовало
(регрессия байтового прогресса от 2026-11-14).

### Изменения
- `gui/attached_files_widget.py`: константа PROGRESS_INT_MAX и хелпер
  `_progress_range(total)` — (максимум, масштаб); при объёме крупнее
  32-битного диапазона значения полосы делятся на масштаб
  (`value // scale`), точность для обычных объёмов не меняется (масштаб 1).
- `tests/test_attached_files_widget.py`:
  - `test_progress_range_fits_int32_for_huge_volumes` — границы диапазона
    int32, setRange не бросает OverflowError, монотонность отображения;
  - `test_run_copy_thread_handles_huge_total` — сквозной прогон
    `_run_copy_thread` с имитированным объёмом 3×INT_MAX: копирование
    завершается, файл на месте.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 297 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.

### Отложено
- Нет.

---

## 2026-11-14 — Подсветка изменённой строки после операций с файлами

### Проблема
При прикреплении/откреплении файлов подсветка «изменено» в таблице
документов не появлялась до перезапуска (запись Change при этом
создавалась). Причина: док-виджет работает в собственной сессии БД,
Change.change_id у документа появляется там, а табличная модель читает
подсветку из кэша объектов другой сессии (DocumentsTableModel.data,
BackgroundRole → item.change_id) и не перечитывала его.

### Изменения
- `gui/attached_files_widget.py`: сигнал `filesChanged(object)` — id
  документа; испускается после успешной привязки (синхронный путь
  link_existing_files и завершение потока копирования attach_copied_files)
  и после открепления (detach_files).
- `gui/document_list_widget.py`: `reload_document_state(document_id)` —
  expire экземпляра в сессии таблицы и dataChanged по строке с ролью
  BackgroundRole; без полного refresh (выделение/пагинация не трогаются).
- `gui/application.py`: `filesChanged` дока подключён к `_on_files_changed`
  — перенаправляет id в активную вкладку-список документов.

### Проверка
- `tests/test_attached_files_widget.py`: `test_dock_files_changed_after_attach_and_detach`
  — сигнал после привязки и открепления.
- `tests/test_window_state.py`: `test_files_changed_signal_updates_document_row_highlight`
  — интеграция уровня MainWindow: экспорт начальных изменений → строка
  без подсветки; привязка файла через док → BackgroundRole == modified_row.
- `.venv/Scripts/python.exe -m pytest tests -q` — 299 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.

### Отложено
- Переименование файла (FileRecord) документную строку не подсвечивает:
  Change создаётся только для FileRecord, состав документа не меняется —
  поведение не изменено.

---

## 2026-11-14 — Пустой пункт у nullable перечислений (тип доклада)

### Проблема
В диалоге телеграммы у «Типа доклада» (nullable TelegramReportType) не
было пустого значения: EnumEditElement наполнял комбобокс только вариантами
перечисления, поэтому незаполненное поле молча отображало (и сохраняло бы)
первый доступный вариант.

### Изменения
- `gui/edit_elements.py`: EnumEditElement определяет nullable колонки
  (`attribute.property.columns[0].nullable`); у nullable первым пунктом
  добавляется «—» с данными None (как у FK-комбобоксов). Обязательные
  перечисления (тип материала/телеграммы) без изменений.
- `tests/test_edit_dialog.py`: `test_enum_editor_empty_item_for_nullable_column`
  — пустой пункт у типа доклада, round-trip set_value, отсутствие пустого
  пункта у обязательного типа телеграммы.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 300 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.

### Отложено
- Нет.

---

## 2026-11-14 — Тёмная тема: белый уголок таблицы

### Проблема
В тёмной теме внутри таблицы документов белый прямоугольник в правом
нижнем углу — уголок пересечения горизонтальной и вертикальной полос
прокрутки (QAbstractScrollArea::corner). Стиль Windows рисует его
дефолтным светлым фоном; в таблице стилей темы правила не было.

### Изменения
- `gui/theme.py`: в _DARK_STYLESHEET добавлено правило
  QAbstractScrollArea::corner с фоном полос прокрутки (#1E1E21).
- `tests/test_theme.py`: `test_dark_theme_styles_scroll_area_corner` —
  правило присутствует в таблице стилей тёмной темы и задаёт тёмный фон.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 301 passed.
- Применение тёмной темы и показ QTableView в offscreen — без ошибок.

### Отложено
- Нет.

---

## 2026-11-14 — Тёмная тема: белый уголок, доводка (виджет-уголок)

### Проблема
Правило QAbstractScrollArea::corner из предыдущего этапа не помогло:
уголок остался белым. Offscreen-проверка снятием пикселей показала, что
правило срабатывает под QFusionStyle, но стиль Windows (QWindowsStyle/
QWindowsVistaStyle на машине пользователя) рисует уголок сам, игнорируя
subcontrol QSS. Классический стиль заодно оставляет «защемлённые» 4px
стрелки add-line полос прокрутки (предсуществующий артефакт, у пользователя
с Vista-стилем их нет — подавить QSS не удалось).

### Изменения
- `gui/theme.py`:
  - _ScrollCornerInstaller — eventFilter на QEvent.Polish для
    QAbstractScrollArea: ставит setCornerWidget(QWidget) с именем объекта
    scroll_area_corner, если уголок не задан явно. Покрывает виджеты,
    созданные до и после применения темы (Polish приходит при стилизации
    и показе). Подключается в Theme.apply при непустой таблице стилей.
  - В QSS добавлено правило QWidget#scroll_area_corner (#1E1E21) — в светлой
    теме таблицы стилей нет, уголок окрашивается палитрой (остаётся светлым).
  - Правило QAbstractScrollArea::corner сохранено (покрывает стили,
    где subcontrol работает: fusion).
  - Полосам прокрутки добавлен border: none (убирает рамку классического
    стиля).
- `tests/test_theme.py`: test_dark_theme_installs_corner_widget — после
  применения тёмной темы у показанной QTableView появляется cornerWidget
  с именем scroll_area_corner; в test_dark_theme_styles_scroll_area_corner
  добавлена проверка правила для именованного виджета.

### Проверка
- Пиксельная проверка (grab().toImage) в offscreen: уголок тёмный
  (#1E1E21) под QFusionStyle и принудительным QWindowsStyle; в светлой
  теме после переключения уголок светлый.
- `.venv/Scripts/python.exe -m pytest tests -q` — 302 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.

### Отложено
- «Защемлённые» стрелки add-line под классическим QWindowsStyle
  (4px, дитеринг) — не воспроизводятся в среде пользователя
  (WindowsVista-стиль), подавление средствами QSS не найдено.


---

## Слияние с main (2026-11-15) — PR #7, PR #8
- Подтянут `origin/main` (`0424d3c`) в `alex_develop`: fast-forward (`7708a19..0424d3c`), конфликтов нет.
- Новое из main (~86 файлов, +12,7 тыс. строк):
  - модуль импорта оценок из текстовых файлов (`text_import/` — parsing/matcher/scheme/service/repository/storage, ~2,5 тыс. строк) + `gui/evaluation_import_dialog.py`, `services/evaluation_import_writer.py`, схемы в `schemes/`, примеры в `examples/`, `matcher_rules.json`;
  - модуль распределения научных задач: `gui/task_dialog.py`, `gui/task_distribution_widget.py`, `gui/task_table_model.py`, `services/task_distribution_service.py`, обмен `importexport/task_export.py`/`task_import.py`;
  - документация схемы БД и генератор диаграмм (`scripts_dev/schema_docs/`, `docs/*.png`, `docs/database.docx/pdf`);
  - миграции `a7d4e2f6b9c1` (import_tables), `c8f1a3d5e7b9` (cleanup_legacy_service_columns), `d2f4a6c8e0b1` (evaluation_effect), `f3b1c9d2e4a7` (task_distribution); скрипты проверки миграций и `scripts_dev/upgrade_real_db.py`;
  - новые зависимости: `charset-normalizer>=3.3`, `Pillow>=10.0` — установлены в `.venv` (Pillow 13.0.0, charset-normalizer 3.5.2);
  - `tasks.md`, `README.md` и `WORK_NOTES.md` — обновлены в main.
- Адаптация нашего кода не потребовалась.
- `pytest tests`: **302/302 passed**; импорт GUI — OK.

### Замечания
- ~~Демо-база `demo/demo.db` снова отстаёт от схемы (4 новые миграции) — перед следующим показом пересоздать `tests/seed_data.py --with-files`.~~ **ВЫПОЛНЕНО 2026-11-15** — `demo/demo.db` пересоздана с нуля: полная цепочка миграций `alembic upgrade head` (head `c7e2a1b9d3f5`, 40 таблиц включая `import_log`/`import_rows` и view `import_matches`), затем `tests/seed_data.py --with-files --seed 42` (120 материалов, 60 телеграмм, 58 оценок, 49 файлов в `demo/storage`).


---

## Подсветка выделенной строки на диаграмме статистики
### Изменения
- `gui/theme.py`: у `Theme` новый цвет `chart_selection` (светлая `#E8710A`, тёмная `#FFB74D`) — акцент подсветки элемента диаграммы.
- `gui/statistics_widget.py`:
  - каждый построитель диаграммы (`_build_bars`/`_build_lines`/`_build_pie`) заполняет карту `_chart_highlight`: ключ строки результата → функция подсветки; карта сбрасывается при каждой перестройке графика;
  - столбцы — перекрашивание набора в `chart_selection`, линии — утолщение пера и акцентный цвет, круговая — «взрыв» сектора (setExploded);
  - `itemSelectionChanged` таблицы → `_sync_chart_highlight()`: подсветка переносится на выделенные строки, при снятии выделения сбрасывается; выделение групповой строки подкатегории подсвечивает все её элементы (группа на график не выводится); строка «ИТОГО» без ключа игнорируется;
  - при перестроении диаграммы (смена типа, темы, пересчёт) подсветка восстанавливается по текущему выделению.
### Проверка
- `tests/test_statistics_service.py`: +3 теста (столбцы: перенос и снятие подсветки; линии и круговая: перо/взрыв сектора; групповая строка подсвечивает все элементы группы).
- `pytest tests`: **305/305 passed**; импорт GUI — OK.


### Дополнение (2026-11-15) — обратная синхронизация и подсветка «ИТОГО»
- `gui/statistics_widget.py`:
  - строка «ИТОГО» получает служебный ключ `_TOTALS_KEY`; её выделение подсвечивает всю диаграмму целиком (все серии/сектора);
  - обратное направление: клик по элементу диаграммы выделяет строку таблицы — `QBarSeries.clicked(index, barSet)` (сопоставление набора и ключа по указателю C++ через `sip.unwrapinstance`: обёртка PyQt в сигнале — другой объект), у `QLineSeries`/`QPieSlice` — замыкание по ключу строки;
  - два старых теста адаптированы: «ИТОГО» теперь имеет ключ и подсвечивает всё, снятие подсветки проверяется через `clearSelection()`.
- `tests/test_statistics_service.py`: +2 теста («ИТОГО» подсвечивает всю диаграмму; клик по столбцу/линии/сектору выделяет строку).
- README: описана двусторонняя синхронизация таблицы и диаграммы.
- `pytest tests`: **307/307 passed**; импорт GUI — OK.


### Дополнение (2026-11-15, вечер) — исправление падений Qt Charts
- **Падение при клике на сектор круговой** (поймано пользователем): обработчик сигнала `clicked` синхронно выделял строку таблицы, подсветка вызывала `setExploded` на том же элементе внутри обработчика его собственного сигнала — Qt Charts падает. Исправлено: `_select_row_by_key` откладывает выделение через `QTimer.singleShot(0, ...)`.
- **Падение при завершении процесса (exit 127, без traceback и без faulthandler-вывода)**: лямбды, подключённые к сигналам элементов диаграммы (`series.clicked.connect(lambda...)`), роняют нативный движок при очистке памяти, если до этого созданы другие Qt-объекты. Исправлено: везде связанные методы + сопоставление элемента и ключа по указателю C++ (`sip.unwrapinstance`); у круговой — сигнал уровня серии `QPieSeries.clicked(QPieSlice*)` вместо `QPieSlice.clicked`.
- Вывод для будущего: в Qt Charts (PyQt5 5.15) не подключать лямбды к сигналам серий/секторов и не мутировать элемент диаграммы в обработчике его собственного сигнала.
- `pytest tests`: **307/307 passed** (двойной прогон); ручная проверка в приложении — падений нет.


### Дополнение (2026-11-15) — график статистики отсоединяемой панелью
- `gui/statistics_widget.py`: вместо `QSplitter` область содержимого — встроенное `QMainWindow` (атрибуты `main_window`, `chart_dock`): таблица центральным элементом, график (с выбором типа) — `QDockWidget` с флагами `Floatable | Movable` (закрытие недоступно, чтобы панель нельзя было потерять). Панель можно открепить в отдельное окно, перенести к любому краю области и вернуть обратно — как виджет прикреплённых файлов.
- `utils/string_resources.py`: новый ключ `stats_chart_dock_title` («График»); секция `strings` пакета регенерирована (357 ключей).
- `tests/test_statistics_service.py`: старый тест переведён со сплиттера на док-панель; +2 теста (заголовок фиксирован / область растягивается — теперь по `main_window`; панель открепляется в отдельное окно и переносится по краям).
- README: график описан как отсоединяемая панель.
- `pytest tests`: **310/310 passed**; импорт GUI — OK.


### Дополнение (2026-11-15) — ОШС: действующие сверху, заголовок колонки скрыт
- `gui/oshm_dialog.py`:
  - сортировка узлов деревьев «действующие сначала, затем по наименованию/фамилии»: отделы (`Department.active.desc(), name`), сотрудники отдела (`Employee.active.desc(), last_name`), рабочие группы (`WorkingGroup.active.desc(), name`), состав групп (`Employee.active.desc(), last_name`). Работает и на SQLite, и на PostgreSQL;
  - заголовок колонки дерева скрыт (`setHeaderHidden(True)`) — надпись «Элемент» убрана; ключ `oshm_col_element` удалён из `AppStrings`, секция `strings` пакета регенерирована (356 ключей).
- `tests/test_oshm_dialog.py`: +2 теста (скрытый заголовок; активные элементы выше неактивных при алфавитно более ранних неактивных).
- `pytest tests`: **312/312 passed**; импорт GUI — OK.


### Дополнение (2026-11-15) — ОШС: в заголовке окна видно, от кого открыт диалог
- `gui/oshm_dialog.py`: заголовок окна формируется в `_window_title()`: для филиала — «ОШС филиала «{branch_name}» ({branch_id})» (наименование берётся из справочника филиалов, при отсутствии записи — код), для головного офиса — «ОШС — Головной офис».
- `utils/string_resources.py`: формат ключа `oshm_window_title` дополнен плейсхолдером `{branch_name}`; пакет регенерирован.
- `tests/test_oshm_dialog.py`: тест заголовка окна для обеих ролей.
- `pytest tests`: **313/313 passed**; импорт GUI — OK.

## 2026-11-15 — Подключение внешнего QSS к обеим темам

### Изменения
- `internal_correspondence/gui/theme.py`:
  - удалена встроенная строка QSS тёмной темы;
  - добавлена загрузка общего шаблона `application.qss` с кешированием;
  - светлая и тёмная палитры подставляются в шаблон через именованные
    цветовые токены;
  - сохранены отдельные цвета строк документов, нераспределённых задач и
    виджета-уголка полос прокрутки.
- `internal_correspondence/gui/application.qss`:
  - добавлены внешние правила для `QAbstractScrollArea::corner` и
    `QWidget#scroll_area_corner`;
  - цвет уголка задаётся токеном `SCROLL_CORNER`, включая прежний
    `#1E1E21` для тёмной темы.

### Проверка
- `python -m pytest tests -q` с `QT_QPA_PLATFORM=offscreen` — 302 passed.
- `.venv/Scripts/python.exe -c "import internal_correspondence.gui.application; ..."`
  — импорт GUI и построение QSS обеих тем успешны, необработанных токенов нет.
- `.venv/Scripts/python.exe -m pytest tests -q` не запускался: в текущем
  виртуальном окружении отсутствует пакет `pytest`.
- `git diff --check` — ошибок форматирования нет.

### Отложено
- Установить dev-зависимости в `.venv`, чтобы обязательная команда pytest
  из `AGENTS.md` выполнялась тем же интерпретатором, что и приложение.

## 2026-11-15 — Фиксация панели прикреплённых файлов справа

### Изменения
- `internal_correspondence/gui/attached_files_widget.py`: у панели оставлена
  только кнопка закрытия; перемещение и отделение в самостоятельное окно
  отключены, разрешена только правая область главного окна.
- `internal_correspondence/gui/application.py`: панель при запуске всегда
  закрепляется справа, старые настройки левого/плавающего положения
  игнорируются; сохраняется только видимость панели.
- `internal_correspondence/core/settings.py`: уточнено назначение оставленных
  для обратной совместимости параметров положения панели.
- `tests/test_window_state.py`: добавлены проверки фиксированного положения,
  отсутствия кнопки отделения, игнорирования старого плавающего состояния и
  показа/скрытия повторным нажатием пункта меню.
- `README.md`: актуализировано описание панели прикреплённых файлов.

### Проверка
- `python -m pytest tests/test_window_state.py tests/test_attached_files_widget.py -q`
  с `QT_QPA_PLATFORM=offscreen` — 28 passed.
- `python -m pytest tests -q -x` с `QT_QPA_PLATFORM=offscreen` — 302 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"`
  — импорт GUI успешен.
- Первый полный прогон системным Python завершился нестабильным `access violation`
  в фоне Qt; повторный чистый прогон прошёл полностью.
- `.venv/Scripts/python.exe -m pytest tests -q` не запускается: в текущем
  виртуальном окружении отсутствует пакет `pytest`.

### Отложено
- Установить dev-зависимости в `.venv`, чтобы обязательный полный прогон
  выполнялся проектным интерпретатором.

## 2026-11-15 — Формирование месячных и полугодовых отчётов DOCX

### Изменения
- `internal_correspondence/gui/application.py`, `gui/report_dialog.py`: в меню «Данные»
  добавлен диалог формирования отчёта с выбором филиала, месяца/полугодия и года;
  ручные текстовые разделы автоматически загружаются для выбранного периода.
- `internal_correspondence/reports/report_service.py`, `reports/word_report.py`:
  реализованы расчёт показателей из БД, сравнение с тем же периодом прошлого года,
  сохранение ручной части и формирование итогового DOCX через `docxtpl`.
- `internal_correspondence/reports/templates/*.docx`,
  `scripts_dev/build_report_templates.py`: подготовлены и визуально проверены два
  изменяемых Word-шаблона на основе предоставленных документов. При первом запуске
  шаблоны копируются в каталог шаблонов файлового хранилища.
- `orm/models.py`, `core/constants.py`, `services/change_tracking.py`,
  `services/enum_validation.py`: добавлены `ReportDraft` и `ReportType`; черновики
  участвуют в change tracking и ZIP-обмене.
- `alembic/versions/e1a4b7c9d2f6_report_drafts.py`: добавлена совместимая с SQLite
  и PostgreSQL миграция таблицы `report_drafts`.
- `core/domain_pack.default.json`, `utils/string_resources.py`: добавлены метки,
  перечисление типа отчёта и все новые строки интерфейса; секция `strings`
  регенерирована скриптом проекта.
- `pyproject.toml`, `requirements.txt`: добавлена runtime-зависимость `docxtpl`,
  DOCX-шаблоны включены в package data.
- `README.md`: описаны интерфейс отчётов, хранение шаблонов, расчётные правила,
  новая структура данных и команда миграции.
- `tests/test_report_service.py`, `tests/test_export_import.py`,
  `tests/test_window_state.py`, `tests/test_domain_pack.py`: добавлены проверки
  расчётов, рендеринга обоих шаблонов, диалога, меню и ZIP-обмена черновиков.
- `tests/test_attached_files_widget.py`: асинхронный тест копирования ожидает
  планировщик Qt, поэтому полный прогон больше не оставляет активный QThread.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 310 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"`
  — импорт GUI успешен.
- `.venv/Scripts/python.exe scripts_dev/test_migration_report_drafts.py` —
  upgrade/downgrade/upgrade успешно.
- `.venv/Scripts/python.exe -m compileall -q internal_correspondence scripts_dev tests`
  — успешно.
- Оба шаблона отрисованы LibreOffice и визуально проверены постранично: выходов
  за границы, наложений и неразрешённых маркеров нет.

### Отложено
- Точные формулировки постоянного текста, правила заполнения качественных разделов
  и состав показателей можно уточнять без изменения схемы БД: текст — во внешних
  шаблонах, ручные значения — в `ReportDraft`, расчёты — в `ReportDataService`.

## 2026-11-15 — Актуализация внешнего пакета для отчётов

### Изменения
- `domain_pack.json`: в активный внешний пакет добавлено перечисление
  `report_type` с неизменяемыми ключами `month` и `half_year` и кодами `МЕС`/`ПОЛ`.
  Остальные пользовательские значения пакета не изменялись.

### Проверка
- Внешний пакет успешно загружается через `load_domain_pack`.
- `validate_enum_codes` для активной БД `123.db` — предупреждений нет.

### Отложено
- Нет.

## 2026-11-15 — Приведение DOCX-отчётов к предоставленным образцам

### Изменения
- `scripts_dev/report_template_sources/*.docx`: сохранены контрольные копии
  предоставленных образцов, от которых воспроизводимо собираются шаблоны.
- `scripts_dev/build_report_templates.py`, `reports/templates/*.docx`: шаблоны
  перестроены непосредственно из образцов с сохранением геометрии страниц,
  абзацев, колонтитулов и состава таблиц. В месячном отчёте оставлена одна
  исходная таблица, в полугодовом — ровно три; добавленные ранее таблицы удалены.
- `internal_correspondence/reports/report_service.py`: подготовлены вычисляемые
  значения для текстовых слотов и трёх таблиц образцов без сохранения расчётов в БД.
- `internal_correspondence/reports/word_report.py`: известные устаревшие встроенные
  копии во внешнем каталоге шаблонов безопасно обновляются; пользовательские
  варианты с другим содержимым остаются без изменений.
- `tests/test_report_service.py`: зафиксировано количество таблиц обоих отчётов и
  проверено безопасное обновление только известной устаревшей версии.
- `README.md`: уточнена структура шаблонов и правило обновления внешних копий.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests/test_report_service.py -q` — 7 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 311 passed.
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"`
  — импорт GUI успешен.
- `.venv/Scripts/python.exe -m compileall -q internal_correspondence scripts_dev tests`
  — успешно.
- Оба отчёта сформированы на данных `123.db`, отрисованы LibreOffice и проверены
  постранично; строки таблиц не разрываются между страницами, структура образцов
  и отсутствие дополнительных таблиц подтверждены.

### Отложено
- Нет.

## 2026-11-15 — Проверка типа черновика отчёта по активному пакету

### Изменения
- `internal_correspondence/core/enum_registry.py`: `ReportType` зарегистрирован
  как перечисление пакета `report_type`, поэтому значения `0` и `1` из
  `ReportDraft.report_type` преобразуются в ключи `month` и `half_year`.
- `tests/test_domain_pack_integration.py`: проверка известных кодов дополнена
  черновиком полугодового отчёта со значением `ReportType.HALF_YEAR`.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests/test_domain_pack_integration.py -q`
  — 14 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 311 passed.
- На активном `domain_pack.json` и рабочей `123.db` функция
  `validate_enum_codes()` вернула пустой список предупреждений.
- Импорт `internal_correspondence.gui.application` и `compileall` успешны.

### Отложено
- Нет.

## 2026-11-15 — Индикатор формирования отчёта

### Изменения
- `internal_correspondence/gui/application.py`: после подтверждения пути
  сохранения показывается модальный неопределённый индикатор; он закрывается до
  сообщения об успешном завершении или ошибке.
- `internal_correspondence/utils/string_resources.py`: добавлена ресурсная строка
  `report_progress_creating` без захардкоженного текста в GUI.
- `internal_correspondence/core/domain_pack.default.json`: секция `strings`
  регенерирована скриптом проекта.
- `tests/test_window_state.py`: проверены текст, модальность, отсутствие отмены и
  фактическая видимость индикатора во время вызова рендера.
- `README.md`: описано поведение индикатора.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests/test_window_state.py -q` — 14 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 313 passed.
- Импорт `internal_correspondence.gui.application` и `compileall` успешны.

### Отложено
- Нет.

## 2026-11-15 — Стили кнопок на научных материалах телеграммах

### Изменения
- `internal_correspondence/gui/document_list_widget.py`: кнопки на вкладках
  научных материалов и телеграмм получили те же QSS-роли, что в редакторе
  «Данные → Страны»: акцентную для добавления, нейтральную для изменения и
  опасную для удаления.
- `tests/test_window_state.py`: одинаковые роли проверяются на обеих вкладках.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests/test_window_state.py -q` — 15 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 314 passed.
- Импорт `internal_correspondence.gui.application` и `compileall` успешны.

### Отложено
- Нет.

## 2026-11-15 — Повторное подключение внешнего QSS после слияния

### Изменения
- `internal_correspondence/gui/theme.py`: восстановлена загрузка
  `application.qss` для светлой и тёмной тем вместо встроенного старого QSS;
  сохранён входящий цвет подсветки выбранного элемента диаграммы.
- `README.md`: описано подключение общего QSS и переключение тем.
- Стандартная системная шапка окна не изменялась.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests/test_theme.py -q` — 9 passed.
- Тесты окна и статистики — 44 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 325 passed, одно известное предупреждение DOCX.
- Импорт обеих тем и подстановка всех токенов QSS успешны.

### Отложено
- Нет.


---

## 2026-11-15 — Подсветка строк: QSS глушил BackgroundRole; цвета тёмной темы

### Проблема
Перестало работать выделение неэкспортированных и без входящего номера
строк материалов/телеграмм в обеих темах.

### Причина (пиксельная диагностика offscreen)
Новый общий QSS-шаблон (application.qss, редизайн тем) содержал базовое
правило «QTableView::item, ... { padding: 5px 7px; border: 0 }». Наличие
любого правила ::item переводит отрисовку фона элементов на
QStyleSheetStyle, который фон из модели (BackgroundRole) не использует —
подсветка пропадала полностью. Проверено снятием пикселей: без правила
цвета строк видны, с ним — только фон/чередование таблицы.

Дополнительно значения подсветки тёмной темы остались от старой палитры
и на новой (base #1D2430, stripe #242D3A) почти неразличимы.

### Изменения
- `gui/application.qss`: базовое правило ::item (padding/border) удалено;
  правила ::item:hover и ::item:selected сохранены — на BackgroundRole
  они не влияют (проверено). Цена: у ячеек нет отступа 5px.
- `gui/theme.py` (DARK_THEME): modified_row #574A2B → #7E6434,
  no_incoming_row #2F3B4C → #35496B — контраст к новой палитре.
  Светлая тема без изменений (значения контрастные).
- `tests/test_theme.py`:
  - test_item_background_role_visible_in_both_themes — пиксельный тест:
    таблица с BackgroundRole рендерится с реальным QSS темы, цвета
    modified_row/no_incoming_row присутствуют в пикселях (падает при
    возврате правила ::item);
  - test_row_highlight_colors_contrast_with_table — цвета подсветки
    отличны от фона и чередования таблицы в обеих темах.

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 327 passed
  (1 предупреждение zipfile «Duplicate name» — предсуществующее,
  из тестов генерации отчётов, не связано).
- Пиксельная проверка: обе темы рисуют оба цвета подсветки.

### Отложено
- Нет.

---

## 2026-11-15 — Фильтры документов: «None» в строке, пустые значения, перечисления

### Запрос пользователя
1. В диалоге фильтров в строке условия вместо наименования поля — «None».
2. Для nullable-полей — возможность выбрать пустое значение.
3. Для полей-перечислений (IntEnum) — выбор значений из списка
   (уточнён вариант: QListWidget с галочками, мультивыбор «одно из»).

### Изменения
- `gui/filter_dialog.py`:
  - FilterDialog._build_row: заголовок колонки с fallback на
    field_short_label (у большинства колонок ColumnDef.header = None —
    отсюда «None» в строке условия);
  - AddFilterDialog: страница значения «enum» — QListWidget с галочками
    (пакетные варианты через pack_enum_choices); операторы строятся с
    учётом nullability; унарные операторы блокируют редактор значения;
    загрузка сохранённого условия восстанавливает галочки/оператор.
- `gui/filter_model.py`:
  - новый тип значения «enum» (IntEnumType до проверки Integer — раньше
    перечисления падали в «text»); хелперы resolve_nullable/
    resolve_pack_enum/_resolve_column;
  - операторы: ENUM_OPERATORS [in «одно из»], NULL_OPERATORS
    [empty/not_empty] для nullable колонок (любого типа);
    operators_for(value_type, nullable); валидация from_dict с nullability;
  - FilterCondition.matches: «in» по множеству кодов (устойчиво к мусору),
    унарные проверки пустоты (None и пустая строка) до типового разбора;
  - describe: унарные условия без значения; enum подписывается метками
    пакета; format_filter_value(value, type, pack_enum).
- `core/enum_registry.py`: pack_key_for_enum_class — общий маппинг
  имя IntEnum-класса → ключ пакета.
- `gui/edit_elements.py`: локальный _ENUM_PACK_KEYS удалён, используется
  общий хелпер (заодно подхватывает ReportType).
- `utils/string_resources.py`: filter_op_in/filter_op_empty/
  filter_op_not_empty; секция strings пакета перегенерирована (398 ключей).
- Тесты: test_filters.py — распознавание enum/nullable, операторы,
  сопоставление «одно из» и пустоты, describe, from_dict, модель таблицы,
  регрессия «None», чек-лист диалога, блокировка редактора, загрузка
  условия; test_filters_persistence.py — roundtrip «in»/«empty».

### Проверка
- `.venv/Scripts/python.exe -m pytest tests -q` — 338 passed
  (1 предупреждение zipfile — предсуществующее, не связано).
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import internal_correspondence.gui.application"` — OK.

### Отложено
- Старые подписи операторов («содержит», «≠» и т.п.) остались
  строковыми константами filter_model (до редизайна); новые строки —
  через AppStrings по инварианту white-label.
