"""Назначения научных задач узлам иерархии

Вводится таблица ``added_tasks`` — единая полиморфная таблица назначений
задач регионам, филиалам, отделам, рабочим группам и сотрудникам.
Назначения хранятся отдельно от документов и участвуют в delta-обмене
как tracked-сущность.

Одновременно удаляется устаревшая связь «задача — сотрудник»
(``task_employees``): распределение задач теперь описывается назначениями
на узлы, а не прямым списком сотрудников.

Данные не переносятся: старые связи задач с сотрудниками не имеют
однозначного соответствия новой иерархии.

Revision ID: f3b1c9d2e4a7
Revises: c4a8f1b2d3e4
Create Date: 2026-11-12 22:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f3b1c9d2e4a7"
down_revision: Union[str, None] = "c4a8f1b2d3e4"
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
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
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
    op.drop_table("task_employees")


def downgrade() -> None:
    """Удаляет назначения и восстанавливает task_employees."""
    op.create_table(
        "task_employees",
        sa.Column("task_id", sa.String(length=50), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["scientific_tasks.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id", "employee_id"),
    )
    op.drop_index("ix_added_tasks_node", table_name="added_tasks")
    op.drop_index("ix_added_tasks_task_id", table_name="added_tasks")
    op.drop_table("added_tasks")
