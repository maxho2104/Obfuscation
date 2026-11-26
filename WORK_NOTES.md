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

---

## 2026-11-16 — Исправление поиска задач и обновления дерева ОШС

### Запрос пользователя
1. Ошибка поиска по задачам: `AttributeError: 'ScientificTaskType'
   object has no attribute 'lower'`.
2. После первичной загрузки дерево ОШС не обновляется после добавления
   отдела или сотрудника.

### Изменения
- `gui/task_table_model.py`: тип задачи переводится из IntEnum в код
  пакета через `pack_enum_display`, затем в метку через `enum_label`;
  хелпер `_type_label` используется в поиске, сортировке и отображении.
  Убрано сравнение `(task.type or "").lower()` — IntEnum не строка.
- `gui/oshm_dialog.py`: `_tree_state`/`_restore_tree_state` запоминают
  раскрытые и выбранные узлы до перестройки деревьев и восстанавливают
  их после; родители выбранных узлов раскрываются, поэтому добавленный
  отдел/сотрудник не остаётся внутри свёрнутого узла.
- `services/reference_service.py`: `EmployeeService.create` проверяет
  `wg_id is not _UNSET` (раньше sentinel `_UNSET` попадал в
  `session.get(WorkingGroup, ...)` и добавление сотрудника без группы
  падало с `AttributeError: 'object' object has no attribute 'hex'`).

### Проверка
- `pytest tests -q` — 341 passed (1 предупреждение zipfile —
  предсуществующее, из тестов отчётов).
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import
  internal_correspondence.gui.application"` — OK.
- Добавлены тесты: поиск по метке типа задачи; сохранение раскрытия
  отдела после добавления сотрудника; сохранение раскрытия филиала
  после добавления отдела.

---

## 2026-11-16 — Просмотр оценочных листов

### Запрос пользователя
Добавить в меню «Данные» пункт «Оценочные листы» под «Импорт оценок из
файла»: окно со списком журналов импорта слева (номер журнала, дата
импорта, номер и дата документа) и строками выбранного журнала справа.
Совпавшие и импортированные строки — светло-зелёные, несовпавшие —
светло-розовые, отклонённые — светло-оранжевые. Только просмотр,
кнопка «Закрыть» внизу справа.

### Изменения
- `gui/evaluation_lists_dialog.py`: новый диалог `EvaluationListsDialog`;
  слева `QTableWidget` журналов (`import_log`), справа — строки
  (`import_rows`); выбор журнала загружает строки; статусы
  `matched`/`unmatched`/`rejected` окрашиваются в
  `#D9EAD3`/`#F4CCCC`/`#FCE5CD`; таблицы только для чтения; кнопка
  «Закрыть»; сессия закрывается при закрытии окна.
- `gui/application.py`: пункт меню «Оценочные листы» сразу после
  «Импорт оценок из файла...», метод `_open_evaluation_lists`.
- `utils/string_resources.py`: новые ключи `menu_evaluation_lists`,
  `evaluation_lists_*`; секция strings пакета перегенерирована
  (422 ключа).
- `tests/test_evaluation_lists_dialog.py`: журналы/строки, статусы и
  цвета, режим только для чтения.
- `tests/test_window_state.py`: пункт меню находится сразу после
  импорта оценок.

### Проверка
- `pytest tests -q` — 343 passed (1 предупреждение zipfile —
  предсуществующее).
- `PYTHONPATH=. .venv/Scripts/python.exe -c "import
  internal_correspondence.gui.application"` — OK.
- Дымовой запуск на рабочей БД: 9 журналов, выбранный журнал — 2 строки.

### Отложено
- Цвета не зависят от темы (светлые фоны с тёмным текстом); при
  необходимости можно сделать палитру темной темы отдельной.
---

## Слияние с main (2026-11-16) — PR #9, #10, #11
- Подтянут `origin/main` (`6c13b3a`) в `alex_develop`: fast-forward, конфликтов нет — main уже включал нашу ветку через PR #9.
- Новое из main (~5,8 тыс. строк):
  - **подсистема отчётов**: `reports/report_service.py` (~1,3 тыс. строк), `reports/word_report.py` (docxtpl), `gui/report_dialog.py`, шаблоны `reports/templates/{monthly_analysis,halfyear_analysis}.docx`, генератор шаблонов `scripts_dev/build_report_templates.py`; отчёты за месяц и полугодие;
  - миграция `e1a4b7c9d2f6` (таблица `report_drafts`) — применена к `demo/demo.db` (head `e1a4b7c9d2f6`);
  - **новый UI**: `application.qss` (477 строк), иконки combo-arrow, переработанный `theme.py` (+332), правки фильтров (выделение неэкспортированных/без входящего номера, отображение фильтров);
  - новая зависимость `docxtpl>=0.20,<1` (+jinja2) — установлена в `.venv`;
  - выгруженный пакет `domain_pack.json` в корне (1 тыс. строк).
- Наши доработки (синхронизация таблицы/диаграммы, док-панель графика, ОШС) в main сохранены; адаптация не потребовалась.
- `pytest tests`: **338/338 passed** (25 новых тестов main, в т.ч. `test_report_service.py`); импорт GUI — OK. Единственное замечание — безобидный warning `Duplicate name: 'docProps/core.xml'` при сборке docx из шаблона (python-docx/docxtpl).


### Дополнение (2026-11-16) — вложенная круговая диаграмма для подкатегории
- `gui/statistics_widget.py`:
  - `_build_pie`: при выбранной подкатегории круговая диаграмма строится вложенной (`_build_nested_pie`) — два наложенных `QPieSeries`: внутренний диск — категории (группы) цветами групп без подписей, внешнее кольцо — элементы подкатегории оттенками цвета группы с подписями снаружи в формате «категория - подкатегория» (`LabelOutside`, легенда скрыта); геометрия: внешнее кольцо `pieSize 0.95 / holeSize 0.55`, внутренний диск `pieSize 0.52`; без подкатегории — прежняя одиночная диаграмма;
  - секторы внутреннего кольца регистрируются в `_chart_highlight`/`_slice_keys` по ключу группы: клик по категории выделяет групповую строку, выделение групповой строки взрывает и категорию, и её элементы; `_sync_chart_highlight` теперь включает в цели сами выделенные ключи (не только их элементы).
- `tests/test_statistics_service.py`: +1 тест (два кольца, подписи «Отдел - Иванов И.», внутренние без подписей, взрыв обоих колец при выделении группы, клик по категории выделяет групповую строку).
- README: описана вложенная круговая диаграмма.
- `pytest tests`: **339/339 passed**; импорт GUI — OK.


### Дополнение (2026-11-16) — панель сведений ОШС переведена на механизм распределения задач
- `gui/oshm_details_panel.py`: таблица назначенных задач сотрудника больше не использует историческую связь `Employee.tasks` (`task_employee_association`) — чтение/добавление/снятие назначений идут через `AddedTask` (`node_type="employee"`, `node_id=str(employee.id)`), единый механизм с вкладкой «Задачи» и дельта-обменом; назначения попадают в change tracking автоматически (`ChangeTrackedMixin`).
- `tests/test_oshm_dialog.py`: фикстура назначает задачу через `AddedTask`; тест снятия проверяет удаление записи `AddedTask`.
- **Не закрыто**: подкатегория статистики «Научные задачи → Сотрудники» (`statistics_service._parent_links`, строка ~75) по-прежнему группирует по старой связи `member.tasks` — после перевода панели данные разойдутся; перевод статистики на `AddedTask` — следующий шаг (потребует правки фикстур тестов статистики).
- `pytest tests`: **339/339 passed**; импорт GUI — OK.


### Дополнение (2026-11-16, ночь) — задачи в панели сведений ОШС для всех элементов
- `gui/oshm_details_panel.py`:
  - таблица назначенных задач показывается не только сотруднику, но и филиалу, отделу и рабочей группе; корень «Головной офис» — без таблицы;
  - ограничение по иерархии модуля «Задачи»: в диалоге выбора доступны только задачи, назначенные старшему элементу — филиалу из пула региона (`node_type=region`), отделу из назначенных филиалу, рабочей группе и сотруднику из назначенных их отделу (`TaskPickerDialog` получил параметр `allowed_ids`);
  - права: филиал/отдел/группа редактируют назначения обеим ролями, сотрудника — только филиал (`can_edit_people`);
  - чтение/запись — через `AddedTask` (см. предыдущую запись).
- `tests/test_oshm_dialog.py`: фикстура дополнена назначениями уровня branch/department; +2 теста (таблица задач у отдела и группы, видимость по уровням; фильтр `allowed_ids` в диалоге выбора).
- README: раздел ОШС — таблица задач для всех элементов с правилом старшего элемента.
- `pytest tests`: **341/341 passed**; импорт GUI — OK.


### Дополнение (2026-11-16) — статистика «Задачи → Сотрудники» на added_tasks
- `reports/statistics_service.py`: подкатегория «Научные задачи → Сотрудники» больше не использует историческую связь `Employee.tasks` — назначения читаются из `AddedTask` (`node_type="employee"`); карта «сотрудник → задачи» строится одним запросом на подсчёт (`_employee_task_map`) и передаётся в `_parent_links` (новый параметр `task_map`).
- `tests/test_statistics_service.py`: фикстура назначает исполнителя через `AddedTask`.
- Теперь панель сведений ОШС, вкладка «Задачи» и статистика работают на одном механизме (`added_tasks`) — данные не расходятся.
- `pytest tests`: **341/341 passed**; импорт GUI — OK.


### Дополнение (2026-11-16) — удаление исторической связи «задача — сотрудник»
- **Модель (`orm/models.py`):** удалены ассоциативная таблица `task_employee_association` (`task_employees`) и связи `ScientificTask.employees` / `Employee.tasks`. Последними потребителями были панель сведений ОШС и статистика — обе переведены на `AddedTask` (см. предыдущие записи).
- **Миграция `alembic/versions/f4c6a8d0e2b1_drop_task_employees.py`** (после `e1a4b7c9d2f6`): upgrade удаляет `task_employees` (с проверкой существования через инспектор — портибельно SQLite/PostgreSQL); downgrade пересоздаёт таблицу пустой (данные не восстанавливаются — задокументировано в docstring).
- `scripts_dev/schema_docs/model.py`: убрана разметка таблицы `task_employees` из генератора схемы.
- `scripts_dev/test_migration_task_distribution.py`: обновлён под новую миграцию (upgrade — таблица удалена; downgrade — пересоздана пустой). Проверен: upgrade → downgrade → повторный upgrade.
- Демо-база `demo/demo.db` приведена к head (`f4c6a8d0e2b1`).
- `pytest tests`: **341/341 passed**; импорт GUI — OK.


### Дополнение (2026-11-17) — формат подписи вложенной круговой в пакете строк
- `gui/statistics_widget.py`: формат подписи сектора внешнего кольца («категория - подкатегория») вместо f-строки — через `STRINGS.chart_slice_grouped_label` (`{group} - {member}`).
- Проверка полноты пакета: все 399 ключей `AppStrings` присутствуют в секции `strings` `domain_pack.default.json`, лишних нет (регенерация скриптом `update_pack_strings.py`).
- Аудит `statistics_widget.py` на захардкоженные строки: чисто (месяцы — осознанно вне пакета как локализация, сообщения лога — не UI).
- `pytest tests`: **341/341 passed**; импорт GUI — OK.

### Дополнение (2026-11-17) — вкладка «Дашборд»
- `reports/dashboard_service.py` — `DashboardService`: KPI, документы/оценки/задачи, изменения, последний импорт, месячная серия, типы, рейтинг, последние документы и «Требуют внимания»; периоды через `build_reporting_period`, финансовый год, фильтр филиала; безопасное чтение `import_log` на БД без таблиц импорта.
- `gui/dashboard_widget.py` — `DashboardWidget` с фильтрами, четырьмя KPI-карточками, четырьмя диаграммами PyQtChart (столбцы/круговая), таблицей последних документов и списком внимания.
- `gui/application.py` — вкладка «Дашборд» первой; обновление после экспорта/импорта, импорта справочников и оценок, смены темы. `_on_files_changed` теперь обновляет обе вкладки документов, а не только активную: док файлов может быть привязан к записи при открытом дашборде.
- `utils/string_resources.py`, `core/domain_pack.default.json` — 471 ключ, секция strings регенерирована.
- `tests/test_dashboard.py` — 5 тестов сервиса и виджета; `tests/test_window_state.py` — исправлена проверка подсветки после прикрепления файла.
- `README.md` — раздел «Дашборд».
- Проверка: `pytest tests -q` — **352 passed**; импорт GUI — OK; native-скриншоты 1024×768 и 1400×900.

### Дополнение (2026-11-18) — этап 1: двухфазное сидирование и UUID-источники

**Скрипты сидирования (план 2026-11-17_plan.md, раздел 1):**
- `tests/seed_common.py` — общие помощники: `YearlyCounter` (годовой счётчик с сбросом 1 января и сдвигом `basis()` за максимумом существующих номеров), разбор диапазонов/дат, прикрепление файлов, определение БД/хранилища.
- `tests/seed_branch.py` — фаза филиала: справочники (при отсутствии), ОШС филиала, источники, материалы/телеграммы за период (`--from/--to`, по умолчанию последние 30 дней; `--materials-per-day`/`--telegrams-per-day` N-M). Нумерация `ИСХ-`/`ТЛГ-`/`РАЗР-` — раздельные годовые счётчики, продолжающие общую последовательность года (составной уникальный индекс «номер+дата» глобален). Для ОБРАЗЕЦ_ПРОДУКЦИИ/ТЕХНИЧЕСКИЙ_ДОКУМЕНТ — серийный номер, год выпуска, разрешительный документ (дата = исходящая или день ранее), для образцов — стоимость. Адреса докладов — без даты. `--branch` задаёт филиал; отсутствующий генерируется через Faker. Файлы-вложения — `--with-files`.
- `tests/seed_head_office.py` — фаза ГО: входящие номера `ВХ-` (единый счётчик на все филиалы), дата = исходящей; правки потребителя (1/30) и комментария (1/5); оценки для всех материалов и 1/100 телеграмм — 1-10 документов на оценку, разброс дат ≤ 14 дней, дата оценки ∈ [max дата документов; +3 дня]; списки оценок `ОЦ-` — 1-10 оценок, дата = max дата оценок; типы докладов (REPORTED чаще, URGENTLY_REPORTED реже), даты адресатам = дате входящего. Повторный запуск пропускает зарегистрированные документы (HeadOfficeSeedError, если все обработаны).
- `tests/seed_data.py` (прежний однофазный генератор) сохранён; `_create_sources` переведён на UUID+индекс.

**Источники: UUID + индекс:**
- `orm/models.py`: `Source.id` — UUID PK (`_uuid_pk()`), новая колонка `index` String(10) unique с меткой «Индекс» (`__field_labels__` для `id` — «Идентификатор»); `material_sources`/`telegram_sources` — `source_id` теперь UUID.
- Миграция `alembic/versions/a1b2c3d4e5f6_sources_uuid_index.py`: пересоздание трёх таблиц через временные (перенос id→UUID, индекс = прежний id ≤10 символов с дедупликацией, обновление `changes.entity_pk` и обеих связок); перенацеливание FK на PostgreSQL после rename (SQLite ≥3.25 — сам). Downgrade: id восстанавливается из индекса (UUID теряется — в docstring).
- `scripts_dev/test_migration_sources_uuid.py`: upgrade → downgrade → повторный upgrade на временной SQLite.
- GUI: `SOURCE_COLUMNS` показывает `index` вместо UUID `id`; `domain_pack.default.json` — метки `id`/`index` сущности Source.

**Тесты:** `tests/test_seed_branch.py` (6: счётчики/нумерация, сброс года, реквизиты разрешительных, uuid+индекс источников, файлы, генерация новых филиалов), `tests/test_seed_head_office.py` (5: входящие номера, правила групп оценок, списки оценок, адресация/типы докладов, повторный запуск). Обновлены фикстуры `test_statistics_service.py` (источники S1/S2 — UUID+index), `test_entity_labels.py` зелёный за счёт `__field_labels__`.

**Проверка:** `pytest tests` — **363 passed**; импорт GUI — OK; ручной прогон экспорт→импорт ZIP с UUID-источниками (82 записи, 0 конфликтов); `test_migration_sources_uuid.py` — OK; старый `seed_data.py` — работает.

**Следующий этап:** раздел 2 плана (экспорт по филиалам с диалогом выбора, имена файлов «для/от <филиал>», поток+прогресс, meta.json со сводкой, импорт с анализом зелёный/красный/жёлтый, таблица запросов + missing.json).

### Дополнение (2026-11-18) — этап 2: экспорт по филиалам и анализ импорта

**Атрибуция «сущность → филиал» (`importexport/branch_scope.py`):**
- `branches_for_change()` — справочники (TerritorialUnit/Branch/Country/AcademicTitle/Consumer/Leader/ScientificTask/AddedTask) → None (в каждый ZIP); документы → свой branch_id; ОШС (Department/WorkingGroup/Employee/WorkGroupMembership) → через отдел; Evaluation/FileRecord/ReportAddress/EvaluationList/Source → через связанные документы (множество филиалов — в архив каждого; источник-сирота — ни в один, остаётся неэкспортированным); удалённые документы без экземпляра — не атрибутируются.
- `pending_branch_ids()` — филиалы с неэкспортированными изменениями (для диалога ГО).

**Запросы контрагенту:** модель `MissingRequest` (`missing_requests`: id autoincrement, branch_id nullable FK→branches, entity_name, entity_pk, created_at; без ChangeTrackedMixin — передаётся отдельным файлом). Миграция `alembic/versions/b2c3d4e5f6a7_missing_requests.py` (create/drop, портибельно). Метки зеркалены в доменном пакете.

