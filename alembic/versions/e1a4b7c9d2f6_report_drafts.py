"""Черновики аналитических отчётов.

Создаёт таблицу ``report_drafts`` для ручных текстовых разделов месячных и
полугодовых отчётов. Таблица новая, перенос существующих данных не требуется.

Revision ID: e1a4b7c9d2f6
Revises: c7e2a1b9d3f5
Create Date: 2026-11-15 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID


revision: str = "e1a4b7c9d2f6"
down_revision: Union[str, None] = "c7e2a1b9d3f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создаёт хранилище ручных разделов отчётов."""
    op.create_table(
        "report_drafts",
        sa.Column("id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.SmallInteger(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("period_number", sa.SmallInteger(), nullable=False),
        sa.Column("recipient", sa.String(length=500), nullable=True),
        sa.Column("shortcomings", sa.Text(), nullable=True),
        sa.Column("significant_results", sa.Text(), nullable=True),
        sa.Column("proposals", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("plan_execution", sa.Text(), nullable=True),
        sa.Column("signatory_position", sa.String(length=500), nullable=True),
        sa.Column("signatory_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("branch_id", sa.String(length=50), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["change_id"],
            ["changes.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "branch_id",
            "report_type",
            "year",
            "period_number",
            name="uix_report_draft_period",
        ),
    )


def downgrade() -> None:
    """Удаляет черновики отчётов вместе с их содержимым."""
    op.drop_table("report_drafts")
