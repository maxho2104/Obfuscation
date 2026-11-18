"""Источники: UUID-первичный ключ и уникальный индекс

Источники не являются справочными данными головного офиса: наборы
источников различаются от филиала к филиалу, поэтому для надёжной
идентификации в обмене первичный ключ ``sources.id`` меняется со строкового
на UUID, а человекочитаемый «Индекс» (String(10), unique) выделяется
в отдельную колонку ``sources.index``.

Перенос данных (upgrade): каждой записи назначается UUID, значением
индекса становится прежний id (усечённый до 10 символов при необходимости,
при коллизиях — с суффиксом). Ссылки в ``material_sources`` и
``telegram_sources`` переключаются на UUID, записи ``changes`` по сущности
Source получают новый строковый PK.

Downgrade обратим по структуре: ``id`` восстанавливается из ``index``
(присвоенные UUID теряются — задокументированная потеря).

Revision ID: a1b2c3d4e5f6
Revises: f4c6a8d0e2b1
Create Date: 2026-11-18 12:00:00.000000
"""
import uuid
from typing import Dict, List, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f4c6a8d0e2b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = PGUUID(as_uuid=True)

# Имена внешних ключей создаются явно, чтобы перенацелить их на
# PostgreSQL после переименования таблиц (SQLite делает это сам).
_FK_MATERIAL_SOURCE = "fk_material_sources_source"
_FK_TELEGRAM_SOURCE = "fk_telegram_sources_source"

# Целевые схемы временных таблиц: имя колонки -> тип.
# change_id — ссылка на Change (ChangeTrackedMixin), переносится как есть.
_SOURCES_NEW_COLUMNS = {
    "id": _UUID,
    "index": sa.String(10),
    "type": sa.SmallInteger,
    "comment": sa.Text,
    "change_id": sa.Integer,
}
_SOURCES_OLD_COLUMNS = {
    "id": sa.String(50),
    "type": sa.SmallInteger,
    "comment": sa.Text,
    "change_id": sa.Integer,
}


def _assign_indexes(old_ids: List[str]) -> Dict[str, str]:
    """Возвращает соответствие старый id -> индекс (≤ 10 символов, unique)."""
    indexes: Dict[str, str] = {}
    used = set()
    for old_id in old_ids:
        base = str(old_id)[:10]
        candidate = base
        serial = 1
        while candidate in used:
            suffix = f"~{serial}"
            candidate = f"{base[: 10 - len(suffix)]}{suffix}"
            serial += 1
        used.add(candidate)
        indexes[str(old_id)] = candidate
    return indexes


def _insert_typed(
    table_name: str,
    columns: Dict[str, sa.types.TypeEngine],
    rows: List[dict],
) -> None:
    """Вставляет строки через типизированную Core-таблицу (корректные UUID)."""
    if not rows:
        return
    metadata = sa.MetaData()
    typed = sa.Table(
        table_name,
        metadata,
        *[sa.Column(name, type_) for name, type_ in columns.items()],
    )
    op.get_bind().execute(typed.insert(), rows)


