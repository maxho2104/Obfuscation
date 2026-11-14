"""Удаление устаревших служебных колонок в ранее созданных базах

Рабочие базы, созданные до появления миграции ``d5b9e3c4f6a7`` через
``Base.metadata.create_all``, содержат колонки ``row_version``,
``changes.created_at`` и ``changes.updated_at``. ORM-модели эти колонки
уже не описывают, поэтому вставка новых записей падает на ограничении
``NOT NULL`` (например, ``evaluation_lists.row_version``).

Миграция идемпотентна: колонки удаляются только там, где они реально есть.
Служебные значения ``row_version`` не используются бизнес-логикой, поэтому
перенос данных не требуется. Downgrade возвращает колонки с ``DEFAULT 1``;
прежние значения теряются — это осознанно, как и в ``d5b9e3c4f6a7``.

Revision ID: c8f1a3d5e7b9
Revises: a7d4e2f6b9c1
Create Date: 2026-11-14 09:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8f1a3d5e7b9"
down_revision: Union[str, None] = "a7d4e2f6b9c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Таблицы, у которых исторически могла остаться колонка row_version.
_ROW_VERSION_TABLES = (
    "territorial_units",
    "branches",
    "countries",
    "academic_titles",
    "consumers",
    "sources",
    "leaders",
    "departments",
    "working_groups",
    "employees",
    "scientific_tasks",
    "file_records",
    "scientific_materials",
    "telegrams",
    "report_addresses",
    "evaluation_lists",
    "evaluations",
    "added_tasks",
)


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    """Возвращает имена колонок таблицы или пустое множество."""
    try:
        return {column["name"] for column in inspector.get_columns(table_name)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    """Удаляет устаревшие служебные колонки, если они присутствуют."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table_name in sorted(tables):
        if "row_version" in _column_names(inspector, table_name):
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.drop_column("row_version")

    if "changes" in tables:
        columns = _column_names(inspector, "changes")
        if "created_at" in columns or "updated_at" in columns:
            with op.batch_alter_table("changes") as batch_op:
                if "created_at" in columns:
                    batch_op.drop_column("created_at")
                if "updated_at" in columns:
                    batch_op.drop_column("updated_at")


def downgrade() -> None:
    """Возвращает служебные колонки (прежние значения не восстанавливаются)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table_name in _ROW_VERSION_TABLES:
        if table_name not in tables:
            continue
        if "row_version" not in _column_names(inspector, table_name):
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "row_version",
                        sa.Integer(),
                        nullable=False,
                        server_default="1",
                    )
                )

    if "changes" in tables:
        columns = _column_names(inspector, "changes")
        with op.batch_alter_table("changes") as batch_op:
            if "created_at" not in columns:
                batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
            if "updated_at" not in columns:
                batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
