"""Таблица запросов контрагенту (missing_requests)

Накопление сущностей, присланных контрагентом на изменение/удаление без
известного в локальной базе первичного ключа. Перечень выгружается в
``missing.json`` при следующем экспорте, после чего таблица очищается.
Таблица служебная: в delta-tracking и обычный экспорт не участвует.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-18 14:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "missing_requests" in inspector.get_table_names():
        return
    op.create_table(
        "missing_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "branch_id",
            sa.String(50),
            sa.ForeignKey("branches.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("entity_name", sa.String(100), nullable=False),
        sa.Column("entity_pk", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Index("ix_missing_requests_entity_name", "entity_name"),
        sa.Index("ix_missing_requests_entity_pk", "entity_pk"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "missing_requests" not in inspector.get_table_names():
        return
    op.drop_table("missing_requests")
