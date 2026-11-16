"""Сбор структуры БД из SQLAlchemy-моделей для генерации документации."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import Table
from sqlalchemy.orm import configure_mappers

from internal_correspondence.core.domain_pack import init_domain_pack
from internal_correspondence.orm.base import Base
from internal_correspondence.orm.labels import entity_label, field_label
from internal_correspondence.text_import.repository import import_log, import_rows


# Домены, в порядке разделов документа.
DOMAINS: List[Tuple[str, str, str]] = [
    (
        "reference",
        "Справочники",
        "Территориальные единицы, страны, научные звания, потребители, источники, руководители.",
    ),
    (
        "oshm",
        "Организационная структура",
        "Филиалы, отделы, рабочие группы, сотрудники и история участия в группах.",
    ),
    (
        "documents",
        "Документы",
        "Научные материалы, телеграммы, адресация доклада и файлы.",
    ),
    (
        "tasks",
        "Научные задачи",
        "Задачи, их распределение по узлам ОШС и устаревшие связи с сущностями.",
    ),
    (
        "evaluations",
        "Оценки",
        "Списки оценок и оценки документов, включая эффект.",
    ),
    (
        "import",
        "Импорт оценок",
        "Журнал импорта и построчные результаты сопоставления.",
    ),
    (
        "exchange",
        "Обмен изменениями",
        "Транзитная таблица изменений для экспорта/импорта ZIP.",
    ),
    (
        "service",
        "Служебные объекты",
        "Версия схемы Alembic и представление совпадений импорта.",
    ),
]

# Явные группы таблиц (ассоциативные таблицы в разделы не выносятся).
TABLE_DOMAIN: Dict[str, str] = {
    "territorial_units": "reference",
    "countries": "reference",
    "academic_titles": "reference",
    "consumers": "reference",
    "sources": "reference",
    "leaders": "reference",
    "branches": "oshm",
    "departments": "oshm",
    "working_groups": "oshm",
    "workgroup_memberships": "oshm",
    "employees": "oshm",
    "scientific_materials": "documents",
    "telegrams": "documents",
    "report_addresses": "documents",
    "file_records": "documents",
    "scientific_tasks": "tasks",
    "added_tasks": "tasks",
    "task_entity_links": "tasks",
    "evaluation_lists": "evaluations",
    "evaluations": "evaluations",
    "import_log": "import",
    "import_rows": "import",
    "changes": "exchange",
}

ASSOCIATIONS: Dict[str, Tuple[str, str]] = {
    "material_countries": ("scientific_materials", "countries"),
    "material_departments": ("scientific_materials", "departments"),
    "material_employees": ("scientific_materials", "employees"),
    "material_files": ("scientific_materials", "file_records"),
    "material_sources": ("scientific_materials", "sources"),
    "material_tasks": ("scientific_materials", "scientific_tasks"),
    "material_workgroups": ("scientific_materials", "working_groups"),
    "telegram_countries": ("telegrams", "countries"),
    "telegram_departments": ("telegrams", "departments"),
    "telegram_employees": ("telegrams", "employees"),
    "telegram_files": ("telegrams", "file_records"),
    "telegram_sources": ("telegrams", "sources"),
    "telegram_tasks": ("telegrams", "scientific_tasks"),
    "telegram_workgroups": ("telegrams", "working_groups"),
    "evaluation_materials": ("evaluations", "scientific_materials"),
    "evaluation_telegrams": ("evaluations", "telegrams"),
}

# Описания сущностей (первая строка docstring модели используется как fallback).
ENTITY_DESCRIPTIONS: Dict[str, str] = {
    "territorial_units": "Территориальная единица (регион), объединяющая филиалы.",
    "branches": "Филиал организации; корневой узел ОШС филиала и владелец документов.",
    "departments": "Отдел филиала; объединяет сотрудников и рабочие группы.",
    "working_groups": "Рабочая группа отдела с историей участия сотрудников.",
    "workgroup_memberships": "Период участия сотрудника в рабочей группе.",
    "employees": "Сотрудник филиала с должностью и научным званием.",
    "academic_titles": "Научное звание сотрудника с падежными формами.",
    "countries": "Страна, связанная с документом.",
    "consumers": "Потребитель научной продукции.",
    "sources": "Источник поступления документа.",
    "leaders": "Руководитель, которому адресуется доклад по телеграмме.",
    "scientific_tasks": "Научная задача с плановыми сроками и порогами решения.",
    "added_tasks": "Назначение научной задачи узлу ОШС (регион, филиал, отдел, группа, сотрудник).",
    "task_entity_links": "Устаревшая связь задачи с произвольной сущностью; оставлена для совместимости.",
    "scientific_materials": "Научный материал с исходящими и входящими реквизитами.",
    "telegrams": "Телеграмма с реквизитами, типом доклада и адресацией.",
    "report_addresses": "Адресат доклада по телеграмме с датой доклада.",
    "file_records": "Файл в файловом хранилище; связывается с документами.",
    "evaluation_lists": "Список оценок (номер и дата), объединяющий оценки.",
    "evaluations": "Оценка документа с кодом, датой и эффектом.",
    "changes": "Изменение сущности для обмена дельтами между филиалом и головным офисом.",
    "import_log": "Журнал одного импорта оценок из текстового файла.",
    "import_rows": "Построчный результат импорта: разобранные данные, статус и совпадение.",
}

# Уточнения меток полей, где общая метка пакета недостаточно конкретна.
FIELD_LABELS: Dict[Tuple[str, str], str] = {
    ("changes", "id"): "Идентификатор изменения",
    ("changes", "entity_name"): "Имя сущности",
    ("changes", "entity_pk"): "Первичный ключ сущности",
    ("changes", "changed_at"): "Дата изменения",
    ("changes", "changed_fields"): "Изменённые поля",
    ("changes", "operation_type"): "Тип операции",
    ("changes", "exported_at"): "Дата экспорта",
    ("added_tasks", "node_type"): "Тип узла",
    ("added_tasks", "node_id"): "Идентификатор узла",
    ("task_entity_links", "entity_name"): "Имя сущности",
    ("task_entity_links", "entity_pk"): "Первичный ключ сущности",
    ("workgroup_memberships", "start_date"): "Начало участия",
    ("workgroup_memberships", "end_date"): "Окончание участия",
    ("evaluations", "effect"): "Эффект",
    ("import_log", "id"): "Идентификатор импорта",
    ("import_log", "year"): "Год",
    ("import_log", "doc_no"): "Номер документа",
    ("import_log", "doc_date"): "Дата документа",
    ("import_log", "file_name"): "Имя файла",
    ("import_log", "file_hash"): "SHA-256 файла",
    ("import_log", "stored_path"): "Путь в хранилище",
    ("import_log", "scheme_name"): "Имя схемы",
    ("import_log", "matched_rule"): "Правило сопоставления",
    ("import_log", "imported_rows"): "Импортировано строк",
    ("import_log", "matched_rows"): "Сопоставлено строк",
    ("import_log", "unmatched_rows"): "Не сопоставлено строк",
    ("import_log", "skipped_rows"): "Пропущено строк",
    ("import_log", "rejected_rows"): "Отклонено строк",
    ("import_log", "error_rows"): "Ошибок",
    ("import_log", "started_at"): "Начало импорта",
    ("import_log", "finished_at"): "Окончание импорта",
    ("import_log", "status"): "Статус",
    ("import_rows", "id"): "Идентификатор строки",
    ("import_rows", "year"): "Год",
    ("import_rows", "import_id"): "Импорт",
    ("import_rows", "source_row_no"): "Номер строки в файле",
    ("import_rows", "raw_line"): "Исходная строка",
    ("import_rows", "data"): "Разобранные данные",
    ("import_rows", "status"): "Статус строки",
    ("import_rows", "error"): "Ошибка",
    ("import_rows", "branch_code"): "Код филиала",
    ("import_rows", "outgoing_no"): "Исходящий номер",
    ("import_rows", "year_month"): "Отчётный месяц",
    ("import_rows", "value_code"): "Код оценки",
    ("import_rows", "evaluation_date"): "Дата оценки",
    ("import_rows", "matched_entity_type"): "Тип найденной сущности",
    ("import_rows", "matched_entity_id"): "Идентификатор найденной сущности",
    ("import_rows", "created_at"): "Дата создания",
}

# Типы для таблиц Core, которых нет в Base.metadata.
CORE_LABELS: Dict[str, str] = {
    "import_log": "Журнал импорта",
    "import_rows": "Строки импорта",
}


@dataclass
class ColumnInfo:
    name: str
    label: str
    type_name: str
    nullable: bool
    primary_key: bool
    foreign_key: Optional[str] = None
    ondelete: Optional[str] = None
    unique: bool = False
    default: Optional[str] = None
    description: str = ""


@dataclass
class IndexInfo:
    name: str
    columns: List[str]
    unique: bool


@dataclass
class TableInfo:
    name: str
    label: str
    description: str
    domain: str
    columns: List[ColumnInfo] = field(default_factory=list)
    indexes: List[IndexInfo] = field(default_factory=list)
    unique_constraints: List[Tuple[str, List[str]]] = field(default_factory=list)
    is_association: bool = False
    is_core: bool = False

    def column(self, name: str) -> Optional[ColumnInfo]:
        for column in self.columns:
            if column.name == name:
                return column
        return None

    @property
    def primary_keys(self) -> List[ColumnInfo]:
        return [column for column in self.columns if column.primary_key]

    @property
    def foreign_keys(self) -> List[ColumnInfo]:
        return [column for column in self.columns if column.foreign_key]


def _mapper_by_table() -> Dict[str, object]:
    return {
        mapper.local_table.name: mapper.class_
        for mapper in Base.registry.mappers
        if mapper.local_table is not None
    }


def _first_line(text: Optional[str]) -> str:
    if not text:
        return ""
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _column_label(table: str, model: Optional[object], name: str) -> str:
    if (table, name) in FIELD_LABELS:
        return FIELD_LABELS[(table, name)]
    if name == "change_id":
        return "Изменение"
    if model is not None:
        try:
            value = field_label(model, name)
            if value:
                return value
        except Exception:
            pass
    return name


def _column_type(column) -> str:
    try:
        return str(column.type)
    except Exception:
        return type(column.type).__name__


def _describe_column(table: str, column) -> str:
    if column.primary_key:
        if len(column.table.primary_key.columns) == 1:
            return "Первичный ключ"
        return "Часть составного первичного ключа"
    if column.name == "change_id":
        return "Изменение для обмена дельтами"
    if column.name in ("created_at", "updated_at", "started_at", "finished_at"):
        return "Служебная метка времени"
    if column.foreign_keys:
        return "Ссылка на связанную запись"
    if table == "changes" and column.name == "operation_type":
        return "0 — создание, 1 — изменение, 2 — удаление"
    if table == "import_log" and column.name == "status":
        return "running, committed или rolled_back"
    return ""


def _collect_table(table: Table, model: Optional[object], domain: str) -> TableInfo:
    label = CORE_LABELS.get(table.name)
    if not label:
        label = entity_label(model) if model is not None else table.name
    description = ENTITY_DESCRIPTIONS.get(table.name) or _first_line(
        getattr(model, "__doc__", None)
    )
    columns: List[ColumnInfo] = []
    for column in table.columns:
        foreign_key = None
        ondelete = None
        for fk in column.foreign_keys:
            foreign_key = fk.target_fullname
            ondelete = fk.ondelete
            break
        unique = bool(column.unique)
        if not unique:
            for constraint in table.constraints:
                names = getattr(constraint, "columns", None)
                if names is None:
                    continue
                if constraint.__class__.__name__ == "UniqueConstraint":
                    if [c.name for c in names] == [column.name]:
                        unique = True
                        break
        default = None
        if column.server_default is not None:
            default = str(column.server_default.arg)
        elif column.default is not None and not column.default.is_callable:
            default = str(column.default.arg)
        columns.append(
            ColumnInfo(
                name=column.name,
                label=_column_label(table.name, model, column.name),
                type_name=_column_type(column),
                nullable=bool(column.nullable),
                primary_key=bool(column.primary_key),
                foreign_key=foreign_key,
                ondelete=ondelete,
                unique=unique,
                default=default,
                description=_describe_column(table.name, column),
            )
        )

    indexes = [
        IndexInfo(
            name=index.name,
            columns=[column.name for column in index.columns],
            unique=bool(index.unique),
        )
        for index in table.indexes
    ]
    unique_constraints = []
    for constraint in table.constraints:
        if constraint.__class__.__name__ == "UniqueConstraint":
            unique_constraints.append(
                (
                    constraint.name or "",
                    [column.name for column in constraint.columns],
                )
            )

    return TableInfo(
        name=table.name,
        label=label,
        description=description,
        domain=domain,
        columns=columns,
        indexes=indexes,
        unique_constraints=unique_constraints,
        is_association=table.name in ASSOCIATIONS,
        is_core=table.name in CORE_LABELS,
    )


def collect_schema() -> Dict[str, TableInfo]:
    """Возвращает все таблицы схемы, включая ассоциативные и служебные."""
    init_domain_pack()
    configure_mappers()
    models = _mapper_by_table()

    result: Dict[str, TableInfo] = {}
    for table in Base.metadata.sorted_tables:
        domain = TABLE_DOMAIN.get(table.name, "service")
        result[table.name] = _collect_table(table, models.get(table.name), domain)

    # Таблицы Core-импорта не входят в Base.metadata.
    for table in (import_log, import_rows):
        result[table.name] = _collect_table(table, None, "import")
    return result


def domain_tables(schema: Dict[str, TableInfo], domain: str) -> List[TableInfo]:
    return [
        table
        for table in schema.values()
        if table.domain == domain and not table.is_association
    ]


def association_pairs() -> Iterable[Tuple[str, str, str]]:
    for name, (left, right) in ASSOCIATIONS.items():
        yield name, left, right