**Экспорт (`importexport/export_service.py`):**
- `export()` — прежний единый архив, сохранён для совместимости и тестов.
- `export_branch()` — филиал: один архив «`<UTC время>` от `<short>`.zip» со всеми изменениями.
- `export_for_branches(branch_ids)` — ГО: архив «`<UTC время>` для `<short>`.zip» на филиал: его изменения + полный набор справочных; `ExportError` для роли филиала. `pending_branches()` — список для диалога.
- Метка `exported_at` — только после записи всех архивов; при ошибке частичные файлы удаляются (`_write_archives`). Справочный Change, вошедший в несколько архивов, помечается один раз (дедупликация по id).
- `meta.json`: + `summary` — {таблица: {added, updated, deleted}}. `missing.json` — перечень MissingRequest, включается при непустой таблице; после успешного экспорта таблица очищается. Имена файлов: `archive_filename()` с санитизацией недопустимых символов Windows.
- Опциональный `progress_cb(current, total, entity)` для прогресс-диалога.

**Импорт (`importexport/import_service.py`):**
- `analyze_archive()` — анализ без применения: `ok` (create/update с обязательными полями и доступными зависимостями), `warning` (delete отсутствующей записи), `error` (неизвестная сущность, некорректный PK, пропущены обязательные поля по `info["required"]`, не найдены зависимости FK/N-N — в БД или в пакете).
- `import_archive(exclude=...)` — пропуск записей по ключам (жёлтые/красные из анализа).
- `record_missing_requests(entries)` — фиксация «не найден»-записей; филиал проставляет себя, ГО — NULL.

**GUI (`gui/exchange_dialogs.py`, `application.py`):**
- `ExportBranchesDialog` — список филиалов с флажками + общий «Все».
- `ExportWorker` (QThread) — сессия БД создаётся внутри потока; сигналы `progressed/succeeded/failed`; `_export` ГО: диалог выбора → воркер; филиал — сразу воркер; QProgressDialog суммарный.
- `ImportPreviewDialog` — таблица анализа (сущность/ключ/операция/статус/пояснение), строки маркированы цветом (зелёный/жёлтый/красный), «Применить/Отмена»; применяются только «зелёные», по «красным» — запросы контрагенту.
- Новые ключи `AppStrings` (диалоги выбора/анализа, прогресс, статусы), секция `strings` регенерирована (`update_pack_strings.py`, 494 ключа).

**Тесты:** `tests/test_branch_export.py` — 12 тестов: резолвер, pending, экспорт по филиалам (имена, состав, пометка), единый архив филиала, сводка meta, missing.json+очистка, анализ (ok/warning/error/unknown), exclude-импорт, запись запросов (роли), анализ реального архива.

**Проверка:** `pytest tests` — **375 passed**; импорт GUI — OK; прогонка миграций (`test_migration_sources_uuid.py`, head теперь `b2c3d4e5f6a7`) — OK.

**Следующий этап:** раздел 3 плана — переработка изменения оценки (последняя по дате/значению, удаление одиночной оценки, диалог выставления: новый список / привязка к существующему, пометка документа изменённым).

### Дополнение (2026-11-18) — этап 3: механизм изменения оценки

**Сервис (`services/evaluation_service.py`):**
- `EvaluationService.set_evaluation(document, value, date, evaluation_list)` — присваивает документу новую оценку: связь со старой последней оценкой снимается всегда; сама старая оценка удаляется, только если она последняя исключительно для этого документа (`_is_exclusive_last` перебирает остальные связанные документы); удаление обязательно с явным `document.evaluations.remove(previous)` — иначе на SQLite без FK-pragma строки связки остаются.
- Документ помечается изменённым через новый публичный helper `change_tracking.mark_fields_changed()` (штатный before_flush не видит изменение: владельцем ассоциативной таблицы `evaluation_materials`/`evaluation_telegrams` является оценка). В Change документа попадает связь `evaluations` — она сериализуется экспортом (абсолютный состав связи) и применяется на приёмной стороне.
- `create_list()` / `suggest_list_number()` — следующий номер «ОЦ-NNNNN» в годовой последовательности.
- `EvaluationMixin.latest_evaluation`: tie-break при равных датах изменён со `str(id)` на большее значение оценки (`int(value)`).

**GUI (`gui/evaluation_dialog.py`, `document_list_widget.py`):**
- `EvaluationAssignDialog(session)`: значение + дата; режимы «Создать новый список оценок» (номер авто, дата) / «Привязать к существующему списку» (фильтр по номеру + список). Новые ключи `AppStrings`, секция strings регенерирована (500 ключей).
- `_assign_evaluation`: один диалог на выделенные записи → список создаётся один, оценки присваиваются через сервис.

**Тесты:** `tests/test_evaluation_service.py` — 9 (tie-break, первое выставление + Change документа, замена одиночной, сохранение общей оценки у других документов, удаление при «утратившей последность» у других, повторное выставление, годовая нумерация списков, привязка к списку, диалог); `tests/test_evaluation_assign.py` обновлён под новую сигнатуру диалога.

**Проверка:** `pytest tests` — **384 passed**; импорт GUI — OK. Все три раздела плана `2026-11-17_plan.md` выполнены.

### Дополнение (2026-11-18) — этап 3, правки по замечаниям

- **Диалог выставления оценки, невидимый текст списков:** `QListWidgetItem.setData(0, uuid)` затирал DisplayRole (QVariant не переваривает `uuid.UUID` — элемент отображался пустым). Идентификатор перенесён в `Qt.UserRole` (`gui/evaluation_dialog.py`); добавлена проверка непустого текста элемента в тесте.
- **Совокупностная оценка выделенных записей:** `EvaluationService.assign_evaluation(documents, ...)` создаёт одну оценку на все выделенные документы (`set_evaluation` — обёртка для одного). Снятие прежних оценок — первым проходом для всей совокупности, удаление — вторым (после снятия связей «последность» пересчитывается корректно; общая прежняя оценка, полностью вытесненная совокупностью, удаляется). `_assign_evaluation` вызывает `assign_evaluation` один раз. Отображение доли (0,50 ПОЛЕЗЕН) — штатное через `evaluation_display`.
- Тесты: +2 (совокупность с долей; замена общей прежней оценки), правка теста диалога. `pytest tests` — **386 passed**; импорт GUI — OK.

### Исправление (2026-11-18) — падение превью импорта

- `gui/exchange_dialogs.py`: `_STATUS_TEXT` ранее переведён со словаря лямбд на строки, но в `ImportPreviewDialog` остался вызов `_STATUS_TEXT[...]()` → `TypeError: 'str' object is not callable` при открытии анализа импорта. Вызов убран.
- Добавлен тест `test_import_preview_dialog_renders_entries` (конструирование диалога, заполненность текста статусов, `excluded_keys`).
- `pytest tests` — **387 passed**; импорт GUI — OK.

### Исправление (2026-11-18) — анализ импорта: обязательные поля только при создании

- `import_service.ImportService._analyze_entry`: проверка пропущенных обязательных полей (`info["required"]`) выполняется только когда записи с таким PK нет в локальной базе (создание). Для изменения существующей записи достаточно наличия по первичному ключу — обязательные поля она уже содержит. Проверка зависимостей (FK/N-N) сохранена для обеих операций.
- Тест `test_analyze_archive_marks_entries` расширен: изменение существующей записи без обязательных полей → статус ok; контроль применения комментария.
- README («Экспорт и импорт изменений») уточнён. `pytest tests` — **387 passed**.

### Исправления (2026-11-19) — полный цикл обмена (tests/test_full_cycle.py)

По сценарию пользователя добавлен сквозной тест `tests/test_full_cycle.py`: ГО (GO.db, хранилище «Головной офис») со справочниками и 3 филиалами → экспорт справочников филиалам → филиалы (свои .db и хранилища) принимают справочники, генерируют данные (seed_branch, с файлами), выгружаются → ГО принимает, регистрирует и оценивает (seed_head_office), выгружает по филиалам → филиалы принимают. Успех: снапшоты материалов/телеграмм совпадают между узлами, конфликтов нет.

По пути исправлено четыре дефекта:
1. **Филиал не принимал входящие номера** — `_allowed_fields_for_update` блокировал `incoming_number`/`incoming_date` для роли филиала (конфликты `restricted_fields_skipped`). Ограничения сняты: филиал принимает от ГО и входящие номера, и оценки.
2. **Коллизия индексов источников** — каждый филиал нумеровал источники с SRC-0001 → UNIQUE-конфликт в базе ГО. `seed_branch._create_sources` теперь кодирует порядковый номер филиала в старших разрядах («SRC-2NNNN» для BR-002, 10 символов).
3. **Глобальная уникальность исходящих номеров** — `uix_material_outgoing`/`uix_telegram_outgoing` расширены колонкой `branch_id` (миграция `c3d4e5f6a7b8_outgoing_number_per_branch.py`; downgrade может отклоняться СУБДью на легальных данных — задокументировано). Иначе центральная база ГО с документами всех филиалов невозможна.
4. **Общая оценка на документы разных филиалов** — `_create_evaluations` группирует по датам без учёта филиала; при возврате в филиал член связи N-N с чужим документом недоступен → конфликт. `_apply_relationships` теперь пропускает недоступных членов связи с предупреждением (локально оценка привязывается к своему документу).
5. **Диалог редактирования** (`entity_edit_dialog._find_duplicate`): колонки уникального ограничения вне полей диалога берутся из записи/`fixed_branch_id`; фокус ошибки — первая колонка с редактором (branch_id редактора не имеет).

Проверка: `pytest tests` — **391 passed**; импорт GUI — OK; прогонка миграций до head (`c3d4e5f6a7b8`) — OK. README уточнён (уникальность исходящего номера — «в сочетании с датой и филиалом»).

### Дополнение (2026-11-19) — колонка «Задачи» в таблицах документов

- `orm/models.py`: свойство `ParticipantMixin.tasks_display` — коды научных задач документа через запятую (отсортированы); метки `tasks_display` → «Задачи» в `__field_labels__` материалов и телеграмм.
- `gui/application.py`: колонка `tasks_display` (width 140) в `material_columns`/`telegram_columns` перед входящими номерами — для обеих ролей.
- `core/domain_pack.default.json`: метки зеркалированы в секции `entities` (ScientificMaterial, Telegram).
- Сортировка по колонке — штатная: `_is_mapped_column` = false → сортировка в памяти (как у `evaluation_display`).
- Тест `test_tasks_display_lists_sorted_task_codes` (сортировка кодов, пустое значение). `pytest tests` — **392 passed**; импорт GUI — OK.

### Дополнение (2026-11-19) — обязательные поля «Страны» и «Сотрудники»

- `gui/edit_elements.py`: `ManyToManyEditElement` — параметр `required`, переопределены `is_required()` (явный флаг или метаданные) и `is_empty()` (пустой список = незаполнено). Штатная валидация `_on_save` даёт сообщение `msg_required_field`, метка получает жирный шрифт со «*».
- `gui/document_dialogs.py`: в спецификациях роли «филиал» `countries`/`employees` материалов и телеграмм — элементы с `required=True`. Для роли ГО обязательности нет (офис правит реквизиты документов филиалов и не обязан заполнять списки; иначе блокировались бы правки старых записей).
- `tests/seed_branch.py`: страны заполняются всегда (материалы 1-2, телеграммы 1), сотрудники — минимум один участник (`_pick_participants`).
- Тесты: `test_documents_always_have_countries_and_employees` (сидирование), `test_countries_and_employees_required_for_branch` и `test_countries_optional_for_head_office` (диалог). `pytest tests` — **395 passed**; импорт GUI — OK.


---

## Слияние с main (2026-11-19) — PR #12, #13, #14
- Подтянут `origin/main` (`354d763`) в `alex_develop`: fast-forward, конфликтов нет — main включал нашу ветку через PR #12.
- Новое из main (~5,5 тыс. строк, 35 файлов):
  - **вкладка «Дашборд»**: сводные KPI, диаграммы, списки;
  - **просмотр оценочных листов** в меню «Данные» (+ сервис оценок);
  - «Большой апдейт для импорта/экспорта»;
  - исправление поиска задач и обновления дерева ОШС;
  - новые тесты: `test_full_cycle.py`, `test_evaluation_service.py`, `test_evaluation_lists_dialog.py`, `test_seed_branch.py`, `test_seed_head_office.py` и др.
- Новых миграций и зависимостей нет; head без изменений (`f4c6a8d0e2b1`), демо-база актуальна.
- Наши доработки (синхронизация таблицы/диаграмм, вложенная круговая, док-панель, `AddedTask`, удаление `task_employees`) в main сохранены; адаптация не потребовалась.
- `pytest tests`: **395/395 passed**; импорт GUI — OK.


---

## Переработка панели сведений ОШС (2026-11-19)
### Минимальные размеры
- `gui/oshm_dialog.py`: минимальный размер окна 1040x640; у сплиттеров снят флаг сворачивания половин (`setChildrenCollapsible(False)`), минимальные ширины: деревья — 360 px, панель сведений — 620 px; минимальные высоты деревьев — 180 px.

### Аватарки элементов
- **Хранение без изменения схемы БД**: записей в базе нет — аватарка находится в директории «Аватарки» файлового хранилища по детерминированному имени `<тип узла>_<наименование>_<хвост id>.jpg` (однозначно интерпретируется; хвост id устраняет коллизии одноимённых элементов). Миграция `g5d7e9f1a3c4` и колонка `avatar_file` отменены (согласовано с пользователем).
- **Сервис `services/avatar_service.py`:** при добавлении изображение **переносится** (move) из указанного места в хранилище и приводится к 150x200 (cover-crop, JPEG q90); удаление — удаление файла; заглушка при отсутствии.
- **Панель:** аватарка 150x200 фиксированного размера слева вверху, под ней кнопки «+» (файловый диалог, фильтр изображений), «−» (с подтверждением), «Печать».

### Статистика элемента
- **Сервис `services/element_stats_service.py`:** документы элемента — по участию (сотрудник/отдел/группа как критерии статистики, филиал — по принадлежности); показатели за период: количество материалов/телеграмм (и по типам), распределение оценок (последняя оценка документа, как в статистике), коэффициент эффективности = средний вес оценок; `shift_period_year` — сдвиг периода на год.
- **Панель:** в центре — наименование с **коэффициентом эффективности: просто цифра справа от имени** (без подписи), ниже поля; справа — таблица оценок за период; низ — выбор периода (`PeriodSelectorWidget` как в статистике, дефолт — текущий месяц) и две трёхкольцевые диаграммы (`ElementDonutWidget`, `gui/oshm_element_charts.py`): внутри материалы по типам, среднее кольцо телеграммы по типам, снаружи оценки по значениям, в центре цифра количества материалов; левая — за выбранный период, правая — за аналогичный период прошлого года.
- **Печать:** `QPrinter` + стандартный диалог; панель печатается как изображение (grab, масштабирование с сохранением пропорций).

### Исправление миграции main (a1b2c3d4e5f6)
- Воспроизведён дефект на демо-данных: в `material_sources_new`/`telegram_sources_new` составной первичный ключ объявлен только по первой колонке — вставка связей падает с `UNIQUE constraint failed` (на пустой БД не проявляется). Исправлено: `primary_key=True` у `source_id` в обеих таблицах. Цепочка проверена на демо-базе до head `g5d7e9f1a3c4`.

### Проверка
- Новый `tests/test_oshm_avatar_stats.py` (9 тестов): сохранение/удаление/заглушка аватарки (размер файла 150x200), ошибка формата; показатели за период по сотруднику/отделу/филиалу, прошлогодний период, сдвиг периода; структура панели и минимальные размеры диалога.
- Секция `strings` пакета регенерирована (511 ключей, добавлены ключи аватарки/печати/коэффициента/таблицы оценок).
- `pytest tests`: **404/404 passed**; импорт GUI — OK; демо-база на head `g5d7e9f1a3c4`.


### Дополнение (2026-11-19, ночь) — диаграмма панели сведений по эскизу
- `gui/oshm_element_charts.py` — `ElementDonutWidget` перестроен по эскизу пользователя: в центре кольца — «ВСЕГО N» (материалы + телеграммы); «мантия» из двух пропорциональных секторов (телеграммы фиолетовые, материалы синие) с подписями «ТЕЛЕГР. — n» / «НАУЧ. МАТ. — n»; внешнее кольцо — сектора оценок внутри каждого класса документов (порядок секторов согласован с мантией: сначала оценки телеграмм, затем материалов), на секторах — только числа; названия оценок — цветная легенда внизу (фиксированные цвета: Б — серый, И — жёлтый, П — зелёный, В — красный); пустой период — «Нет данных» и нулевой центр.
- `services/element_stats_service.py`: `ElementPeriodStats` дополнен раздельными распределениями оценок по классам (`material_evaluation_counts`, `telegram_evaluation_counts`).
- Новые строки: `oshm_chart_total` («ВСЕГО»), `oshm_chart_materials` («НАУЧ. МАТ.»), `oshm_chart_telegrams` («ТЕЛЕГР.»); пакет регенерирован (513 ключей).
- Тесты: `test_donut_structure_example` — структура по числам из эскиза (8 телеграмм + 12 материалов, оценки 2/4/2 и 2/4/6), `test_donut_no_data`.
- `pytest tests`: **406/406 passed**; импорт GUI — OK.


---

## Алфавитный порядок значений N→N (2026-11-20)

### Таблицы вкладок «Научные материалы» и «Телеграммы»
- `gui/application.py`: форматтеры `_format_employees`, `_format_departments`, `_format_workgroups`, `_format_countries` сортируют значения по отображаемому тексту (`str.casefold`) перед объединением через запятую. Колонки «Задачи» (`tasks_display`, сортировка по коду) и «Адресация доклада» (`format_report_addresses`, сортировка по коду руководителя) были отсортированы и раньше — изменений не потребовали.

