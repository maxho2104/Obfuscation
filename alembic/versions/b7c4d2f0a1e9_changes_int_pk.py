"""changes: первичный ключ UUID -> Integer autoincrement

Таблица ``changes`` локальна и транзитна (записи удаляются после экспорта),
поэтому глобальная уникальность UUID ей не нужна. Перевод на целочисленный
ключ уменьшает размер таблицы и ускоряет работу с ней.

Миграция сохраняет данные: старые UUID-ключи сопоставляются новым
целочисленным через временную колонку ``old_id``, ссылки ``change_id``
в отслеживаемых таблицах переносятся на новые значения.

Downgrade является потерьным: записи ``changes`` и ссылки ``change_id``
очищаются (допустимо, т.к. таблица транзитна).

Revision ID: b7c4d2f0a1e9
Revises: 699a1e3ea27c
Create Date: 2026-11-09 22:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7c4d2f0a1e9"
down_revision: Union[str, None] = "699a1e3ea27c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Таблицы, имеющие внешний ключ change_id -> changes.id
TRACKED_TABLES = [
    "academic_titles",
    "branches",
    "consumers",
    "countries",
    "departments",
    "employees",
    "evaluation_lists",
    "evaluations",
    "file_records",
    "leaders",
    "report_addresses",
    "scientific_materials",
    "scientific_tasks",
    "sources",
    "telegrams",
    "territorial_units",
    "working_groups",
]


def upgrade() -> None:
    """Переводит changes.id на Integer с сохранением ссылок change_id."""
    # 1. Переименовываем старую таблицу изменений и освобождаем имена индексов.
    op.rename_table("changes", "changes_old")
    op.drop_index("ix_changes_entity_name", table_name="changes_old")
    op.drop_index("ix_changes_entity_pk", table_name="changes_old")

    # 2. Создаём новую таблицу с целочисленным PK и временной колонкой old_id.
    op.create_table(
        "changes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("old_id", sa.String(36), nullable=True),
        sa.Column("entity_name", sa.String(length=100), nullable=False),
        sa.Column("entity_pk", sa.String(length=255), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_changes_entity_name", "changes", ["entity_name"])
    op.create_index("ix_changes_entity_pk", "changes", ["entity_pk"])

    # 3. Копируем данные, запоминая соответствие старых UUID новым id.
    op.execute(
        "INSERT INTO changes (old_id, entity_name, entity_pk, changed_at,"
        " changed_fields, created_at, updated_at)"
        " SELECT CAST(id AS VARCHAR(36)), entity_name, entity_pk, changed_at,"
        " changed_fields, created_at, updated_at FROM changes_old"
    )

    # 4. Переносим ссылки change_id в отслеживаемых таблицах.
    for table in TRACKED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("change_id_new", sa.Integer(), nullable=True))
        op.execute(
            f"UPDATE {table} SET change_id_new ="
            f" (SELECT c.id FROM changes c"
            f" WHERE c.old_id = CAST({table}.change_id AS VARCHAR(36)))"
            f" WHERE change_id IS NOT NULL"
        )
        with op.batch_alter_table(table) as batch:
            batch.drop_column("change_id")
        with op.batch_alter_table(table) as batch:
            batch.alter_column("change_id_new", new_column_name="change_id")
        with op.batch_alter_table(table) as batch:
            batch.create_foreign_key(
                f"fk_{table}_change_id",
                "changes",
                ["change_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # 5. Удаляем временную колонку и старую таблицу.
    with op.batch_alter_table("changes") as batch:
        batch.drop_column("old_id")
    op.drop_table("changes_old")


def downgrade() -> None:
    """Возвращает UUID-ключ, очищая транзитные записи изменений.

    Потеря данных таблицы changes допустима: записи транзитны и
    удаляются после экспорта. Ссылки change_id обнуляются.
    """
    # 1. Обнуляем ссылки и очищаем таблицу изменений.
    for table in TRACKED_TABLES:
        op.execute(f"UPDATE {table} SET change_id = NULL")
    op.execute("DELETE FROM changes")

    # 2. Переводим ссылки change_id обратно на UUID.
    for table in TRACKED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.alter_column("change_id", type_=sa.UUID())

    # 3. Переводим первичный ключ changes обратно на UUID.
    with op.batch_alter_table("changes") as batch:
        batch.alter_column("id", type_=sa.UUID(), autoincrement=False)
