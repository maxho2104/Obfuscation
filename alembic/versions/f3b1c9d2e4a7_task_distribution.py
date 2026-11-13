"""Назначения научных задач узлам иерархии

Вводится таблица ``added_tasks`` — единая полиморфная таблица назначений
задач регионам, филиалам, отделам, рабочим группам и сотрудникам.
Назначения хранятся отдельно от документов и участвуют в delta-обмене
как tracked-сущность.

Историческая связь «задача — сотрудник» (``task_employees``) сохраняется
для панели ОШС и статистики по исполнителям; распределение задач по
иерархии ведётся через ``added_tasks``.

Данные не переносятся: старые связи задач с сотрудниками не имеют
однозначного соответствия новой иерархии.

Revision ID: f3b1c9d2e4a7
Revises: b1d2e3f4a5c6
Create Date: 2026-11-12 22:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f3b1c9d2e4a7"
down_revision: Union[str, None] = "b1d2e3f4a5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создаёт added_tasks и удаляет task_employees."""
    op.create_table(
        "added_tasks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.String(length=50), nullable=False),
        sa.Column("node_type", sa.String(length=20), nullable=False),
        sa.Column("node_id", sa.String(length=50), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["scientific_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "node_type",
            "node_id",
            name="uix_added_task_node",
        ),
    )
    op.create_index(
        "ix_added_tasks_task_id", "added_tasks", ["task_id"], unique=False
    )
    op.create_index(
        "ix_added_tasks_node", "added_tasks", ["node_type", "node_id"], unique=False
    )


def downgrade() -> None:
    """Удаляет назначения."""
    op.drop_index("ix_added_tasks_node", table_name="added_tasks")
    op.drop_index("ix_added_tasks_task_id", table_name="added_tasks")
    op.drop_table("added_tasks")
