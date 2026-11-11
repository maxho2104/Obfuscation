"""Связь научной задачи с сущностью (распределение задач)

Создаёт таблицу ``task_entity_links`` — закладку под механизм
распределения научных задач: связь задачи (``task_id``) с произвольной
сущностью через имя класса (``entity_name``) и строковый первичный
ключ (``entity_pk``). Таблица новая, перенос данных не требуется.

Revision ID: f8cc27a9d0e1
Revises: f7db15e6b8c9
Create Date: 2026-11-11 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f8cc27a9d0e1"
down_revision: Union[str, None] = "f7db15e6b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создаёт таблицу связи задачи с сущностью."""
    op.create_table(
        "task_entity_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(length=50), nullable=False),
        sa.Column("entity_name", sa.String(length=100), nullable=False),
        sa.Column("entity_pk", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["scientific_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_entity_links_entity",
        "task_entity_links",
        ["entity_name", "entity_pk"],
    )


def downgrade() -> None:
    """Удаляет таблицу связи задачи с сущностью."""
    op.drop_index("ix_task_entity_links_entity", table_name="task_entity_links")
    op.drop_table("task_entity_links")
