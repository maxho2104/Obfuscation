"""Добавление поля «Эффект» в оценки

Импорт оценочных данных формата «Эффект» сохраняет числовое значение
эффекта в оценке. Поле необязательное, поэтому перенос данных не требуется.

Revision ID: d2f4a6c8e0b1
Revises: c8f1a3d5e7b9
Create Date: 2026-11-14 15:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2f4a6c8e0b1"
down_revision: Union[str, None] = "c8f1a3d5e7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("evaluations")}
    if "effect" in columns:
        return
    with op.batch_alter_table("evaluations") as batch:
        batch.add_column(sa.Column("effect", sa.Numeric(15, 2), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("evaluations")}
    if "effect" not in columns:
        return
    with op.batch_alter_table("evaluations") as batch:
        batch.drop_column("effect")
