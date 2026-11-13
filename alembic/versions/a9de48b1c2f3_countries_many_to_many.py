"""Связь документов со странами 1-N -> N-N

Связь «документ — страна» переводится с внешнего ключа ``country_id``
(одна страна на документ) на ассоциативные таблицы ``material_countries``
и ``telegram_countries`` (несколько стран на документ).

Миграция сохраняет данные: существующие ``country_id`` переносятся
в ассоциативные таблицы, после чего колонки удаляются.

Downgrade возвращает колонки ``country_id`` и переносит в них по одной
(минимальной по коду) стране на документ; при множественных связях
остальные теряются.

Revision ID: a9de48b1c2f3
Revises: f8cc27a9d0e1
Create Date: 2026-11-11 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID


# revision identifiers, used by Alembic.
revision: str = "a9de48b1c2f3"
down_revision: Union[str, None] = "f8cc27a9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создаёт ассоциативные таблицы и переносит связи из country_id."""
    op.create_table(
        "material_countries",
        sa.Column(
            "material_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("scientific_materials.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "country_id",
            sa.String(10),
            sa.ForeignKey("countries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_table(
        "telegram_countries",
        sa.Column(
            "telegram_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("telegrams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "country_id",
            sa.String(10),
            sa.ForeignKey("countries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.execute(
        "INSERT INTO material_countries (material_id, country_id) "
        "SELECT id, country_id FROM scientific_materials "
        "WHERE country_id IS NOT NULL"
    )
    op.execute(
        "INSERT INTO telegram_countries (telegram_id, country_id) "
        "SELECT id, country_id FROM telegrams "
        "WHERE country_id IS NOT NULL"
    )

    with op.batch_alter_table("scientific_materials") as batch_op:
        batch_op.drop_column("country_id")
    with op.batch_alter_table("telegrams") as batch_op:
        batch_op.drop_column("country_id")


def downgrade() -> None:
    """Возвращает колонки country_id (по одной стране на документ)."""
    with op.batch_alter_table("scientific_materials") as batch_op:
        batch_op.add_column(sa.Column("country_id", sa.String(10), nullable=True))
        batch_op.create_foreign_key(
            "fk_scientific_materials_country_id",
            "countries",
            ["country_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("telegrams") as batch_op:
        batch_op.add_column(sa.Column("country_id", sa.String(10), nullable=True))
        batch_op.create_foreign_key(
            "fk_telegrams_country_id",
            "countries",
            ["country_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        "UPDATE scientific_materials SET country_id = ("
        "SELECT MIN(country_id) FROM material_countries "
        "WHERE material_countries.material_id = scientific_materials.id)"
    )
    op.execute(
        "UPDATE telegrams SET country_id = ("
        "SELECT MIN(country_id) FROM telegram_countries "
        "WHERE telegram_countries.telegram_id = telegrams.id)"
    )

    op.drop_table("telegram_countries")
    op.drop_table("material_countries")