### Диалоги редактирования и диалог выбора («+»)
- `gui/edit_elements.py`: `ItemsPickerDialog` получил метод `_ordered_instances` — записи списка диалога выбора отображаются в алфавитном порядке отображаемых значений; `ManyToManyEditElement._refresh_list` использует тот же порядок для списка уже выбранных значений (задачи, страны, сотрудники). Таблица адресации доклада (`ReportAddressesEditElement`) сортируется по коду руководителя — алфавитный порядок, изменений не потребовало.

### Проверка
- Новые тесты в `tests/test_edit_dialog.py`: `test_many_to_many_list_sorted_alphabetically`, `test_items_picker_sorted_alphabetically`.
- `pytest tests`: **409/409 passed**; импорт GUI — OK. Изменений схемы БД и строк интерфейса нет.


---

## Сохранение сортировки таблиц документов (2026-11-20)

### Изменения
- `core/settings.py`: новые поля `material_sort` / `telegram_sort` (секция INI «Application»), формат — «колонка» (по возрастанию) или «колонка:desc» (по убыванию), пусто — сортировка не задана.
- `gui/table_model.py`: публичные аксессоры `sort_column()` / `sort_descending()` у `SqlAlchemyTableModel` (состояние по умолчанию — сортировка не задана, как и раньше).
- `gui/document_list_widget.py`: `sort_state()` — текущая сортировка (None, если пользователь не сортировал); `set_sort_state()` — применение сортировки по имени колонки через `sortByColumn` (False, если колонки нет в текущей роли).
- `gui/application.py`: хелперы `_format_sort_state` / `_parse_sort_state`; сохранение в `_save_ui_state` (при закрытии окна), восстановление в `_restore_ui_state` до применения фильтров; неизвестная колонка молча игнорируется.

### Проверка
- Новые тесты в `tests/test_window_state.py`: разбор формата, сохранение сортировки обеих таблиц, восстановление, игнорирование чужой колонки.
- `pytest tests`: **413/413 passed**; импорт GUI — OK. Миграции и строки интерфейса не затронуты.


---

## Фильтры «многие ко многим» в таблицах документов (2026-11-20)

### Поведение
- Для колонок «Страны», «Задачи», «Сотрудники», «Отделы», «Рабочие группы», «Адресация доклада» в диалоге «Добавить/Изменить фильтр» значение задаётся списком с кнопками «+»/«−» по аналогии с виджетами редактирования: «+» открывает `ItemsPickerDialog` (мультивыбор, алфавитный порядок, исключение уже выбранных), «−» удаляет выделенные элементы. Условие единственное — «содержит любое из» (логика ИЛИ по идентификаторам связанных записей).
- Строка условия в диалоге фильтров показывает имена связанных записей, а не идентификаторы.

### Изменения
- `gui/filter_model.py`: тип значения `m2m` (распознаётся по имени колонки из `M2M_COLUMN_NAMES`), оператор «содержит любое из» (`filter_op_m2m_in`), сопоставление `FilterCondition.matches` через пересечение множеств ключей (`m2m_actual_keys`: `id` или `leader_id`; строка кодов — для `tasks_display`), хелперы `parse_id_list`/`coerce_filter_ids` (приведение к UUID-ключам), `describe` с необязательным готовым `value_label`.
- `gui/table_model.py`: у `ColumnDef` новые необязательные параметры `filter_target` (класс связанной сущности) и `filter_attr` (атрибут для чтения связи — для вычисляемых колонок); модель определяет тип фильтра с учётом метаданных колонки и читает значение через `filter_attr`.
- `gui/filter_dialog.py`: `AddFilterDialog` и `FilterDialog` принимают `session`; редактор значения N→N (QListWidget + «+»/«−», переиспользуется `ItemsPickerDialog` и его алфавитная сортировка); восстановление выбранных записей при редактировании условия; `resolve_m2m_labels` для отображения имён в строках условий.
- `gui/application.py`: колонки материалов и телеграмм снабжены `filter_target`/`filter_attr` (Country, ScientificTask, Employee, Department, WorkingGroup, Leader).
- `gui/document_list_widget.py`: в `FilterDialog` передаётся сессия вкладки.
- `utils/string_resources.py`: новый ключ `filter_op_m2m_in`; секция `strings` пакета регенерирована (515 ключей).

### Проверка
- Новые тесты в `tests/test_filters.py` (10 шт.): распознавание типа, операторы, сопоставление (страны/адресация/строка кодов/пусто), сериализация roundtrip, сквозная фильтрация модели, редактор «+»/«−», загрузка условия на редактирование, имена в строке условия, UUID-приведение.
- `pytest tests`: **423/423 passed**; импорт GUI — OK. Схема БД не менялась.


---

## Импорт дельт в отдельном потоке с прогресс-диалогом (2026-11-20)

### Поведение
- Применение импортируемого ZIP-архива (после анализа и подтверждения в `ImportPreviewDialog`) выполняется в отдельном потоке; GUI не блокируется. Ход импорта показывает `QProgressDialog`: «Запись {current} из {total}: {entity}». По завершении — прежнее итоговое сообщение (импортировано/удалено/пропущено/конфликты, предупреждения пакета, запросы контрагенту) и обновление всех вкладок; при ошибке транзакция откатывается в воркере и показывается сообщение об ошибке.
- Анализ архива остаётся в GUI-потоке (быстрый, интерактивный предпросмотр).

### Изменения
- `importexport/import_service.py`: `ImportService` принимает `progress_cb` (как `ExportService`); `_apply_payload` планирует записи заранее и шлёт прогресс по каждой (готово/всего/имя сущности); обработчик необязателен, поведение без него не изменилось.
- `gui/exchange_dialogs.py`: новый `ImportWorker` (QObject + QThread-паттерн как у `ExportWorker`): сессия создаётся внутри потока, `import_archive` + `record_missing_requests` + commit, сигналы `progressed`/`succeeded`/`failed`.
- `gui/application.py`: `_import` разделён на анализ (GUI-поток, с обработкой ошибок) и `_run_import_worker` (поток + прогресс-диалог, ссылки на поток/воркер хранятся в атрибутах окна); итоговое сообщение собирается в `_on_import_finished`.
- `utils/string_resources.py`: ключи `progress_import_caption`, `progress_import_entry`; секция `strings` пакета регенерирована (517 ключей).

### Проверка
- Новый тест `test_import_archive_reports_progress` в `tests/test_branch_export.py`: сигналы прогресса по числу записей пакета, счётчик/итог/имя сущности, импорт без обработчика не изменился.
- `pytest tests`: **424/424 passed**; импорт GUI — OK. Схема БД не менялась.


---

## «Файлы последнего импорта» на дашборде (2026-11-20)

### Поведение
- На дашборде добавлен блок «Файлы последнего импорта»: файлы, восстановленные последней операцией импорта ZIP-дельт. Состав хранится в манифесте `last_import_files.json` (корень хранилища, относительные POSIX-пути), который `ImportService` перезаписывает после каждой успешной операции импорта.
- Список упорядочен по алфавиту имени файла; отсутствующие на диске — зачёркнутые.
- Фильтр по имени файла с regex (QRegularExpression, регистронезависимо; некорректный шаблон подсвечивает поле и ничего не скрывает).
- Двойной щелчок — открытие стандартным обработчиком ОС; drag&drop наружу отдаёт URL файлов (проводник копирует; перемещение не предлагается — DragOnly + CopyAction, приём дропа отключён).
- Контекстное меню: «Расположение файла» (explorer /select, как в attached_files_widget), «Переименовать» (диск + запись FileRecord при наличии + манифест; недоступно при множественном выборе), «Удалить файл» (с диска и из манифеста после подтверждения; записи документов сохраняются и далее отображаются как отсутствующие).

### Изменения
- `importexport/import_service.py`: `read_import_manifest`/`write_import_manifest`; `_extract_files` возвращает относительные пути восстановленных файлов; `import_archive` пишет манифест после коммита и возвращает их в результате (ключ `files`).
- `gui/imported_files_widget.py` (новый): `ImportedFilesWidget` — фильтр-regex, сортировка, открытие, drag-out, контекстное меню (переиспользованы `FileListWidget`, `_explorer_select_command`, `BROKEN_FILE_COLOR` из attached_files_widget).
- `gui/dashboard_widget.py`: параметр `storage_root`; третий блок нижнего ряда; `refresh()` обновляет и список файлов.
- `gui/application.py`: в `DashboardWidget` передаётся `storage_path_obj()`.
- `utils/string_resources.py`: ключи `dashboard_imported_files`, `dashboard_imported_filter_placeholder`, `dashboard_imported_empty`, `dashboard_imported_invalid_regex`, `action_delete_file`, `imported_files_delete_confirm`, `imported_files_error`, `files_rename_invalid`, `files_rename_exists`; секция `strings` пакета регенерирована (526 ключей).
- `docs/dashboard.md`: раздел 7.4.

### Проверка
- Новый `tests/test_imported_files_widget.py` (8 тестов): сортировка, regex-фильтр и некорректный шаблон, зачёркивание отсутствующих, MIME drag&drop, переименование (с записью БД и без), удаление, интеграция с дашбордом. В `tests/test_branch_export.py` — тест записи манифеста при импорте архива с файлами.
- `pytest tests`: **433/433 passed**; импорт GUI — OK. Схема БД не менялась.


---

## Очистка tmp_import после импорта (2026-11-20)

### Поведение
- Временная папка `tmp_import` в файловом хранилище удаляется после завершения операции импорта (и после анализа архива). Ранее удалялся только подкаталог сессии распаковки, а сам `tmp_import` оставался в хранилище.
- Перед распаковкой архива остатки прошлых запусков (в т.ч. прерванных) вычищаются целиком, чтобы мусор не копился.

### Изменения
- `importexport/import_service.py`: хелперы `_prepare_extract_dir` (чистая директория сессии, удаление остатков) и `_cleanup_extract_dir` (удаление директории сессии и пустого корня `tmp_import`); применены в `import_archive` и `analyze_archive`.

### Проверка
- Новый тест `test_import_removes_tmp_import_directory` в `tests/test_branch_export.py`: после `analyze_archive` и `import_archive` папки `tmp_import` нет, включая остатки «прерванного» запуска.
- `pytest tests`: **434/434 passed**; импорт GUI — OK.

## Распределение задач: фильтр распределённых и тип задачи (2026-11-21)

### Изменения
- `gui/task_distribution_widget.py`: кнопка `distributed_button` («Скрыть распределённые» / «Показать распределённые»). В скрытом режиме в средней и правой таблицах остаются только задачи, не назначенные ни одному потомку соответствующего узла.
- `gui/task_table_model.py`: вынесена `task_type_label(task)` — безопасно обрабатывает `ScientificTaskType`, строковый код и неизвестное значение, чтобы колонка «Тип» не оставалась пустой.
- `gui/oshm_details_panel.py`: в таблицу задач добавлена колонка «Тип» (5 колонок), используется общий `task_type_label`.
- `utils/string_resources.py` и `core/domain_pack.default.json`: добавлены строки фильтра и пустого результата, секция strings регенерирована (530 ключей).
- `README.md`: описание колонки «Тип» и кнопки «Скрыть/Показать распределённые».

### Проверка
- Новые тесты: `test_task_model_shows_type_column`, `test_distributed_toggle_filters_distributed_tasks`; в `test_details_panel_employee` проверяется колонка «Тип».
- `pytest tests/test_task_widget.py tests/test_oshm_dialog.py -q` — 32 passed.

### Дополнение (2026-11-21) — множественный выбор в распределении задач
- `gui/task_distribution_widget.py`: дерево переведено в `ExtendedSelection`; порядок выделения запоминается (`_selected_keys`, `_on_tree_current_item_changed`), ведущим считается первый выбранный узел. Правая таблица и подпись показывают задачи ведущего узла, средняя — задачи его вышестоящего элемента. Кнопка `>>>` и drag-and-drop назначают выбранные задачи всем выбранным узлам; неактивные/справочные узлы исключаются, при смешанном выборе выводится предупреждение.
- `utils/string_resources.py`: строка `task_assign_invalid_nodes`; секция strings пакета перегенерирована (531 ключ).
- `tests/test_task_widget.py`: тест `test_tree_multi_selection_assigns_to_all_and_right_shows_first` (Ctrl-подобное выделение двух отделов, назначение одной задачи обоим, правая таблица ведущего узла).
- Проверка: `pytest tests/test_task_widget.py` — 7 passed; полный `pytest tests -q` — 437 passed, 1 warning zipfile.
- `README.md`: описан множественный выбор и ведущий узел.

### Дополнение (2026-11-21) — ширина столбцов и краткий тип задачи
- `gui/task_table_model.py`: `task_type_label()` теперь возвращает краткий код (`ОЗ`/`ДЗ`); полная метка сохранена в `task_type_full_label()` и используется для поиска и сортировки, поэтому поиск по «основная»/«дополнительная» продолжает работать.
- `gui/task_distribution_widget.py`, `gui/oshm_details_panel.py`: вместо `QHeaderView.Stretch` для колонки «Наименование» все секции переведены в `Interactive`, последняя колонка растягивается; граница «Наименование»/«Тип» снова перетаскивается.
- `tests/test_task_widget.py`, `tests/test_oshm_dialog.py`: ожидания краткого типа и проверка режима изменения ширины.
- Проверка: целевые тесты 33 passed; полный `pytest tests -q` — 437 passed, 1 warning zipfile.

### Дополнение (2026-11-21) — адаптивный дашборд без нижних блоков
- `gui/dashboard_widget.py`: удалены «Последние документы», «Требуют внимания», блок файлов последнего импорта и KPI последнего импорта; `QScrollArea` убран, вкладка целиком помещается в окно.
- Добавлен адаптивный масштаб 0,72–1,35: `KpiCard.set_scale()` меняет шрифты/отступы/высоту плиток, `DashboardWidget._apply_scale()` пересчитывает масштаб при `resizeEvent` и перерисовывает диаграммы; подписи месяцев наклонены, чтобы не перекрываться.
- Переключатель «Материалы/Телеграммы» вынесен над диаграммами; «Документы по месяцам» и «Структура по типам» начинаются на одной линии.
- `gui/application.py`: `DashboardWidget` больше не получает `storage_root`.
- `tests/test_dashboard.py`: проверки 3 KPI для ГО, отсутствия `QScrollArea` и роста шрифта при увеличении окна; тест блока файлов импорта на дашборде удалён.
- `docs/dashboard.md`, `README.md` приведены к фактической компоновке.
- Проверка: целевые тесты 33 passed; полный `pytest tests -q` — 437 passed, 1 warning zipfile.

### Дополнение (2026-11-21) — дашборд: названия, оценки и фильтр финансового года
- `gui/dashboard_widget.py`: карточка оценок названа «Оценки», рейтинг — «Эффективность филиалов/отделов»; на диаграмме оценок короткие подписи Б/И/П/В, над столбцами количество и доля от общего числа, цвета от красного (Б) к зелёному (В) через `QStackedBarSeries` и подписи `QGraphicsSimpleTextItem`.
- Верхние/нижние отступы KPI-карточек уменьшены с 10 до 5 px (в масштабе).
- Кнопка «Обновить» перенесена в начало панели фильтров; справа показывается текущая дата и день недели.
- «Финансовый год» включён по умолчанию и подсвечивается; при переходе к календарному году подсветка снимается.
- `reports/dashboard_service.py`: `evaluation_counts` отдаёт короткие коды оценок.
- `utils/string_resources.py` и `core/domain_pack.default.json` — 531 ключ, секция strings регенерирована.
- `tests/test_dashboard.py` — проверки финансового года по умолчанию, даты, названий, цветов оценок, отступов карточек; 6 passed.
- `README.md`, `docs/dashboard.md` обновлены.
- Проверка: полный `pytest tests -q` — **437 passed**, 1 warning zipfile; native-скриншоты 1024×720 и 1400×900.

### Дополнение (2026-11-21) — дашборд: шрифты и вложенный рейтинг
- `gui/dashboard_widget.py`: базовые размеры шрифтов KPI-карточек — название 12 pt, пояснение 11 pt, значение 24 pt; минимальная высота диаграмм увеличена со 120 до 150 px. Переключатель «Материалы/Телеграммы» перенесён в панель фильтров, уменьшены внешние отступы и расстояние между блоками, за счёт чего выросла полезная высота диаграмм.
- `reports/dashboard_service.py`: в `DashboardData` добавлено `ranking_children`; для головного офиса — отделы филиала, для филиала — сотрудники отдела (до пяти лучших).
- `gui/dashboard_widget.py`: в рейтинге внутри основного столбца рисуются вложенные столбцы следующего уровня; их высота пропорциональна количеству и не превышает основной, внутри — краткое наименование, над основным столбцом — числовой коэффициент. Заголовок рейтинга зависит от разреза: «Эффективность филиалов» / «Эффективность отделов».
- `utils/string_resources.py`: раздельные заголовки рейтинга; секция strings пакета регенерирована (531 ключ).
- `tests/test_dashboard.py`: проверки `ranking_children`, динамического заголовка, шрифтов 12/11/24 и минимальной высоты диаграмм; 6 passed.
- `README.md`, `docs/dashboard.md` обновлены.
- Проверка: полный `pytest tests -q` — 437 passed, 1 warning zipfile; native-скриншоты 1024×720 и 1400×749.

