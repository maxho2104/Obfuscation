"""Удаление исторической связи «задача — сотрудник» (task_employees)

Связь задачи с сотрудниками через ассоциативную таблицу ``task_employees``
(``ScientificTask.employees`` / ``Employee.tasks``) больше не используется:
панель сведений ОШС, вкладка «Задачи» и статистика переведены на
``added_tasks`` (AddedTask). Таблица удаляется.

Данные не переносятся: назначения ведутся через ``added_tasks``;
downgrade пересоздаёт таблицу пустой (для совместимости схемы).

Revision ID: f4c6a8d0e2b1
Revises: e1a4b7c9d2f6
Create Date: 2026-11-16 23:55:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f4c6a8d0e2b1"
down_revision: Union[str, None] = "e1a4b7c9d2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Удаляет таблицу task_employees (если она ещё существует)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_employees" in inspector.get_table_names():
        op.drop_table("task_employees")


def downgrade() -> None:
    """Пересоздаёт пустую таблицу task_employees (данные не восстанавливаются)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_employees" not in inspector.get_table_names():
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
