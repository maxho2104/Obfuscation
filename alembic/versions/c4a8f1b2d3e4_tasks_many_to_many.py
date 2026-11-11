"""Связь документов с задачами 1-N -> N-N

Связь «документ — научная задача» переводится с внешнего ключа
``task_id`` (одна задача на документ) на ассоциативные таблицы
``material_tasks`` и ``telegram_tasks`` (несколько задач на документ).

Миграция сохраняет данные: существующие значения ``task_id`` переносятся
в ассоциативные таблицы, после чего колонки удаляются.

Downgrade возвращает колонки ``task_id`` и переносит в них по одной
(минимальной по коду) задаче на документ; при множественных связях
остальные связи теряются.

Revision ID: c4a8f1b2d3e4
Revises: b7c4d2f0a1e9
Create Date: 2026-11-09 23:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID


# revision identifiers, used by Alembic.
revision: str = "c4a8f1b2d3e4"
down_revision: Union[str, None] = "b7c4d2f0a1e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создаёт ассоциативные таблицы и переносит связи из task_id."""
    op.create_table(
        "material_tasks",
        sa.Column(
            "material_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("scientific_materials.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            sa.String(50),
            sa.ForeignKey("scientific_tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "telegram_tasks",
        sa.Column(
            "telegram_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("telegrams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            sa.String(50),
            sa.ForeignKey("scientific_tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.execute(
        "INSERT INTO material_tasks (material_id, task_id) "
        "SELECT id, task_id FROM scientific_materials WHERE task_id IS NOT NULL"
    )
    op.execute(
        "INSERT INTO telegram_tasks (telegram_id, task_id) "
        "SELECT id, task_id FROM telegrams WHERE task_id IS NOT NULL"
    )

    with op.batch_alter_table("scientific_materials") as batch_op:
        batch_op.drop_column("task_id")
    with op.batch_alter_table("telegrams") as batch_op:
        batch_op.drop_column("task_id")


def downgrade() -> None:
    """Возвращает колонки task_id (по одной задаче на документ)."""
    with op.batch_alter_table("scientific_materials") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(50), nullable=True))
        batch_op.create_foreign_key(
            "fk_scientific_materials_task_id",
            "scientific_tasks",
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("telegrams") as batch_op:
        batch_op.add_column(sa.Column("task_id", sa.String(50), nullable=True))
        batch_op.create_foreign_key(
            "fk_telegrams_task_id",
            "scientific_tasks",
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        "UPDATE scientific_materials SET task_id = ("
        "SELECT MIN(task_id) FROM material_tasks "
        "WHERE material_tasks.material_id = scientific_materials.id)"
    )
    op.execute(
        "UPDATE telegrams SET task_id = ("
        "SELECT MIN(task_id) FROM telegram_tasks "
        "WHERE telegram_tasks.telegram_id = telegrams.id)"
    )

    op.drop_table("telegram_tasks")
    op.drop_table("material_tasks")
