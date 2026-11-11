"""Удаление служебных колонок row_version, created_at, updated_at

Миксины ``VersionedMixin`` и ``TimestampMixin`` удалены из ORM-моделей.
Оптимистичный контроль версий (``row_version``) отменён, а у таблицы
``changes`` временные метки ``created_at``/``updated_at`` дублировали
поле ``changed_at``.

Удаляемые колонки — чисто служебные: бизнес-данные (в т.ч. ``changed_at``)
не затрагиваются, поэтому перенос данных не требуется.

Downgrade возвращает колонки; восстановить прежние значения невозможно —
они теряются (служили только для служебных целей).

Revision ID: d5b9e3c4f6a7
Revises: c4a8f1b2d3e4
Create Date: 2026-11-11 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d5b9e3c4f6a7"
down_revision: Union[str, None] = "c4a8f1b2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Таблицы, у которых удаляется служебная колонка row_version
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
)


def upgrade() -> None:
    """Удаляет служебные колонки row_version и created_at/updated_at."""
    for table_name in _ROW_VERSION_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("row_version")

    with op.batch_alter_table("changes") as batch_op:
        batch_op.drop_column("created_at")
        batch_op.drop_column("updated_at")


def downgrade() -> None:
    """Возвращает служебные колонки (прежние значения не восстанавливаются)."""
    with op.batch_alter_table("changes") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    for table_name in _ROW_VERSION_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column("row_version", sa.Integer(), nullable=False, server_default="1")
            )