### Дополнение (2026-11-21) — рейтинг: подписи, контраст и дата
- `gui/dashboard_widget.py`: подписи вложенных столбцов рейтинга повёрнуты вертикально, прижаты к нижнему краю столбца и центрированы по его ширине; шрифт подписи увеличен на 2 pt.
- Основной столбец рейтинга сделан светлым (`ACCENT_SOFT`) с рамкой, вложенные — насыщенными тёмными цветами; контраст между уровнями усилен.
- Дата и день недели в панели фильтров увеличены на 10 pt и выделены жирным; ширина окна 1024 px по-прежнему помещается за счёт уплотнения отступов.
- `tests/test_dashboard.py`: добавлена проверка размера и жирности шрифта даты.
- `README.md`, `docs/dashboard.md` обновлены.
- Проверка: `pytest tests/test_dashboard.py` — 6 passed; полный `pytest tests -q` — 437 passed, 1 warning zipfile.

### Дополнение (2026-11-22) — дашборд: оценённые документы, доклады и выполненные задачи
- `reports/dashboard_service.py`: новые поля `DashboardData` — `evaluated_materials`, `evaluated_telegrams`, `materials_without_evaluation`, `reported_count`, `report_type_counts`, `undelivered_count`, `tasks_completed`, `tasks_uncompleted`, `tasks_due_soon`; `KpiValue.attention`.
- Формулы: «Оценено документов» = оценённые материалы + оценённые телеграммы, процент — от суммы всех материалов и оценённых телеграмм; «Доложено телеграмм» — телеграммы с `report_type`, разбивка по кодам; «Выполнено задач» — задачи с `end_date` раньше текущей даты, процент от общего числа задач периода; предупреждения — неоценённые материалы, недоложенные телеграммы, задачи со сроком в ближайшие 30 дней.
- `gui/dashboard_widget.py`: `KpiCard.attention_label` с треугольным значком; высота карточек 96–150 px; шрифт подписей осей увеличен на 2 pt; дата и день недели в две строки, жирные, с отступом; подписи вложенных столбцов рейтинга — белая заливка с чёрным контуром; на тёмной теме основной столбец `#4F6B92`, вложенные — яркая палитра.
- `utils/string_resources.py`: ключи `dashboard_unevaluated_materials`, `dashboard_reported`, `dashboard_undelivered`, `dashboard_completed_tasks`, `dashboard_completed_detail`, `dashboard_due_soon`; секция strings пакета — 537 ключей.
- `tests/test_dashboard.py`: 5 карточек HO / 6 филиал, значения и предупреждения, разбивка докладов, выполненные/невыполненные/срок, контур подписей; 8 passed.
- `README.md`, `docs/dashboard.md` обновлены.
- Проверка: полный `pytest tests -q` — 440 passed, 1 warning zipfile.

### Дополнение (2026-11-22) — дашборд: типы задач и подписи рейтинга
- `gui/dashboard_widget.py`: шрифт подписей вложенных столбцов рейтинга увеличен с 8 до 10 pt (с учётом масштаба), подписи остаются белыми с чёрным контуром и центрируются по ширине столбца.
- `reports/dashboard_service.py`: в `DashboardData` добавлены `task_type_counts` и `completed_task_type_counts`; `_task_type_counts()` отдаёт коды ОЗ/ДЗ.
- `_task_stats()`: в головном офисе задача распределена при наличии назначения на регион, в филиале — при наличии назначения на сотрудника; исправлено двойное суммирование в ветке филиала.
- Карточка «Задачи»: общее количество, разбивка по типам, предупреждение «Не распределено: N». Карточка «Выполнено задач»: количество и процент от общего числа задач, разбивка выполненных по типам, предупреждение «Не выполнено: N».
- `utils/string_resources.py`: `dashboard_unassigned_tasks`, `dashboard_uncompleted_tasks`; секция strings пакета — 539 ключей.
- `tests/test_dashboard.py`: обновлены ожидания карточек, добавлен тест `_task_stats` для ГО/филиала; 10 passed.
- `README.md`, `docs/dashboard.md` обновлены.
- Проверка: полный `pytest tests -q` — 441 passed, 1 warning zipfile.

### Дополнение (2026-11-22) — дашборд: карточка даты и «Выполнение задач»
- `gui/dashboard_widget.py`: дата и день недели вынесены в отдельную карточку в стиле KPI (`QFrame#dashboardCard`), одна строка, шрифт base+5, жирный.
- Удалён переключатель «Материалы/Телеграммы» и круговая «Структура по типам»; вместо неё — диаграмма «Выполнение задач»: по филиалам (ГО) или отделам (филиал), два столбца (назначено/выполнено), сегменты ОЗ/ДЗ с контрастными цифрами, процент выполнения над группой, оси как у эффективности.
- `reports/dashboard_service.py`: `TaskExecution`, `DashboardData.task_execution`, `_task_execution()` (назначенные/выполненные по ОЗ/ДЗ, цели — филиалы или отделы филиала).
- Подписи над столбцами оценок увеличены на 3 pt.
- `utils/string_resources.py`: `dashboard_chart_execution`, `dashboard_assigned`, `dashboard_completed`; секция strings пакета — 542 ключа.
- `tests/test_dashboard.py`: тесты `task_execution`, сегментов диаграммы, даты одной строкой; 12 passed.
- `README.md`, `docs/dashboard.md` обновлены.
- Проверка: полный `pytest tests -q` — 443 passed, 1 warning zipfile.

### Дополнение (2026-11-22) — дашборд: надпись финансового/календарного года
- Кнопка переключения теперь показывает выбранный диапазон: «Фин. год (окт 2026-сен 2027)» для финансового года и «Календ. год (янв-дек 2026)» для календарного; текст обновляется при смене года и переключателя.
- Удалена отдельная строка с описанием выбранного периода; карточка даты перенесена на отдельную строку под фильтрами, справа.
- `utils/string_resources.py`: `dashboard_financial_button`, `dashboard_calendar_button`; секция strings пакета — 544 ключа.
- `tests/test_dashboard.py`: проверки обеих надписей и переключения; 12 passed.
- `README.md`, `docs/dashboard.md` обновлены.
- Проверка: полный `pytest tests -q` — 443 passed, 1 warning zipfile.

### Дополнение (2026-11-22) — легенда диаграммы «Выполнение задач»
- Под диаграммой добавлена легенда: «ОЗ — Назначено», «ДЗ — Назначено», «ОЗ — Выполнено», «ДЗ — Выполнено»; цвета совпадают с сегментами, выполненные — светлее.
- Реализовано через скрытую серию-легенду QBarSeries; основная серия в легенду не попадает.
- `README.md`, `docs/dashboard.md` дополнены; `tests/test_dashboard.py` проверяет видимость и набор подписей легенды.
- Проверка: `tests/test_dashboard.py` — 12 passed; полный прогон — ниже.

### 2026-11-22 — Дашборд: уведомления и сохранение в DOCX
- В `gui/dashboard_widget.py` добавлены карточка «Уведомления» с бегущей строкой
  (`TickerLabel`), карточка даты фиксированной ширины и кнопка «Сохранить».
- Уведомления: неэкспортированные записи, дата последнего экспорта, задачи с
  истекающим сроком, просроченные задачи; дополнительно — неоценённые материалы,
  недоложенные телеграммы, нераспределённые задачи и ошибки импорта.
- `reports/dashboard_service.py`: `DashboardData.last_export`,
  `DashboardService(..., storage_root=None)`, поиск самого свежего файла в каталоге
  экспорта.
- Сохранение в DOCX: заголовок, период, дата, таблица KPI, уведомления и четыре
  диаграммы как изображения; диалог выбора файла, сообщения об ошибках.
- `utils/string_resources.py`: ключи уведомлений и сохранения; секция strings — 567 ключей.
- `tests/test_dashboard.py`: тикер, фиксированная ширина даты, DOCX с четырьмя
  изображениями; 14 passed.
- Проверка: полный `pytest tests -q` — 445 passed, 1 warning zipfile.
- Отложено: отдельного просмотрщика сохранённых отчётов нет.

### 2026-11-22 — Задачи: сохранение распределения филиала
- В филиале вместо кнопки «Выгрузить задачи по регионам...» показывается
  «Сохранить распределение задач»; головной офис по-прежнему видит выгрузку по регионам.
- Добавлена выгрузка XLSX: № п/п, код задачи, наименование, даты начала и завершения,
  отдел, сотрудники. Одна строка — задача × отдел; задачи без распределения
  сохраняются с пустыми отделом и сотрудниками; учитываются только отделы
  выбранного филиала.
- `importexport/task_export.py`: `branch_tasks`, `write_branch_distribution`,
  `default_distribution_filename`, `DISTRIBUTION_HEADERS`.
- `gui/task_distribution_widget.py`: кнопка `save_distribution_button`, метод
  `_save_distribution`, диалог сохранения, имя по умолчанию.
- `utils/string_resources.py`: ключи `task_save_*`; секция strings — 573 ключа.
- `tests/test_task_widget.py`: экспорт распределения по отделам/сотрудникам и
  видимость кнопок для ролей; 9 passed.
- Проверка: `pytest tests/test_task_widget.py -q` — 9 passed.

### 2026-11-22 — Дашборд: возврат блока файлов последнего импорта (таблица)

Виджет, удалённый в `e4192e4`, возвращён на дашборд и переработан: список
заменён таблицей, данные берутся из базы, манифест хранит первичные ключи.

- `importexport/import_service.py`: `last_import_files.json` теперь хранит
  строковые UUID записей `FileRecord` (раньше — относительные пути);
  `_extract_files` возвращает ключи восстановленных записей; файлы без записи
  (резервное размещение) в манифест не попадают; записи старого формата
  виджет игнорирует.
- `gui/imported_files_widget.py` (переписан): `QTableView` + модель
  `ImportedFilesTableModel` (4 колонки: «Имя файла» со значком
  `QFileIconProvider`, «Филиал», «Тип документ», «Номер и дата исходящего»
  в формате «{number} от {date}»; данные колонок — из документа файла,
  последнего по дате исходящего). Фильтр — `QSortFilterProxyModel`
  (подстрока без regex по всем колонкам). Drag-out отдаёт URL файлов,
  двойной щелчок открывает файл, контекстное меню «Расположение файла» /
  «Переименовать» / «Удалить файл»; переименование меняет файл на диске
  и запись БД (манифест не меняется), удаление убирает файл с диска и ключ
  из манифеста; отсутствующие файлы — зачёркнутыми.
- `gui/dashboard_widget.py`: блок внизу под диаграммами только для роли
  головного офиса при заданном `storage_root`; обновляется в `refresh()`.
  `gui/application.py` не менялся — `storage_path_obj()` уже передавался.
- `utils/string_resources.py`: новые ключи `dashboard_imported_col_*`,
  `dashboard_imported_outgoing_full`, плейсхолдер поиска — «Поиск по таблице»;
  ключ `dashboard_imported_invalid_regex` удалён (regex больше не нужен);
  секция strings пакета регенерирована (577 ключей).
- `docs/dashboard.md`: схема компоновки, раздел 4.1 с описанием блока,
  архитектура и проверка.