def _create_new_tables(source_columns: Dict[str, sa.types.TypeEngine]) -> None:
    """Создаёт временные таблицы: источники (source_columns) + две связки."""
    source_defs = [
        sa.Column(name, type_, primary_key=(name == "id"))
        for name, type_ in source_columns.items()
    ]
    source_defs.append(
        sa.ForeignKeyConstraint(
            ["change_id"], ["changes.id"], ondelete="SET NULL"
        )
    )
    if "index" in source_columns:
        source_defs.append(
            sa.UniqueConstraint("index", name="uq_sources_index")
        )
    op.create_table("sources_new", *source_defs)
    source_pk_type = source_columns["id"]

    op.create_table(
        "material_sources_new",
        sa.Column(
            "material_id",
            _UUID,
            sa.ForeignKey("scientific_materials.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_id", source_pk_type, nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources_new.id"],
            ondelete="CASCADE",
            name=_FK_MATERIAL_SOURCE,
        ),
    )
    op.create_table(
        "telegram_sources_new",
        sa.Column(
            "telegram_id",
            _UUID,
            sa.ForeignKey("telegrams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_id", source_pk_type, nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources_new.id"],
            ondelete="CASCADE",
            name=_FK_TELEGRAM_SOURCE,
        ),
    )


def _drop_final_tables() -> None:
    op.drop_table("material_sources")
    op.drop_table("telegram_sources")
    op.drop_table("sources")


def _drop_new_tables() -> None:
    op.drop_table("telegram_sources_new")
    op.drop_table("material_sources_new")
    op.drop_table("sources_new")


def _retarget_constraints(tables: Sequence[str], target: str) -> None:
    """Перенацеливает FK источников (PostgreSQL; SQLite — автоматически)."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for constraint, table in (
        (_FK_MATERIAL_SOURCE, tables[0]),
        (_FK_TELEGRAM_SOURCE, tables[1]),
    ):
        op.drop_constraint(constraint, table)
        op.create_foreign_key(
            constraint,
            table,
            target,
            ["source_id"],
            ["id"],
            ondelete="CASCADE",
        )


def _rename_new_to_final() -> None:
    op.rename_table("sources_new", "sources")
    op.rename_table("material_sources_new", "material_sources")
    op.rename_table("telegram_sources_new", "telegram_sources")
    # PostgreSQL не обновляет цели FK при переименовании таблиц.
    _retarget_constraints(("material_sources", "telegram_sources"), "sources")


def _update_source_changes(id_map: Dict[str, str]) -> None:
    """Переписывает entity_pk записей Change по сущности Source."""
    bind = op.get_bind()
    for old_pk, new_pk in id_map.items():
        bind.execute(
            sa.text(
                "UPDATE changes SET entity_pk = :new "
                "WHERE entity_name = 'Source' AND entity_pk = :old"
            ),
            {"new": new_pk, "old": old_pk},
        )


def _read_mappings() -> tuple:
    """Читает источники и связки с источниками в исходной схеме."""
    bind = op.get_bind()
    has_index = "index" in {
        column["name"] for column in sa.inspect(bind).get_columns("sources")
    }
    select_sources = (
        'SELECT id, "index", type, comment, change_id FROM sources'
        if has_index
        else 'SELECT id, NULL AS "index", type, comment, change_id FROM sources'
    )
    sources = bind.execute(sa.text(select_sources)).mappings().all()
    material_links = (
        bind.execute(sa.text("SELECT material_id, source_id FROM material_sources"))
        .mappings()
        .all()
    )
    telegram_links = (
        bind.execute(sa.text("SELECT telegram_id, source_id FROM telegram_sources"))
        .mappings()
        .all()
    )
    return sources, material_links, telegram_links


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    sources_columns = {column["name"] for column in inspector.get_columns("sources")}
    if "index" in sources_columns:
        return  # миграция уже применена

    old_sources, old_material_links, old_telegram_links = _read_mappings()

    id_map = {str(row["id"]): uuid.uuid4() for row in old_sources}
    index_map = _assign_indexes([str(row["id"]) for row in old_sources])

    _create_new_tables(_SOURCES_NEW_COLUMNS)

    _insert_typed(
        "sources_new",
        _SOURCES_NEW_COLUMNS,
        [
            {
                "id": id_map[str(row["id"])],
                "index": index_map[str(row["id"])],
                "type": row["type"],
                "comment": row["comment"],
                "change_id": row["change_id"],
            }
            for row in old_sources
        ],
    )
    _insert_typed(
        "material_sources_new",
        {"material_id": _UUID, "source_id": _UUID},
        [
            {
                "material_id": uuid.UUID(str(row["material_id"])),
                "source_id": id_map[str(row["source_id"])],
            }
            for row in old_material_links
        ],
    )
    _insert_typed(
        "telegram_sources_new",
        {"telegram_id": _UUID, "source_id": _UUID},
        [
            {
                "telegram_id": uuid.UUID(str(row["telegram_id"])),
                "source_id": id_map[str(row["source_id"])],
            }
            for row in old_telegram_links
        ],
    )

    _drop_final_tables()
    _rename_new_to_final()
    _update_source_changes({old: str(new) for old, new in id_map.items()})


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    sources_columns = {column["name"] for column in inspector.get_columns("sources")}
    if "index" not in sources_columns:
        return  # схема ещё старая, откатывать нечего

    old_sources, old_material_links, old_telegram_links = _read_mappings()

    # UUID -> прежний строковый id (восстанавливается из индекса).
    # Ключи приводим к каноническому виду str(uuid) — именно в таком виде
    # PK хранится в changes.entity_pk (SQLite отдаёт UUID-колонку как hex).
    id_map = {
        str(uuid.UUID(str(row["id"]))): str(row["index"]) for row in old_sources
    }

    _create_new_tables(_SOURCES_OLD_COLUMNS)

    _insert_typed(
        "sources_new",
        _SOURCES_OLD_COLUMNS,
        [
            {
                "id": str(row["index"]),
                "type": row["type"],
                "comment": row["comment"],
                "change_id": row["change_id"],
            }
            for row in old_sources
        ],
    )
    _insert_typed(
        "material_sources_new",
        {"material_id": _UUID, "source_id": sa.String(50)},
        [
            {
                "material_id": uuid.UUID(str(row["material_id"])),
                "source_id": id_map[str(uuid.UUID(str(row["source_id"])))],
            }
            for row in old_material_links
        ],
    )
    _insert_typed(
        "telegram_sources_new",
        {"telegram_id": _UUID, "source_id": sa.String(50)},
        [
            {
                "telegram_id": uuid.UUID(str(row["telegram_id"])),
                "source_id": id_map[str(uuid.UUID(str(row["source_id"])))],
            }
            for row in old_telegram_links
        ],
    )

    _drop_final_tables()
    _rename_new_to_final()
    _update_source_changes(id_map)