- `tests/test_imported_files_widget.py` (переписан, 11 тестов): сортировка,
  данные колонок из БД, поиск по всем колонкам (включая литеральный «[»),
  зачёркивание отсутствующих, MIME drag&drop без дублей, переименование
  (диск + БД, манифест неизменен), удаление, пустой и устаревший манифесты,
  наличие блока только у дашборда ГО. `tests/test_branch_export.py`:
  манифест теперь сверяется с UUID записи `FileRecord`.
- Проверка: полный `pytest tests -q` — 450 passed, 1 warning zipfile;
  импорт GUI — OK. Схема БД не менялась, миграция не нужна.

### 2026-11-22 — Сидирование ГО, первоначальная загрузка филиала из архива

- `tests/seed_reference.py` (новый): справочники головного офиса на пустой
  базе — 5 территориальных единиц × 2 филиала, 30–40 стран, 4 научных
  звания, 10 потребителей, 5 руководителей, 60 научных задач
  (20 × 01.01.2025–31.12.2025, 20 × 01.01.2026–31.12.2026,
  10 × 01.10.2025–30.09.2026, 10 × с 01.10.2025 без окончания;
  `build_task_periods` с весами долей). Каждая задача назначена одному
  филиалу через `AddedTask` (перемешивание + round-robin: ровно по 6).
  Отказывается работать на непустой базе без `--clear`.
- `importexport/branch_import.py` (новый): первоначальная загрузка филиала —
  `read_archive_branches` (филиалы из export.json), `exclude_set_for_branch`
  (атрибуция по содержимому архива зеркалит `branch_scope`: справочники
  целиком, документы/отделы по `branch_id`, группы/сотрудники через
  отделы, оценки/файлы/источники/адресации через связи документов,
  AddedTask — только выбранному филиалу и его узлам), `run_initial_import`
  (ImportService с exclude).
- `importexport/branch_scope.py`: `AddedTask` исключён из `REFERENCE_ENTITIES`
  — добавлена атрибуция по узлу назначения (филиал напрямую, регион —
  всем филиалам региона, отдел/группа/сотрудник — через филиал узла).
  Раньше чужие назначения попадали в каждый архив и валидатор импорта
  отклонял их конфликтом.
- `gui/first_run_wizard.py`: на странице роли при пустой базе блок
  «Первоначальная загрузка из архива головного офиса» (Обзор → филиалы
  архива в Combobox, ручной ввод остаётся); `run_first_run_wizard`
  возвращает пару (настройки, `InitialBranchImport`).
  `gui/application.py`: импорт выбранного филиала выполняется после
  создания таблиц, до открытия главного окна; ошибка — предупреждение.
- `tests/seed_branch.py`: справочники (территориальные единицы, филиалы,
  страны, звания, потребители, руководители, задачи) больше не
  генерируются — читаются из базы (должны быть импортированы из архива
  ГО); филиал не создаётся (`_resolve_branch` ищет среди загруженных).
  Добавлено каскадное распределение задач филиала по действующим отделам
  (минимум одному), случайным подмножествам рабочих групп и
  действующим сотрудникам групп; нераспределённых не остаётся
  (кроме случая без действующих отделов — фиксируется в статистике);
  повторный прогон идемпотентен.
- `utils/string_resources.py`: ключи `wizard_archive_*`; секция strings
  пакета регенерирована (585 ключей).
- Тесты: `tests/test_seed_reference.py` (6), `tests/test_branch_import.py`
  (4), `tests/test_first_run_wizard.py` (+4), `tests/test_seed_branch.py`
  (7), `tests/test_branch_export.py` (+1 атрибуция AddedTask),
  `tests/test_full_cycle.py` переведён на `seed_reference`,
  `tests/test_seed_head_office.py` — фикстура создаёт справочники ГО.
- Проверка: полный `pytest tests -q` — 474 passed, 1 warning zipfile;
  импорт GUI — OK. Сквозной сценарий вручную: seed_reference → экспорт
  ГО для BR-001 → первоначальная загрузка (added_tasks 6, конфликтов 0,
  Change не осталось) → seed_branch (38 назначений по ОШС, 0
  нераспределённых). Схема БД не менялась.

### Дополнение (2026-11-22) — seed_reference: 240 задач с пересечениями

- `tests/seed_reference.py`: `--tasks` по умолчанию 240; каждая задача
  назначается 1–3 филиалам (`TASK_BRANCH_COUNT`, случайные подмножества
  с пересечениями — в среднем ~48 задач на филиал). Исправлен крах
  `random.sample` при числе филиалов меньше верхней границы диапазона
  (`k=min(len(branches), ...)`): тесты с 1–2 филиалами падали
  «Sample larger than population».
- Тесты: `test_seed_reference.py` переписаны под пересечения (1–3
  назначения на задачу, >= 120 общих задач), периоды проверяются на
  наборе из 60 задач.
- Пройден полный тестовый сценарий на рабочих файлах (старые GO.db и
  FIL.db пользователь заранее переместил в Backups; каталоги хранилищ
  очищены):
  1. `GO.db` + `Файловое хранилище/ГО`: `seed_reference --seed 42`
     (5 ТЕ, 10 филиалов, 40 стран, 4 звания, 10 потребителей,
     5 руководителей, 240 задач, 462 назначения).
  2. Экспорт ГО для BR-001 (`ExportService.export_for_branches`): архив
     содержит все справочники + 41 назначение задач филиалу.
  3. `FIL.db` + `Файловое хранилище/FIL`: первоначальная загрузка
     (`branch_import.run_initial_import`): 355 записей, 0 конфликтов,
     Change не осталось; `seed_branch --branch Ф-1` (10 отделов, 5 групп,
     15 сотрудников, 190 каскадных назначений, 0 нераспределённых,
     25 материалов, 26 телеграмм, 7 файлов).
  4. Экспорт филиала → импорт в ГО: 312 записей, 0 конфликтов; файлы
     вложений восстановлены в хранилище ГО.
  5. `seed_head_office`: входящие номера у всех документов, все материалы
     оценены (4 оценки по правилам групп), 1 список оценок, даты 37
     адресатам докладов.
- Проверка: полный `pytest tests -q` — 474 passed, 1 warning zipfile.

### Дополнение (2026-11-22) — персональный экспорт справочников, выбор периода в «Задачах», seed_branch без --branch

- `importexport/branch_scope.py`: `reference_keys_for_branch()` — ключи
  персональных справочников филиала (его `Branch`, его
  `TerritorialUnit`, задачи, назначенные филиалу/его региону и задачи
  документов филиала).
- `importexport/export_service.py`: `export_for_branches` кладёт в архив
  филиала общие справочники целиком, а территориальную единицу, запись
  филиала и научные задачи — только персональные
  (`_reference_changes_for_branch`); нужные записи, чьи изменения уже
  поглощены прошлыми экспортами, дозабираются из журнала Change
  (иначе новый филиал не получил бы записи, ссылаемые свежими
  назначениями).
- `importexport/branch_import.py`: при первоначальной загрузке
  принимаются также региональные назначения задач (регион филиала).
- `gui/task_distribution_widget.py`: вкладка «Задачи» по умолчанию
  открывает текущий финансовый год, а не самый поздний из списка
  (раньше при сидированных задачах 2025–2026 вкладка открывалась на
  пустом 2027–2028 — назначения были невидимы). Поиск периода вынесен в
  `_period_index`: `QComboBox.findData` не сравнивает объекты Python по
  равенству (прежний выбор периода фактически не восстанавливался).
- `tests/seed_branch.py`: параметр `--branch` удалён — филиал берётся
  из базы (единственный; при нескольких — ошибка с перечнем).
- Тесты: + `test_export_for_branches_scopes_personal_references`,
  дозабор поглощённых изменений проверен в
  `test_export_for_single_branch_keeps_other_branch_pending`;
  `test_full_cycle` — в базах филиалов по одному филиалу и одной ТЕ;
  вызовы `seed_branch` без `--branch`.
- Сценарий на рабочих файлах пройден заново: архив ГО для BR-001 —
  только его ТЕ/запись/41 задача (общие справочники целиком); FIL.db —
  1 филиал, 1 ТЕ, 41 задача, 41 назначение; вкладка «Задачи» на FIL.db
  открывается на 2025–2026 и показывает 25 задач филиала (по фильтру
  финансового года); экспорт филиала → ГО (313, 0 конфликтов) →
  регистрация и оценки ГО.
- Проверка: полный `pytest tests -q` — 474 passed, 1 warning zipfile.

### Дополнение (2026-11-22) — док прикреплённых файлов стал перемещаемым

- `gui/attached_files_widget.py`: `setAllowedAreas(Qt.AllDockWidgetAreas)`,
  features — Closable | Movable | Floatable (раньше только справа и без
  перетаскивания, поэтому панель было не сдвинуть с места).
- `gui/application.py`: `_save_files_dock_state` сохраняет реальную
  область (`dockWidgetArea`), признак плавания и геометрию плавающего
  окна; `_restore_files_dock_state` восстанавливает их, при мусоре в
  области — откат на правую.
- Тесты `tests/test_window_state.py`: заменён блок «фиксированное
  положение» — перемещаемость, сохранение/восстановление области,
  откат при невалидной области, устойчивость к мусорной геометрии.
- Проверка: полный `pytest tests -q` — 476 passed, 1 warning zipfile;
  импорт GUI — OK.

### Дополнение (2026-11-22) — раскладка колонок таблиц документов

- `gui/document_list_widget.py`: заголовок таблицы получил
  `setSectionsMovable(True)` — перетаскивание колонок мышью (порядок),
  сортировка по щелчку сохраняется; правый щелчок по заголовку открывает
  меню видимости колонок с галочками (`_build_header_menu`,
  `_header_context_menu`, `_set_column_visible`; последнюю видимую
  колонку скрыть нельзя). Добавлены `columns_layout()`/
  `set_columns_layout()` — сериализация «имя:ширина:видимость» в
  визуальном порядке (порядок + ширина + видимость).
- `core/settings.py`: новые поля `material_columns_layout` /
  `telegram_columns_layout`; старые `*_column_widths` сохранены как
  запасной формат (читаются, только если раскладки нет).
- `gui/application.py`: `_save_ui_state` пишет раскладки обеих таблиц,
  `_restore_ui_state` применяет их, при отсутствии — legacy-ширины.
- Тесты `tests/test_window_state.py` (+4): меню заголовка, переключение
  видимости с защитой последней колонки, roundtrip сериализации,
  сохранение/восстановление раскладки через настройки.
- Проверка: полный `pytest tests -q` — 480 passed, 1 warning zipfile;
  импорт GUI — OK.

### Дополнение (2026-11-22) — сидирование: потребитель обязателен, задачи распределены без остатка

- `tests/seed_head_office.py`: при регистрации ГО заполняет пустое поле
  «Потребитель» у материала (раньше оставалось пустым, если филиал его
  не указал при создании документа).
- `tests/seed_branch.py`: `_create_branch_structure` гарантирует
  распределяемость ОШС — в каждом отделе есть действующий сотрудник и
  действующая рабочая группа, у каждой группы — действующий участник;
  `_distribute_branch_tasks` опускает каждую задачу минимум до одной
  группы каждого выбранного отдела и минимум до одного сотрудника
  каждой выбранной группы. Нераспределённых задач внутри филиала и
  отделов не остаётся.
- `tests/test_full_cycle.py` — полный прогон а–г: (а) ГО — справочники
  и экспорт в филиал; (б) филиал — импорт, сидирование (все задачи
  распределены по ОШС), экспорт в ГО; (в) ГО — импорт, входящие номера
  и оценки, экспорт в филиал; (г) филиал — импорт оценок и входящих
  номеров. Новые проверки: потребитель заполнен у всех материалов,
  `test_cycle_distributes_all_tasks` — каждая задача филиала опущена до
  отделов, групп и сотрудников (равенство наборов на всех уровнях).
- `tests/test_seed_branch.py`: каскадные равенства наборов задач
  (отделы == группы == сотрудники), новый тест гарантий структуры
  `test_generated_structure_guarantees_distributability`.
- Рабочие файлы: FIL.db занят запущенным приложением (запись 21:46),
  бэкап и пересоздание только для GO.db: свежие справочники + архив
  для BR-001 в «Файловое хранилище/ГО/Экспорт» (шаг «а» готов к прогону
  «б–г» после закрытия приложения).
- Проверка: полный `pytest tests -q` — 482 passed, 1 warning zipfile;
  импорт GUI — OK.

## 2026-11-22 — Кастомная шапка главного окна

### Изменения
- `gui/custom_title_bar.py`: добавлены безрамочная шапка, перетаскивание за
  заголовок, двойное нажатие для разворачивания, кнопки свернуть,
  развернуть/восстановить и закрыть; изменение размера на Windows использует
  `WM_NCHITTEST`, на остальных платформах — системный механизм Qt.
- `gui/application.py`: `MainWindow` подключён к кастомной шапке; иконка
  разворачивания обновляется при смене темы.
- `gui/icons/window-*.png`: перенесены три предоставленные пользователем иконки;
  `pyproject.toml` включает PNG в данные пакета.
- `gui/application.qss`: шапка и кнопки оформлены общей палитрой светлой и
  тёмной тем.
- `utils/string_resources.py`, `core/domain_pack.default.json`: добавлены
  локализуемые подсказки кнопок окна; секция `strings` регенерирована.
- `tests/test_window_state.py`, `tests/test_theme.py`: проверены безрамочный
  режим, состав шапки, иконки, разворачивание и QSS обеих тем.
- `README.md`: описано управление окном с кастомной шапкой.

### Проверка
- Целевые тесты окна и тем — 34 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 450 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application` и `compileall` выполнены
  успешно; `git diff --check` ошибок не выявил.

### Отложено
- Нет.

## 2026-11-22 — Кастомная шапка всех окон приложения

### Изменения
- `gui/custom_title_bar.py`: добавлен глобальный установщик, который при
  создании оформляет все `QDialog`, резервирует место над содержимым,
  синхронизирует заголовок и состояние разворачивания, подключает
  перетаскивание и изменение размера.
- Механизм применяется к обычным диалогам, прогресс-окнам, мастеру первого
  запуска, сообщениям и Qt-окнам выбора файлов. Для аварийно несовместимых с
  `FramelessWindowHint` системных классов в тестовом offscreen-плагине действует
  защитное исключение; в обычных GUI-сеансах Windows/AstraLinux они оформляются.
- `gui/application.py`: установщик подключается до запуска мастера первого
  запуска; нативные файловые диалоги отключены через
  `AA_DontUseNativeDialogs`, чтобы их оформление совпадало с приложением.
- `gui/application.qss`: добавлены стили шапки и заголовка вторичных окон для
  обеих тем.
- `tests/test_window_state.py`, `tests/test_theme.py`: проверены обычные и
  прогресс-диалоги, резервирование места, смена заголовка, разворачивание,
  системные типы окон и QSS.
- `README.md`: описано единое оформление всех окон.

### Проверка
- Целевые тесты окна и тем — 40 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 456 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

## 2026-11-22 — Золотоватые заголовки окон

### Изменения
- `gui/theme.py`: добавлен общий цвет `TITLE_TEXT`: `#9A6B00` для светлой темы и
  `#D8B45A` для тёмной темы.
- `gui/application.qss`: заголовки главного и вторичных окон переведены на цвет
  `TITLE_TEXT`; остальные элементы палитры не изменялись.
- `tests/test_theme.py`: добавлена проверка оттенков и их подстановки в итоговый QSS.
- `README.md`: описано цветовое выделение заголовков в обеих темах.

### Проверка
- Целевые тесты окна и тем — 40 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 456 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

## 2026-11-22 — Изменение размера безрамочных окон

### Изменения
- `gui/custom_title_bar.py`: обработчик границ показывает горизонтальные,
  вертикальные и диагональные системные курсоры; перетаскивание работает для
  главного окна и всех диалогов.
- Если оконная система не поддерживает `startSystemResize`, используется
  ручное изменение геометрии с соблюдением минимального и максимального размера.
- `tests/test_window_state.py`: проверены все типы курсоров границ и резервное
  изменение геометрии.
- `README.md`: описано изменение размера безрамочных окон мышью.

### Проверка
- Целевые тесты состояния окон — 30 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 458 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

## 2026-11-22 — Изменение размера главного окна

### Изменения
- `gui/custom_title_bar.py`: явный обработчик курсоров и resize подключён к
  главному окну в Windows и остальных ОС, поэтому работа не зависит только от
  реакции системы на `WM_NCHITTEST`.
- Обработчик устанавливается локально на окно и его дочерние виджеты вместо
  глобального фильтра `QApplication`; новые дочерние элементы подключаются
  автоматически.
- `tests/test_window_state.py`: проверено наличие обработчика у главного окна и
  определение его правой границы и верхнего левого угла.

### Проверка
- Целевые тесты состояния окон — 30 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 458 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

## 2026-11-22 — Исправление управления главным окном

### Изменения
- `gui/custom_title_bar.py`: свободная область `QMenuBar` подключена к
  перемещению и двойному щелчку; пункты меню и кнопки управления не
  перехватываются.
- Перемещение начинается через `startSystemMove` только после движения мыши,
  поэтому двойной щелчок стабильно разворачивает и восстанавливает окно;
  добавлен ручной режим с захватом мыши.
- Для resize координаты вычисляются через `mapToGlobal`, а конфликтующий
  Windows hit-test отключается при наличии Qt-обработчика.
- `tests/test_window_state.py`: событиями мыши проверены перемещение главного
  окна, двойной щелчок и resize-курсор на правой границе.

### Проверка
- Целевые тесты состояния окон — 33 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 461 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

## 2026-11-22 — Стрелки всех выпадающих списков

### Изменения
- `gui/application.qss`: SVG-стрелка вниз из оформления статистики применена
  ко всем `QComboBox`; унифицированы ширина кнопки раскрытия и правый отступ
  текста в обычном состоянии и при фокусе.
- Используются существующие `combo-arrow-light.svg` и
  `combo-arrow-dark.svg`, поэтому цвет стрелки соответствует активной теме.
- `tests/test_theme.py`: добавлена проверка общего селектора стрелки и
  тематического пути к SVG.
- `README.md`: описано единое оформление выпадающих списков.

### Проверка
- Целевые тесты тем — 13 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 462 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

## 2026-11-23 — Файлы последнего импорта: док-панель и пункт меню «Вид»

### Изменения
- `gui/imported_files_widget.py`: `ImportedFilesWidget` переведён с `QWidget` на
  `QDockWidget` (objectName `imported_files_dock`, `Qt.AllDockWidgetAreas`,
  `DockWidgetClosable | DockWidgetMovable | DockWidgetFloatable`); содержимое
  собрано в дочернем `QWidget` с полем поиска и таблицей, жирный заголовок убран —
  его заменил заголовок дока. Таблица: имя файла растягивается, колонки реквизитов
  имеют штатную ширину (`_COLUMN_WIDTHS`), текст сокращается многоточием, полный
  текст любой ячейки отдаётся ролью `Qt.ToolTipRole`; ширина панели по умолчанию
  (420 px, `_DOCK_MIN_WIDTH`) вмещает все колонки без горизонтальной прокрутки.
- `gui/dashboard_widget.py`: из раскладки дашборда удалены импорт, создание
  виджета и вызов `refresh()`; вкладка заканчивается сеткой четырёх диаграмм.
- `gui/application.py`: док создаётся только в головном офисе; добавлены
  `_files_dock_preference` и `_imported_files_dock_preference` (выбор оператора
  отдельно от фактической видимости), `_update_docks_visibility()`,
  `_apply_dock_visibility()` (флаг `_syncing_docks` не даёт программному показу
  считаться выбором оператора), `_refresh_imported_files_dock()`. Правила:
  «Прикреплённые файлы» — только вкладки «Научные материалы»/«Телеграммы» на
  любой роли; «Файлы последнего импорта» — только «Дашборд» и только головной
  офис. Сохранение и восстановление состояния обобщены до `_save_dock_state` /
  `_restore_dock_state(prefix)` для обоих доков (видимость, область, плавание,
  геометрия плавающего окна). После импорта пакета панель обновляется.
- `core/settings.py`: четыре поля `imported_files_dock_*`.
- `utils/string_resources.py` и `core/domain_pack.default.json`: пункт меню
  «Файлы последнего импорта» (`menu_imported_files`).
- `tests/test_imported_files_widget.py`: оформление дока, отсутствие блока в
  дашборде, отсутствие горизонтальной прокрутки при штатной ширине, полный текст
  в подсказке.
- `tests/test_window_state.py`: видимость доков по вкладкам и роли, пункт меню,
  сохранение и восстановление области, плавания и выбора видимости, отсутствие
  записи «отказа» при скрытии панели правилом вкладки.
- `README.md`, `docs/dashboard.md`: правила показа панелей, состав колонок,
  поведение меню «Вид».

### Проверка
- `pytest tests/test_imported_files_widget.py tests/test_window_state.py -q` —
  58 passed.
- Полный `pytest tests -q` с `QT_QPA_PLATFORM=offscreen` — 506 passed, одно
  известное предупреждение DOCX.
- Импорт GUI и `scripts_dev/update_pack_strings.py` (590 ключей) выполнены.
- Снимки в offscreen-режиме: панель импорта на дашборде (4 строки, все колонки
  без прокрутки), панель прикреплённых файлов на «Научных материалах» и
  «Телеграммах», отсутствие обеих панелей на «Задачах» и «Статистике», пункт
  меню «Вид», снятие и возврат галочки, переполнения дашборда нет при
  1440×900, 1280×800 и 1024×768.

### Отложено
- Нет.



### Изменения
- `gui/custom_title_bar.py`: `QProgressDialog` и `QFileDialog` исключены из
  глобального установщика кастомных шапок на всех платформах.
- `gui/application.py`: снят атрибут `AA_DontUseNativeDialogs`; выбор и
  сохранение файлов снова выполняются нативными средствами ОС.
- `tests/test_window_state.py`: проверено отсутствие контроллера кастомной
  шапки и `FramelessWindowHint` у прогресс- и файловых диалогов.
- `README.md`: описаны системные прогресс-окна и нативный выбор файлов.

### Проверка
- Целевые тесты состояния окон — 33 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 462 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Задачи: режим «Управление задачами»

### Запрос пользователя
После кнопки «Скрыть распределённые» добавить подсвеченную кнопку «Управление задачами»:
по нажатию выйти из режима распределения (скрыть дерево, обе таблицы, «Создать задачу»,
«Выгрузить задачи») и показать таблицу задач выбранного периода — «Код задачи»,
«Наименование», «Тип», для головного офиса «Назначено регионам»/«Назначено филиалам»,
для филиала «Назначено отделам»/«Назначено исполнителям» (перечисления через запятую),
далее «% процент выполнения», «Частичное решение», «Полное решение», «Начало»,
«Окончание», «Примечание». Функции — как в таблице «Телеграммы», включая фильтр.

### Изменения
- `gui/task_management_model.py` (новый): `management_columns(is_head_office)` собирает
  `ColumnDef` для режима отчёта; `TaskManagementModel(SqlAlchemyTableModel)` хранит
  загруженные задачи периода и вычисляет назначения и процент выполнения в памяти:
  назначения читаются одним запросом из `added_tasks`, документы — суммарным `count`
  по `material_tasks` и `telegram_tasks`; «% процент выполнения» = документы /
  «Полное решение» × 100 (пусто при нулевом или незаданном пороге). Список
  назначений сортируется по названию и перечисляется через запятую; филиал видит
  только узлы своего филиала. Поиск идёт по всем видимым колонкам, сортировка
  по вычисляемым колонкам — числовая для процента и дат.
- `gui/task_management_widget.py` (новый): таблица режима с поиском, фильтром
  (`FilterDialog`, счётчик условий), кнопкой обновления, пагинацией, контекстным меню
  строки (изменение/удаление), изменением ширины, порядка и видимости столбцов,
  сохранением и восстановлением раскладки и сортировки. Ширина скрытых колонок
  запоминается отдельно: у невидимой секции `QHeaderView.columnWidth()` возвращает 0.
- `gui/task_distribution_widget.py`: кнопка «Управление задачами» (`role="primary"`,
  checkable) рядом с «Скрыть распределённые»; страница распределения и страница
  управления собраны в `QStackedWidget`; в режиме управления кнопка «Скрыть
  распределённые» скрывается, таблица заполняется задачами выбранного периода и
  перезагружается при смене периода, после импорта и изменений данных; сигналы
  правки и удаления строки переиспользуют диалоги распределения; `apply_theme`
  обновляет цвета новой таблицы.
- `core/settings.py`: поля `task_columns_layout`, `task_sort`, `task_filters`.
- `gui/application.py`: сохранение и восстановление раскладки, сортировки и фильтров
  режима отчёта; подписка на `tasks_tab.filtersChanged`.
- `gui/application.qss`: `QToolButton` с ролью `primary` (в том числе в состоянии
  `:checked`) оформляется как подсвеченная кнопка — раньше правило действовало
  только для `QPushButton`.
- `utils/string_resources.py`, `core/domain_pack.default.json`: строки режима
  (`task_manage`, `task_manage_tooltip`, `task_manage_hint`, `task_manage_empty`,
  `task_col_*`); пакет перегенерирован — 607 ключей.
- `tests/test_task_widget.py`: подготовка данных с назначениями всех уровней и
  документом; тесты переключения режима (скрытие страницы распределения), состава
  столбцов и значений для головного офиса и филиала, поиска и сортировки по
  вычисляемым колонкам, обратимости раскладки столбцов.
- `README.md`: описан режим «Управление задачами» (столбцы, формула процента,
  возможности таблицы) и особенность вычисляемых колонок.

### Проверка
- `pytest tests/test_task_widget.py -q` (offscreen) — 14 passed.
- Полный `pytest tests -q` (offscreen) — 511 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application` выполнен успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Оформление модуля ОШС

### Запрос пользователя
Убрать кнопку «-» (Скрыть/показать); кнопки «Скрыть», «Изменить», «Статистика» опустить
на один уровень с кнопкой «+» (Добавить), не меняя поведения; кнопку «Закрыть» поднять
на уровень «+»; уменьшить отступы вокруг таблиц на 2/3; кнопки «+»/«-» аватарки
зафиксировать под областью изображения; подпись филиала выводить без слова «Филиал»
и кавычек; территориальную единицу показывать сокращённым наименованием; проверить
правую панель на наползания и обрезку, у диаграмм — видимость всех подписей.

### Изменения
- `gui/oshm_dialog.py`: удалена кнопка «-» (`toggle_btn`) и её обработчик `_toggle_selected`
  (действие осталось в контекстном меню дерева как «Скрыть»); нижний ряд теперь один:
  `add_btn` «+», затем `hide_btn`/`edit_btn`/`stats_btn` (создаются в панели сведений,
  но размещаются здесь), stretch и `QDialogButtonBox(Close)` — «Закрыть» на одном уровне
  с «+». Отступы диалога 6 px, spacing 6, у деревьев 2; `setObjectName("oshmDialog")`
  для адресных правил QSS. Заголовок окна и узлы филиалов используют `branch_display_name`.
- `gui/oshm_details_panel.py`: новая функция `branch_display_name(branch)` — убирает
  служебный префикс «Филиал «…»» и кавычки, при несоответствии шаблону берёт `short_name`
  или код; карточка филиала и подпись филиала в карточке отдела переведены на неё.
  Территориальная единица показывается кодом (сокращённым наименованием `TerritorialUnit.id`),
  а не полным названием. Панель переведена на `QScrollArea`: содержимое не сжимается
  и не обрезается при небольшой высоте окна. Столбец аватара фиксированной ширины,
  кнопки «+»/«-» стоят под изображением, «Печать» — отдельной строкой под ними.
  Поля карточки переносят длинные подписи по словам (`WrapLongRows` + `wordWrap`),
  поэтому панель не уходит в горизонтальную прокрутку; таблица оценок получила
  политику `Preferred` и минимальную ширину 180 px; ширины колонок таблицы задач
  подобраны так, чтобы заголовки читались целиком при минимальном размере окна.
  Попутно добавлен пропущенный импорт `QPainter` (печать панели падала бы с `NameError`).
- `gui/oshm_element_charts.py`: подписи секторов вынесены наружу кольца (`LabelOutside`)
  с коротким выносом, шрифт секторов — 9 pt полужирный; мантия 0.54/0.30, внешнее
  кольцо 0.80/0.54; легенда собрана в `QGridLayout` по две пары «маркер + название»
  в строке и переносится, длинные подписи не обрезаются; минимальный размер вида
  240×240, обе диаграммы делят ширину поровну (`stretch=1`); цвет подписей и числа
  в центре зависит от темы (`_label_color()`), на тёмной теме — белый.
- `gui/application.qss`: блок `QDialog#oshmDialog` — компактные отступы групп
  (margin-top 8, padding 3), заголовок группы со сдвигом 8 px, радиус таблиц 5 px,
  padding заголовков 3/6, тонкий разделитель сплиттера 4 px.
- `tests/test_oshm_dialog.py`: тест `test_head_office_sees_all_branches` больше не ждёт
  `toggle_btn` (проверяет его отсутствие и наличие кнопок нижнего ряда).
- `README.md`: раздел «Изменение организационно-штатной структуры филиала» описывает
  новый нижний ряд кнопок, прокрутку панели, легенду диаграмм, правило отображения
  наименования филиала и сокращённой территориальной единицы; шаг скрытия записей
  ссылается на кнопку «Скрыть».

### Проверка
- `pytest tests/test_oshm_dialog.py tests/test_oshm_avatar_stats.py -q` (offscreen) — 38 passed.
- Полный `pytest tests -q` (offscreen) — 511 passed, одно известное предупреждение zipfile.
- Геометрия панели на эталонной базе (`123.db`, филиал BR-001) при окнах 1040×640,
  1280×800, 1600×900: горизонтальной прокрутки нет ни при одном размере, вертикальная
  прокрутка появляется по потребности; диаграммы равной ширины, легенда без обрезки
  (вторая диаграмма переносится на две строки), на границах области отрисовки нет
  отсечённых подписей; заголовки таблиц оценок и задач читаются целиком; карточки
  филиала, отдела, сотрудника и головного офиса собираются без наложений.
- Тёмная тема: подписи секторов и число в центре белые, читаются.

### Отложено
- Нет.

## 2026-11-24 — ОШС: вторая итерация оформления карточки

### Запрос пользователя
Не коммитить без указания. Для подписи графиков использовать сокращённые наименования
оценок, расшифровку цветов разместить в одну строку. Кнопки «Скрыть», «Изменить»,
«Статистика» и «Печать» прижать к кнопке «Закрыть» с отступом в 1 см. Увеличить
у таблиц отступ сверху в 2 раза. Под надписью территориальной единицы добавить подпись
«Коэффициент эффективности:» и перенести к ней значение коэффициента, не изменяя
размер шрифта. Зафиксировать размер таблицы оценок — в него должны помещаться заголовок
таблицы и 4 строки. Кнопку «Печать» переименовать в «Сохранить» и изменить её функционал:
сохранение отображаемой на карточке информации в файл DOCX.

### Изменения
- `gui/oshm_element_charts.py`: новые `_evaluation_short()` (код из пакета через
  `pack_enum_display("evaluation_value", …)`) и `_evaluation_full()` (`enum_label`);
  легенда строится одной строкой `QGridLayout` (маркер 12×12 + сокращение, по две
  пары в колонке), полное название — во всплывающей подсказке, «без оценки» — «б/о»;
  `PeriodSelectorWidget` получил `AdjustToMinimumContentsLengthWithIcon` и
  `setMinimumContentsLength(4)` — иначе минимальная ширина панели вырастала до 658 px
  и появлялась горизонтальная прокрутка.
- `gui/oshm_details_panel.py`: добавлены `EVAL_TABLE_ROWS = 4`, `_safe_file_name()`,
  `coef_label` («Коэффициент эффективности:»); `coef_value` перенесён из верхней
  центральной области в `fields_layout` последней строкой (у филиала — сразу после
  «Территориальная единица»), шрифт прежний (`pointSize() + 4`), `_add_coefficient_row()`
  и `takeRow` в `_clear_fields()` не дают строке дублироваться при смене карточки.
  Высота `eval_table` зафиксирована: `header_height + row_height * 4 + 2 * frameWidth()`
  (при 8 pt — 141 px, viewport 120 px = ровно 4 строки). Кнопка `print_btn` заменена
  на `save_btn` («Сохранить», `setEnabled(False)` до открытия карточки, включается
  в `_update_avatar()` при наличии узла); удалены `_print_panel`, импорты
  `QPrintDialog`/`QPrinter`/`QPainter`. Новый `save_docx(path)`: заголовок карточки,
  «Период», аватарка (или «Аватарка не задана»), таблица данных с коэффициентом,
  таблица назначенных задач, таблица оценок и обе диаграммы через `grab().save()`
  шириной `Cm(8.5)`; стиль таблиц `Light Grid Accent 1`.
- `gui/oshm_dialog.py`: в нижний ряд добавлены `save_btn` перед «Закрыть»,
  `QSpacerItem(max(0, self._cm(1.0) - spacing), 0)` — отступ ровно 1 см;
  `QDialogButtonBox` получил `QSizePolicy.Fixed`, иначе растягивался на всю ширину
  и зазор становился произвольным; новый метод `_cm()` переводит сантиметры в пиксели
  через `logicalDpiX()`.
- `gui/application.qss`: у `QDialog#oshmDialog QGroupBox` `margin-top` 8 → 16 px.
- `utils/string_resources.py` + `core/domain_pack.default.json`: удалены
  `button_print` и `msg_print_unavailable`; добавлены `oshm_coefficient`,
  `oshm_save_tooltip/title/filter/done/error`, `oshm_doc_*` (title/period/fields/
  tasks/evaluations/charts/no_avatar), `oshm_chart_no_evaluation_short` («б/о»);
  pack перегенерирован — 619 ключей.
- `tests/test_oshm_avatar_stats.py`: обновлён `test_details_panel_new_structure`
  (коэффициент, фиксированная высота таблицы, `save_btn`), легенда проверяется
  как сокращённые коды в одной строке; добавлены `test_details_panel_coefficient_row`,
  `test_details_panel_save_docx` (DOCX: тексты, таблица полей с коэффициентом,
  две диаграммы) и `test_details_panel_save_btn_requires_node`.
- `README.md`: карточка элемента описана по новой раскладке (коэффициент последней
  строкой полей, фиксированная таблица оценок на четыре строки, легенда одной строкой
  сокращениями), кнопка «Печать» заменена описанием «Сохранить» с выгрузкой в Word.

### Проверка
- `pytest tests/test_oshm_avatar_stats.py tests/test_oshm_dialog.py -q` (offscreen) — 41 passed.
- Полный `pytest tests -q` (offscreen) — 514 passed, одно известное предупреждение zipfile.
- Геометрия на эталонной базе (`123.db`, филиал BR-001) при 1040×640, 1280×800,
  1600×900: горизонтальной прокрутки нет, вертикальная — по потребности (188/79/79 px);
  зазор между «Сохранить» и «Закрыть» 38 px при 96 dpi (1 см = 37.8 px) на всех размерах;
  легенды обеих диаграмм — одна строка; `eval_table` 141 px, viewport ровно 120 px.
- Выгрузка DOCX проверена вручную: 3 таблицы (данные с коэффициентом, задачи, оценки),
  2 изображения диаграмм, файл открывается.

### Отложено
- Нет. Коммит не выполняется без указания пользователя.

## 2026-11-24 — ОШС: квадратные диаграммы и полное описание цветов

### Запрос пользователя
Сделать области размещения графиков квадратными; размер графиков и их областей должен
изменяться в зависимости от размера виджета. В описании должны быть раскрыты все цвета
с графика — расшифровки цветов из сокращённых названий; на графике — только цифры значений.

### Изменения
- `gui/oshm_element_charts.py`:
  - `_DonutView`: область построения всегда квадратная — вид занимает всю доступную
    площадь (растягивается по ширине панели), а `apply_square_area()` выставляет поля
    `QChart.setMargins(...)` так, чтобы круг вписался в квадрат со стороной
    `min(width, height)` и центрировался; там же позиционируется надпись в центре
    (`side * 0.30`) и шрифт центра `max(8, min(16, side * 0.055))`. Новый
    `square_side()`.
  - `ElementDonutWidget`: `MIN_SIDE = 180`, `MAX_SIDE = 460`; вид получил
    `Expanding` по ширине и `Minimum` по высоте, минимум по стороне и предел
    `setMaximumWidth(MAX_SIDE)`; в `resizeEvent` высота вида приравнивается к
    `min(max(width, MIN_SIDE), MAX_SIDE)` (`setFixedHeight`, только при изменении) —
    диаграмма растёт вместе с панелью и остаётся квадратной, рекурсии раскладки нет.
    `chart_side()` возвращает сторону квадрата, `chart_title()` — заголовок периода.
  - заголовок периода вынесен из `QChart` в отдельный `_title_label` (wordWrap,
    по центру, шрифт `max(8, min(12, side * 0.035))`), у диаграммы
    `setTitle("")`, `setMargins(QMargins(0, 0, 0, 0))`, `setBackgroundRoundness(0)` —
    область построения не «съедается» подписью.
  - на секторах мантии и внешнего кольца — только числа (`mantle.append(str(telegrams))`
    и `str(materials)`), без «ТГ — 8» / «НМ — 12».
  - описание цветов — одна надпись `_legend_label` (`QLabel`, wordWrap, слева-сверху,
    `Preferred/Minimum`) с HTML-разметкой `_legend_html()`: перед каждой парой цветной
    квадрат `<span style='color:…;'>■</span>&nbsp;{short} — {full}`, пары разделены
    «; ». В описание попадают все цвета, встречающиеся на диаграмме: «ТГ — телеграммы»,
    «НМ — научные материалы» (при наличии), все оценки в порядке убывания веса
    («Б — Бесполезно», «И — Интересно», «П — Полезно», «В — Важно») и «б/о — без оценки».
    Новые `legend_descriptions()` (список строк «сокращение — полное») и
    `_clear_legend()`.
  - промежуточный вариант с `QGridLayout` и пересчётом пар в `resizeEvent`
    (`_reflow_legend`) отброшен: при показе диалога на реальной базе он уходил в
    рекурсию (stack overflow, код -1073741571). Причина — `setFixedSize()` вида внутри
    `resizeEvent` в прокручиваемой панели; замена на поля диаграммы и `setFixedHeight`
    без изменения ширины устранила зацикливание.
- `gui/oshm_dialog.py`: у `main_splitter` заданы `setStretchFactor(0, 0)` и
  `setStretchFactor(1, 1)` — прирост ширины окна забирает панель сведений, поэтому
  диаграммы увеличиваются вместе с окном (было: размеры фиксировались на 620 px).
- `gui/oshm_details_panel.py`: в `save_docx()` перед изображениями диаграмм добавлены
  абзацы с расшифровкой цветов — `f"{chart.chart_title()}: " + "; ".join(...)`.
- `utils/string_resources.py` + `core/domain_pack.default.json`: добавлены
  `oshm_chart_materials_full` («научные материалы»), `oshm_chart_telegrams_full`
  («телеграммы»), `oshm_chart_no_evaluation_full` («без оценки»),
  `oshm_legend_item` («{short} — {full}»); pack перегенерирован — 623 ключа.
- `tests/test_oshm_avatar_stats.py`: `test_donut_structure_example` проверяет подписи
  мантии `{"8", "12"}` и описание цветов; `test_donut_unevaluated_fill_class_arcs` —
  «б/о — без оценки» в описании; новые `test_donut_area_is_square_and_grows`
  (квадрат, рост при увеличении виджета, предел стороны) и
  `test_donut_description_lists_every_color` (все цвета с диаграммы).
- `README.md`: раздел о панели сведений описывает два кольца, числа на секторах,
  описание всех цветов под диаграммой и квадратную область построения, растущую с панелью;
  выгрузка в Word упоминает описание цветов.

### Проверка
- `pytest tests/test_oshm_avatar_stats.py tests/test_oshm_dialog.py -q` (offscreen) — 41 passed;
  после добавления новых тестов — 17 passed в `test_oshm_avatar_stats.py`.
- Полный `pytest tests -q` (offscreen) — 516 passed, одно известное предупреждение zipfile
  (`Duplicate name: 'docProps/core.xml'` в `tests/test_report_service.py`).
- Геометрия на эталонной базе (`123.db`, филиал BR-001) при 1040×640, 1280×800,
  1600×900: обе диаграммы квадратные (293×293 / 310×310), сторона растёт с окном и не
  превышает `MAX_SIDE`; горизонтальной прокрутки нет; подписи на границах области
  построения не обрезаются (проверка пикселей по рамке — 0 попаданий).

### Отложено
- Нет. Коммит не выполняется без указания пользователя.

## 2026-11-24 — Исправление вылета при переключении темы оформления

### Проблема
При переключении темы («Вид» → «Тема») приложение падало с
`AttributeError: 'TaskManagementModel' object has no attribute 'refresh_theme'`
в `MainWindow._set_theme` → `task_distribution_widget.apply_theme()`.

### Причина
`TaskDistributionWidget.apply_theme()` вызывает `refresh_theme()` у модели таблицы
режима «Управление задачами», но `TaskManagementModel` наследуется от
`SqlAlchemyTableModel`, где такого метода не было (он существовал только в
`TaskTableModel`).

### Изменения
- `gui/table_model.py`: в `SqlAlchemyTableModel` добавлен метод `refresh_theme()` —
  эмитит `dataChanged` с `Qt.BackgroundRole` по всем видимым строкам (подсветка
  изменённых записей берёт цвет из текущей темы).
- `tests/test_window_state.py`: регрессионный тест
  `test_switch_theme_recolors_all_tabs` — переключение темы через
  `MainWindow._set_theme` в обе стороны не падает и обновляет настройки.

### Проверка
- Воспроизведение вылета скриптом (offscreen): до правки — `AttributeError`,
  после — переключение dark/light/dark проходит без ошибок.
- Полный `pytest tests -q` — 512 passed.
- Импорт `internal_correspondence.gui.application` — успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Исправление переключения темы

### Причина
- `TaskDistributionWidget.apply_theme()` вызывал отсутствующий метод
  `TaskManagementModel.refresh_theme()`, из-за чего переключение темы падало с
  `AttributeError` после частичного обновления интерфейса.
- Глобальная `current_theme()` обновлялась после применения палитры и QSS, хотя
  Qt рассылает `PaletteChange` и `StyleChange` синхронно во время применения.

### Изменения
- `gui/table_model.py`: в базовую `SqlAlchemyTableModel` добавлен
  `refresh_theme()`, который уведомляет представления об изменении модельных
  цветов; метод доступен и `TaskManagementModel`.
- `gui/theme.py`: активная тема устанавливается до применения палитры/QSS с
  восстановлением прежней темы при исключении.
- `gui/application.py`: настройка темы сохраняется только после успешного
  обновления всех таблиц, графиков и шапки.
- `tests/test_window_state.py`, `tests/test_theme.py`: добавлены повторное
  переключение темы на полном главном окне и проверка темы внутри событий Qt.
- `README.md`: описан безопасный порядок переключения темы.

### Проверка
- Целевые тесты тем и состояния окна — 60 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 513 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Организация в заголовке главного окна

### Задача
Отображать в заголовке главного окна «Головной офис» для роли головного офиса
или краткое наименование филиала для роли филиала.

### Решение (согласовано с пользователем)
- Формат: «{название приложения} — {организация}», например
  «Внутренняя корреспонденция — Головной офис».
- Для филиала: краткое наименование (`Branch.short_name`); фолбэки — полное
  наименование, затем идентификатор филиала из настроек.
- Заголовок формируется при создании окна (смена роли/филиала применяется
  перезапуском приложения).

### Изменения
- `utils/string_resources.py`: новый шаблон `window_title_with_org`
  (`"{app_title} — {organization}"`); метка «Головной офис» переиспользует
  существующую строку `role_head_office`.
- `core/domain_pack.default.json`: секция `strings` регенерирована
  (`scripts_dev/update_pack_strings.py`) — 608 ключей.
- `gui/application.py`: `MainWindow._window_title_text()` и
  `_organization_label()` (запрос `Branch` по `settings.branch_id`);
  заголовок ставится и в `setWindowTitle`, и в кастомную шапку
  (`setup_custom_title_bar` получает `self.windowTitle()`).
- `tests/test_window_state.py`: тесты заголовка для головного офиса, филиала
  с кратким наименованием, фолбэков на полное наименование и идентификатор;
  тест кастомной шапки обновлён под новый заголовок.

### Проверка
- `pytest tests/test_window_state.py -k "title or theme or custom_title_bar"` — 13 passed.
- Полный `pytest tests -q` — 516 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application` — успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Увеличение заголовков кастомных шапок

### Изменения
- `gui/application.qss`: размер названия главного окна увеличен с 11 до 13 px,
  заголовков диалогов — с 12 до 14 px; высота шапок и кнопок не менялась.
- `tests/test_theme.py`: размеры заголовков проверяются в итоговом QSS обеих тем.
- `README.md`: описан увеличенный полужирный текст кастомных шапок.

### Проверка
- Целевые тесты тем — 14 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 513 passed, одно известное предупреждение DOCX.
- Импорт GUI, `compileall` и `git diff --check` выполнены успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Мастер первого запуска: метки страниц перекрывались шапкой окна

### Проблема
В диалогах мастера первого запуска заголовок и подзаголовок страницы
заползали под кастомную шапку окна (44 px).

### Причина
`DialogTitleBarController` резервирует место под шапку через
`setContentsMargins`, но `QWizard` раскладывает дочерние виджеты вручную,
без `QLayout` (у мастера вообще нет layout — проверено: `wizard.layout()`
возвращает None), и игнорирует contents margins: шапка страницы всегда
рисуется у верхней кромки окна.

### Решение
`QWizard` исключён из автоустановки кастомной шапки — мастер сохраняет
системную рамку окна, как `QProgressDialog` и `QFileDialog`. Альтернатива
(вручную сдвигать дочерние виджеты мастера) отклонена как хрупкая: мастер
перераскладывает их при каждом изменении размера и смене страницы.

### Изменения
- `gui/custom_title_bar.py`: в `DialogTitleBarInstaller._should_install`
  `QWizard` исключён для всех платформ (ранее — только для offscreen).
- `tests/test_window_state.py`: `QWizard` убран из параметризации теста
  «системные диалоги оформляются вне offscreen»; добавлен
  `test_wizard_keeps_system_title_bar` — мастер никогда не получает кастомную
  шапку и не становится безрамочным. Нюанс: offscreen-плагин падает
  (access violation) при показе `QWizard` со стилем по умолчанию (Aero),
  поэтому в тесте используется `ModernStyle` — как в `FirstRunWizard`.

### Проверка
- `pytest tests/test_window_state.py -q` — 50 passed.
- `pytest tests/test_first_run_wizard.py -q` — 11 passed.
- Полный `pytest tests -q` — 516 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application` — успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Отступ под шапкой мастера первого запуска

> Отменено при слиянии 2026-11-24: мастер исключён из автоустановки кастомной
> шапки (см. запись выше), поэтому отступ-свойство и rich-text-заголовки
> страниц удалены из `first_run_wizard.py`. Механизм индивидуального отступа
> (`TITLE_BAR_CONTENT_GAP_PROPERTY`) в `custom_title_bar.py` сохранён.

### Изменения
- `gui/first_run_wizard.py`: мастер первого запуска запрашивает дополнительный
  вертикальный отступ 16 px; встроенные заголовки всех страниц переведены в
  формат rich text с верхним пустым блоком, поскольку внутренний layout
  `QWizard` не учитывает внешние поля окна. Заголовок шага, описание и формы
  теперь начинаются ниже кастомной шапки.
- `gui/custom_title_bar.py`: контроллер диалоговой шапки учитывает индивидуальный
  отступ окна при резервировании места и увеличивает высоту окна, поэтому
  содержимое и нижние кнопки мастера не сжимаются.
- `tests/test_first_run_wizard.py`, `tests/test_window_state.py`: проверены настройка
  отступа, смещение встроенных заголовков страниц и применение отступа
  контроллером кастомной шапки.
- `README.md`: описан отступ мастера первого запуска.

### Проверка
- `pytest tests/test_first_run_wizard.py tests/test_window_state.py -q`
  (`QT_QPA_PLATFORM=offscreen`) — 59 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 515 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application`, `compileall` и
  `git diff --check` выполнены успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Поле «Филиал» в диалогах документов головного офиса

### Задача
Убрать поле «Филиал» из обязательных в диалогах редактирования научных
материалов и телеграмм для роли «головной офис»; виджет выбора филиала
переместить к полям, раскрываемым кнопкой «Больше».

### Изменения
- `gui/edit_elements.py`: в `EditElement` добавлены `set_required()`
  и переопределение обязательности (`_required_override`); по умолчанию
  обязательность по-прежнему берётся из метаданных колонки.
- `gui/entity_edit_dialog.py`: новый параметр `branch_in_extra` — выбор
  филиала для роли «головной офис» делается необязательным и размещается
  последней строкой среди дополнительных полей (под «Больше»); без флага
  поведение прежнее (обязательный список в начале диалога).
- `gui/document_dialogs.py`: `MaterialEditDialog` и `TelegramEditDialog`
  передают `branch_in_extra=True`.
- `tests/test_edit_dialog.py`: тест материалов для ГО проверяет
  необязательность, скрытие под «Больше» и положение строки; добавлен
  аналогичный тест для телеграмм.

### Проверка
- `pytest tests/test_edit_dialog.py -q` — 24 passed.
- Полный `pytest tests -q` — 517 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application` — успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Размеры диалога материала и обязательность поля «Филиал»

### Задачи
1. Диалог редактирования научного материала по умолчанию должен показывать
   все поля и кнопки «Сохранить»/«Отмена» без прокрутки.
2. Поле «Филиал» материалов и телеграмм снова обязательное (жирная метка
   с красной звёздочкой), но без подчёркивания (подчёркивание — только для
   уникальных полей) и по-прежнему скрыто под «Больше» для головного офиса.

### Причины
- Подгонка размеров (`_fit_to_content`) выполнялась только в конструкторе:
  подсказки размеров до показа не учитывают оформление стилем, а «обвязка»
  (поля layout + рамка области прокрутки) недоучитывалась — высота занижалась
  и появлялась прокрутка.
- Метка филиала получала подчёркивание, потому что `branch_id` входит
  в составной UniqueConstraint документа, хотя сам по себе не уникален.

### Изменения
- `gui/entity_edit_dialog.py`:
  - `_fit_to_content` считает «обвязку» по фактической геометрии
    (`высота диалога − высота viewport`) и подгоняет также ширину;
  - добавлен `showEvent` с отложенной (`QTimer.singleShot(0)`) повторной
    подгонкой — в момент showEvent дочерние виджеты ещё не «полированы»
    стилем;
  - `branch_in_extra` больше не снимает обязательность филиала; вместо этого
    снимается подчёркивание уникальности (`element.set_unique(False)`).
    Незаполненное обязательное поле по-прежнему показывается даже в
    свёрнутом виде (правило `_apply_row_visibility`).
- `gui/edit_elements.py`: в `EditElement` добавлен `set_unique()`
  (`_unique_override`); неиспользуемый `set_required` удалён.
- `tests/test_edit_dialog.py`: тесты ГО-диалогов проверяют обязательность,
  звёздочку в метке, отсутствие подчёркивания и скрытие под «Больше»;
  тест подгонки размеров обновлён под новую логику и дополнен случаем
  компактного диалога документа (все поля без прокрутки).

### Проверка
- `pytest tests/test_edit_dialog.py -q` — 24 passed.
- Полный `pytest tests -q` — 517 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application` — успешно.
- Высокие диалоги филиала в offscreen-экране 800×600 по-прежнему упираются
  в доступную высоту (прокрутка — штатный запасной вариант); на реальном
  экране содержимое помещается.

### Отложено
- Нет.

---

## 2026-11-24 — Вкладка задач: чекбокс «Отображать распределённые»

### Задача
Заменить кнопку «Скрыть/Показать распределённые» на чекбокс
«Отображать распределённые» с тем же функционалом.

### Изменения
- `gui/task_distribution_widget.py`: `QToolButton distributed_button` заменён
  на `QCheckBox distributed_check` («Отображать распределённые», включён по
  умолчанию — соответствует прежнему состоянию «показывать все»); фильтрация
  применяется при снятом флажке; переключение текста кнопки удалено; в режиме
  «Управление задачами» чекбокс скрывается, как и раньше.
- `utils/string_resources.py`: ключи `task_hide_distributed` и
  `task_show_distributed` заменены одним `task_show_distributed_check`;
  подсказка `task_distributed_tooltip` сохранена.
- `core/domain_pack.default.json`: секция `strings` регенерирована — 607 ключей.
- `tests/test_task_widget.py`: тесты фильтра и режима управления обновлены
  под чекбокс (снятие флажка скрывает распределённые).
- `README.md`: описание вкладки задач приведено к чекбоксу.

### Проверка
- `pytest tests/test_task_widget.py -q` — 14 passed.
- Полный `pytest tests -q` — 517 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application` — успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Перемещение генераторов сидирования в пакет tests/seed_data/

### Контекст
Пользователь переместил фазовые генераторы в пакет `tests/seed_data/`
с переименованием: `seed_reference.py` → `seed_data/seed_reference_1.py`,
`seed_branch.py` → `seed_data/seed_branch_2.py`,
`seed_head_office.py` → `seed_data/seed_head_office_3.py`.

### Правки после перемещения
- `tests/seed_data/*.py`: `PROJECT_ROOT` — `parents[1]` → `parents[2]`
  (файлы на уровень глубже; корень проекта нужен для sys.path и как app_dir
  DatabaseManager); примеры запуска в docstring — на новые пути модулей.
- `tests/test_full_cycle.py`: обращения `seed_branch.main`/`seed_head_office.main`
  заменены на `seed_branch_2.main`/`seed_head_office_3.main`; docstring обновлён.
- `tests/test_seed_branch.py`, `tests/test_seed_head_office.py`: обращения
  к старым именам модулей заменены на новые (`seed_reference_1`,
  `seed_branch_2`, `seed_head_office_3`).
- `README.md`: команды запуска генераторов — `python -m tests.seed_data.seed_*`.
- `tests/seed_data.py`: из docstring убран пример `python -m tests.seed_data` —
  имя модуля теперь занято одноимённым пакетом; запуск по пути файла работает.
- `AGENTS.md`: упомянут пакет `tests/seed_data/`.

### Проверка
- `pytest tests/test_full_cycle.py -q` — 5 passed.
- `pytest tests/test_seed_branch.py tests/test_seed_head_office.py tests/test_seed_reference.py -q` — 27 passed.
- Запуск генераторов `--help`: `python -m tests.seed_data.seed_reference_1`,
  `...seed_branch_2`, `...seed_head_office_3` и `python tests/seed_data.py` — успешно.
- Полный `pytest tests -q` — 517 passed, одно известное предупреждение DOCX.

### Отложено
- Нет.

---

## 2026-11-24 — Подразделение в центре главной шапки

### Изменения
- `gui/custom_title_bar.py`: добавлена прозрачная для мыши центральная подпись
  `WindowContextTitle`; она остаётся по центру всей шапки при изменении размера
  окна и не мешает перетаскиванию за свободную область меню.
- `gui/application.py`: для головного офиса выводится локализованная подпись
  роли; для филиала выполняется поиск по сохранённому `branch_id` и выводится
  «индекс — наименование», а при отсутствии записи в справочнике сохраняется
  введённое вручную значение. После сохранения настроек подпись обновляется.
- `gui/application.qss`: центральная подпись оформлена цветом и размером
  заголовков активной темы.
- `tests/test_window_state.py`, `tests/test_theme.py`: проверены центрирование,
  пропуск событий мыши, головной офис, филиал из БД, ручное значение и стили
  обеих тем.
- `README.md`: описана центральная подпись роли/филиала.

### Проверка
- `pytest tests/test_window_state.py tests/test_theme.py tests/test_first_run_wizard.py -q`
  (`QT_QPA_PLATFORM=offscreen`) — 75 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 517 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application`, `compileall` и
  `git diff --check` выполнены успешно.

### Отложено
- Нет.

---

## 2026-11-24 — Слияние origin/main (PR #20, lo0v777) в somebody_ms_branch

### Конфликты и решения
- `WORK_NOTES.md` (текстовый): сохранены обе истории записей.
- `gui/table_model.py` (семантический): обе ветки добавили `refresh_theme()`
  в `SqlAlchemyTableModel`; оставлена версия из main (Background+Foreground
  роли, защита от пустых колонок), дубликат удалён.
- Мастер первого запуска (семантический): параллельные решения одной проблемы
  перекрытия заголовков. Оставлено исключение `QWizard` из кастомной шапки
  (системная рамка); отступ `TITLE_BAR_CONTENT_GAP_PROPERTY` на мастере и
  rich-text-заголовки с `<br><br><br>` из `first_run_wizard.py` удалены,
  тест `test_first_run_wizard_requests_gap_below_custom_title_bar` снят.
  Сам механизм индивидуального отступа в `custom_title_bar.py` и его тест
  (`test_dialog_title_bar_reserves_requested_content_gap`) сохранены.
- Заголовок главного окна: сосуществуют оба решения — заголовок окна
  «{приложение} — {организация}» (`_window_title_text`, краткое наименование)
  и центральная подпись шапки `WindowContextTitle` («индекс — наименование»,
  `_organization_title`). Потенциальная избыточность отображения — на решении
  пользователя.
- `_set_theme` и `apply_theme`: принята версия main (тема активируется до
  рассылки событий Qt, настройка сохраняется после успешного применения).
- `README.md`: абзац о шапке мастера приведён к выбранному решению
  (системная рамка у мастера).

### Проверка
- Целевые: `pytest tests/test_window_state.py tests/test_theme.py
  tests/test_first_run_wizard.py tests/test_edit_dialog.py
  tests/test_task_widget.py -q` — 117 passed.
- Полный `pytest tests` — 522 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application` — успешно.

### Отложено
- Решить судьбу дублирующегося отображения организации (левый заголовок
  и центральная подпись показывают одно и то же разными форматами).


---

## Слияние с main (2026-11-25) — PR #17–#23 + код-ревью №3
- Подтянут `origin/main` (`8a5bbe9`): fast-forward, конфликтов нет. Новое (~12 тыс. строк): дашборд с уведомлениями/DOCX, перемещаемые/скрываемые колонки таблиц, дашборд-виджет последних файлов (ГО), док-панель файлов последнего импорта, режим «Управление задачами», кастомная заголовочная полоса (`custom_title_bar`), фазовые генераторы `tests/seed_data/`. Новых миграций нет (head `c3d4e5f6a7b8`); main принял нашу правку PK в `a1b2c3d4e5f6`.
- Обновлён `AGENTS.md` (упоминание фазовых генераторов) — правила без изменений.
- **Исправлены баги ревью 20.11, живые в main:** NameError `QPainter` при печати панели сведений (подтверждённая причина падения приложения при печати), NameError `QDesktopServices` в `evaluation_import_dialog`, недостижимый `return True` в `_show_workgroup`.
- Код-ревью №3 записано в `CODE_REVIEW.md`: 522 теста, покрытие 80%; новые находки — захардкоженные коды оценок в цветовой карте дашборда (инвариант 1), 62 мёртвых ключа AppStrings, утечка сессий диалогов не устранена, `application.py` вырос до 1743 строк.
- `pytest tests`: **522/522 passed**; импорт GUI — OK.


---

## Выполнение рекомендаций код-ревью №3 (2026-11-25)
### Рек. 1 — карта цветов дашборда (инвариант 1)
- `gui/dashboard_widget.py`: цветовая карта оценок больше не ключуется кодами пакета (`"Б"/"И"/"П"/"В"`) — новая `_EVALUATION_COLORS_BY_VALUE` по семантическому значению `EvaluationValue` + хелпер `_evaluation_color(code, fallback)` (код → значение через `pack_enum_display`). `tests/test_dashboard.py` переведён на новый API.

### Рек. 2 — чистка строк и pyflakes в чек-листе
- Удалены **48 мёртвых ключей** `AppStrings` (остатки удалённых фич и недоделанных дашбордных ключей; динамические `import_problem_*`/`import_reason_*` сохранены); секция `strings` пакета регенерирована (559 ключей). Один тест ссылался на удалённый `import_load` — переведён на литерал.
- `pyflakes` установлен в `.venv` и добавлен в чек-лист AGENTS.md (п. 3); вычищены все 39 существующих замечаний (неиспользуемые импорты в 24 модулях, 2 мёртвые локальные переменные) — `pyflakes internal_correspondence/` теперь чист.

### Рек. 3 — утечка сессий модальных диалогов
- `gui/application.py`: редакторы справочников открываются через `_open_reference_editor` с `try/finally session.close()`; `OSHMDialog` — сессия закрывается в `finally` после `exec_()`. `ReportDialog` и операции импорта/экспорта уже закрывали сессии корректно. Долгоживущие сессии вкладок/док-виджетов (живут всё время работы приложения) осознанно оставлены — это не утечка по открытиям.

### Проверка
- `pytest tests`: **522/522 passed**; импорт GUI — OK; `pyflakes` — 0 замечаний.
- Не закрыто (осознанно): разбиение `application.py` (1743 строки) — рекомендация «при следующих касаниях».


---

## Оптимизация панели сведений ОШС (2026-11-25)
### Причина медленной работы
- `ElementStatsService.element_documents` загружал ВСЕ материалы и телеграммы и фильтровал в Python; связи (`employees`, `participating_workgroups` через `workgroup_on`, `latest_evaluation`) догружались лениво — N+1 запросов на каждый документ; расчёт выполнялся дважды (текущий период + прошлый год).

### Изменения (`services/element_stats_service.py`)
- Кандидаты отбираются SQL-запросом: диапазон дат (`coalesce(outgoing_date, incoming_date)` между границами периода) + принадлежность, где выразима в SQL (филиал — `branch_id`, сотрудник/отдел — `employees.any(...)`); рабочая группа (участие на дату документа) — остаточная проверка в Python по подгруженным данным.
- Eager-загрузка: `selectinload(employees → workgroup_memberships, evaluations)`, `joinedload(employees → department)` — без ленивых запросов на документ.
- Новый `period_stats_pair()` — показатели текущего и прошлогоднего периодов за ОДИН проход (объединённый диапазон дат); панель (`_refresh_stats`) переведена на него.

### Проверка
- Новый тест `test_period_stats_pair_query_count`: счётчик SQL-запросов через `event.listen(before_cursor_execute)` — пара периодов считается ≤ 12 запросами независимо от числа документов (защита от регресса N+1); результаты совпадают с раздельным расчётом.
- `pytest tests`: **523/523 passed**; импорт GUI — OK; pyflakes — чист.


---

## Редактор пакета предметной области (2026-11-25)
- **`scripts_dev/pack_editor.py`** — автономная утилита (не подключена к окнам приложения): запуск `python scripts_dev/pack_editor.py [путь_к_пакету.json]`; без аргумента открывается встроенный пакет как шаблон.
- Вкладки: «Общие» (id/версия), «Перечисления» (метка перечисления + таблица значений: ключ, код, метка, вес, «устаревшее»; добавление/удаление), «Сущности» (4 метки + таблица полей: метка, кратко, обязательное), «Директории», «Строки» (значения при фиксированных ключах, с фильтром).
- Сохранение/проверка валидируют структуру тем же кодом, что и приложение (`DomainPack.from_dict`) — некорректный пакет сохранить нельзя; открытие файла — через `load_domain_pack`.
- `tests/test_pack_editor.py` (3 offscreen-теста): загрузка встроенного пакета и круговой оборот правки строки, отклонение невалидной структуры, правка метки значения перечисления.
- `pytest tests`: **526/526 passed**; pyflakes — чист (в т.ч. новые файлы).


### Дополнение (2026-11-25) — доработки редактора пакета
- Группировка строк интерфейса: слева список групп по префиксу ключа («Все (N)» + префиксы с количеством), выбор группы фильтрует таблицу; фильтр по тексту работает вместе с группой.
- Переименование перечислений и сущностей (кнопка «Переименовать...», проверка уникальности имени).
- Подсветка пустых обязательных ячеек (фон #F5C6CB): общие — id/версия; перечисления — ключ/код/метка; сущности — имя поля; строки — значение.
- `tests/test_pack_editor.py`: +3 теста (группировка, переименование, подсветка) — 6 всего.
- `pytest tests`: **529/529 passed**; pyflakes — чист.

---

## 2026-11-26 — Кастомная шапка мастера и устранение дублирования роли

### Изменения
- `gui/first_run_wizard.py`: мастер первого запуска помечен как подготовленный
  для кастомной шапки; заголовки его страниц получили внутренний верхний
  отступ, чтобы шапка не перекрывала название и описание шага.
- `gui/custom_title_bar.py`: глобальный установщик разрешает кастомную шапку
  только тем `QWizard`, которые явно подготовили содержимое; остальные мастера
  сохраняют системную рамку.
- `gui/application.py`: системное название и левая подпись главного окна теперь
  содержат только название приложения. Головной офис или выбранный филиал
  отображаются один раз — в центральной подписи шапки.
- `tests/test_window_state.py`: проверены кастомная шапка мастера, сохранение
  системной рамки у обычного `QWizard` и отсутствие роли/филиала слева.
- `README.md`: описание шапок приведено к новому поведению.

### Проверка
- `pytest tests/test_window_state.py tests/test_first_run_wizard.py tests/test_theme.py -q`
  (`QT_QPA_PLATFORM=offscreen`) — 80 passed.
- `.venv/Scripts/python.exe -m pytest tests -q` с
  `QT_QPA_PLATFORM=offscreen` — 535 passed, одно известное предупреждение DOCX.
- Импорт `internal_correspondence.gui.application`, `compileall` и
  `git diff --check` выполнены успешно.
- Визуальный offscreen-рендер: шапка мастера имеет высоту 44 px, заголовок
  шага использует подготовленный внутренний отступ.
- `pyflakes` для изменённых Python-файлов — без замечаний; полная проверка
  проекта показывает три ранее существовавших неиспользуемых импорта в
  `gui/oshm_details_panel.py`.

### Отложено
- Удаление трёх неиспользуемых импортов в `gui/oshm_details_panel.py` не входит
  в эту доработку.

---

## 2026-11-26 — Импорт оценок: «Закрыть» после успеха открывает оценочные листы

### Запрос пользователя
После успешного завершения импорта на 4-м шаге нажатие кнопки «Закрыть» должно
закрывать окно импорта и открывать окно с оценочными листами. Меняется поведение
только этой кнопки.

### Изменения
- `gui/evaluation_import_dialog.py`:
  - кнопка «Закрыть» сохранена в атрибуте `self.close_button` и подключена к новому
    обработчику `_on_close()` вместо `reject`;
  - `_on_close()` вызывает `accept()` (и выставляет флаг `_lists_requested`), только
    если `_import_completed()`: результат есть, это не пробный прогон
    (`not self._result.dry_run`) и текущая страница — результат (`stack.currentIndex() == 3`);
    во всех остальных случаях поведение прежнее — `reject()`;
  - новый метод `shows_evaluation_lists()` отдаёт флаг «после закрытия открыть журналы».
- `gui/application.py`: `_import_evaluations()` после обновления вкладок проверяет
  `dialog.shows_evaluation_lists()` и вызывает `_open_evaluation_lists()`.
- `tests/test_evaluation_import_dialog.py`: четыре новых теста —
  `test_close_after_successful_import_requests_lists` (Accepted + флаг),
  `test_close_without_import_stays_rejected`, `test_close_after_dry_run_stays_rejected`,
  `test_close_on_earlier_step_stays_rejected`.
- `README.md`: в разделе «Импорт оценок из текстового файла» добавлен пункт 6 о новом
  поведении кнопки «Закрыть».

### Проверка
- `pytest tests/test_evaluation_import_dialog.py -q` (offscreen) — 11 passed.
- `pytest tests/test_evaluation_lists_dialog.py tests/test_text_import.py -q` — 18 passed.
- Импорт `internal_correspondence.gui.application` — успешно.
- `pyflakes` (установлен в `.venv`, версия 4.1.0) для изменённых файлов — без замечаний.
- `pytest tests -q` (`QT_QPA_PLATFORM=offscreen`, полный прогон) — 539 passed, одно
  известное предупреждение zipfile (`Duplicate name: 'docProps/core.xml'`).

### Отложено
- Нет. Коммит не выполняется без указания пользователя.

## 2026-11-26 — Индекс филиала в сидирующем скрипте ГО — формат «dd-d-dd»

### Изменения
- `tests/seed_data/seed_reference_1.py`: `Branch.id` (метка «Индекс») теперь
  формируется как «dd-d-dd» со всеми цифрами от 1 до 9 — новая функция
  `build_branch_index(unit_number, branch_number)` («11-1-11», «12-1-12»,
  «21-2-21»…); было `BR-NNN`. В `main()` добавлена валидация: единиц и
  филиалов в единице — не более 9 (однозначные разряды индекса).
- `tests/seed_data/seed_branch_2.py`: `_create_sources` берёт порядковый номер
  филиала из первой части нового индекса; множитель смещён с 10000 на 1000,
  чтобы индекс источника оставаться `SRC-` + 5 цифр (максимум «SRC-99999»).
- `tests/test_full_cycle.py`: константы `BRANCHES` обновлены под новые
  индексы («11-1-11», «21-2-21», «31-3-31»).
- `tests/test_seed_reference.py`: новый тест `test_branch_indexes_match_digit_format`
  (формат `[1-9]{2}-[1-9]-[1-9]{2}`, уникальность индексов).

### Проверка
- `.venv/Scripts/python.exe -m pytest tests/test_seed_reference.py tests/test_seed_branch.py -q` — 23 passed.
- `.venv/Scripts/python.exe -m pytest tests/test_full_cycle.py tests/test_seed_head_office.py -q` — 10 passed.
- Полный прогон `pytest tests -q` — см. ниже.

---

## 2026-11-26 — Колонка и редактор «Источники» для материалов и телеграмм

### Изменения
- `orm/models.py`: связям `ScientificMaterial.sources` и `Telegram.sources`
  добавлены метки `info={"label": "Источники"}`; у `Source` появился метод
  `display_name()` (индекс источника для списков выбора).
- `core/domain_pack.default.json`, `domain_pack.json`: секции `entities`
  зеркалят новые метки полей `sources` (ScientificMaterial, Telegram).
- `gui/application.py`: форматтер `_format_sources` (индексы через запятую,
  по алфавиту) и колонка «Источники» (`sources`, width=110, фильтр N→N)
  сразу после «Страны» в `material_columns()` и `telegram_columns()`
  (обе роли). Обмен ZIP источники по документам уже учитывал
  (`branch_import.source_keep`), схема БД не менялась.
- `gui/document_dialogs.py`: виджет источников (`ManyToManyEditElement`,
  необязательный) ниже виджета стран: в роли «филиал» — в основных полях,
  в роли «головной офис» — в дополнительных под кнопкой «Больше».
- `gui/filter_model.py`: `sources` добавлено в `M2M_COLUMN_NAMES`
  (мультивыбор связанных записей, UUID-ключи поддерживались).
- Тесты: `tests/test_edit_dialog.py` (+3: размещение/видимость виджета
  источников в диалогах материала и телеграммы для обеих ролей, сбор
  значений и отображение индексов), `tests/test_document_table_model.py`
  (+2: порядок колонки «Источники» после «Страны» для обеих ролей,
  форматирование ячейки).

### Проверка
- `pytest tests/test_edit_dialog.py tests/test_document_table_model.py tests/test_entity_labels.py tests/test_domain_pack.py -q` — 88 passed.
- Импорт `internal_correspondence.gui.application`, pyflakes по изменённым
  файлам — чисто.
- Полный прогон `pytest tests -q` — см. итог ниже (дата-сессия 2026-11-26).

---

## 2026-11-26 — Новая классификация типов источников (SourceType 0–4)

### Изменения
- `core/constants.py`: `SourceType` — ANALYTICAL=0, INSTRUMENTAL=1,
  DIFFERENTIATED=2, VERIFICATION=3, MASS_MEDIA=4 (вместо ЭО/НТ).
- `core/domain_pack.default.json`, `domain_pack.json`: перечисление
  `source_type` — коды/метки «А», «И», «Д», «П», «СМИ»
  (Аналитический, Инструментальный, Дифференцированный, Проверочный,
  Средства массовой информации). Схема БД не менялась (в БД — целые значения).
- `tests/seed_data/seed_branch_2.py`: `_create_sources` — индекс источника
  формируется как «<сокращённое наименование типа><пять цифр>»
  (например, «И21001»; числовая часть — прежняя: филиал × 1000 + номер);
  тип выбирается случайно из всех пяти значений.
- `reports/report_service.py`: метрика «материалы с экспериментальным
  оборудованием» переведена на INSTRUMENTAL; ключ контекста шаблона
  `experimental_difference` → `instrumental_difference`.
- `scripts_dev/build_report_templates.py`: фраза месячного шаблона —
  «материалам, полученным инструментальным способом»; шаблоны
  `reports/templates/*.docx` пересобраны скриптом.
- `tests/seed_data.py` (прежний однофазный генератор): тип источника —
  случайный из всех значений перечисления.
- Тесты: `test_domain_pack.py` (коды/метки source_type), `test_seed_branch.py`
  (формат индекса `(А|И|Д|П|СМИ)\d{5}`), `test_statistics_service.py` (метки
  источников), `test_edit_dialog.py`, `test_document_table_model.py` (новые
  члены enum).
- README.md: список значений типа источника приведён к новой классификации.

### Не трогал (история)
- Миграция `alembic/versions/f7db15e6b8c9_enum_codes_to_int.py` и
  `scripts_dev/upgrade_real_db.py` отображают легаси-строки «ЭО»/«НТ» в 0/1 —
  это исторические данные; семантика 0/1 в новой базе иная (Аналитический /
  Инструментальный), при переносе старых БД значения типов источников
  потребуют ручной разметки.

### Проверка
- `pytest tests/test_seed_branch.py tests/test_domain_pack.py tests/test_statistics_service.py tests/test_report_service.py tests/test_edit_dialog.py tests/test_document_table_model.py -q` — 110 passed (1 известное DOCX-предупреждение).
- Полный прогон `pytest tests -q` — итог см. ниже.

---

## 2026-11-26 — Скрипт добавления порций документов филиала (seed_branch_add_4)

### Изменения
- `tests/seed_data/seed_branch_add_4.py` (новый): добавляет научные материалы
  и телеграммы периодом со дня после крайней даты исходящих документов филиала
  в базе (max по материалам и телеграммам) по дату `--to` (по умолчанию —
  сегодня). В отличие от `seed_branch_2`: не создаёт ОШС, не распределяет
  задачи, не создаёт источники — документы ссылаются на имеющиеся записи;
  участники берутся из действующей ОШС. Нумерация продолжает годовые
  счётчики (`_align_counters`), реквизиты разрешительных документов — по
  прежним правилам. Генераторы (`_create_material`, `_create_telegram`,
  `_pick_participants`, `_load_reference_data`, `_resolve_branch`) переиспользованы
  из `seed_branch_2`. Аргументы: `--db-url`, `--storage`, `--to`,
  `--materials-per-day`, `--telegrams-per-day`, `--seed`, `--with-files`
  (нет `--from`, `--clear` и параметров структуры/источников).
  Ошибки BranchSeedError: нет ОШС, нет документов, `--to` раньше
  производного начала периода.
- `tests/test_seed_branch.py`: +3 теста — продолжение периода и нумерации
  от крайней даты без дублирования ОШС/источников; отказ без ОШС и без
  документов; отказ при `--to` раньше производного начала.

### Проверка
- `pytest tests/test_seed_branch.py -q` — 19 passed.
- pyflakes и импорт модуля — чисто; полный прогон — итог ниже.

---

## 2026-11-26 — Запоминание геометрии диалогов документов

### Изменения
- `core/settings.py`: новые поля `material_dialog_geometry` и
  `telegram_dialog_geometry` (Base64 от `QByteArray.saveGeometry`), общая
  секция INI «Application»; запись в файл — существующим `_save_ui_state`
  при завершении работы программы, чтение — при старте (`SettingsManager`).
- `gui/document_dialogs.py`: helpers `_geometry_to_string`/`_restore_geometry`
  и примесь `_DialogGeometryMixin` (восстановление в `__init__` через
  `_init_geometry`, сохранение в `closeEvent`). `MaterialEditDialog` и
  `TelegramEditDialog` принимают необязательный `settings: AppSettings`;
  без него диалоги работают без запоминания (тесты, другие вызовы).
- `gui/document_list_widget.py`: параметр `settings`, передаётся в диалоги
  создания/редактирования; `gui/application.py` передаёт `self.settings`
  обеим вкладкам. Значения копятся в объекте настроек главного окна и
  попадают в INI при выходе (как геометрия главного окна).
- `tests/test_edit_dialog.py`: +3 теста — запоминание/восстановление
  геометрии материала, раздельное хранение материалов/телеграмм, работа
  без настроек.

### Проверка
- `pytest tests/test_edit_dialog.py -q` — 30 passed.
- pyflakes и импорт `gui.application` — чисто; полный прогон — итог ниже.
