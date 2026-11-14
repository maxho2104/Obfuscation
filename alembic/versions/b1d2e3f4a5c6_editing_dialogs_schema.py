"""Подготовка схемы к новым диалогам редактирования

Научный материал:
- ``permit_date`` (date, nullable) — дата разрешительного документа,
  пара к ``permit_number`` (элемент «Номер и дата разрешительного
  документа»).

Адресация доклада:
- ``report_date`` становится nullable: пустая дата означает
  «ещё не доложено» (в интерфейсе заполненная дата даёт суффикс «+»).

Оценка:
- новая колонка ``date`` (date, NOT NULL) — дата выставления оценки;
  при миграции заполняется из даты списка оценок (перенос данных);
- ``evaluation_list_id`` становится nullable: оценка может существовать
  без списка (ручное выставление оценок). «Последняя» оценка документа
  далее определяется по ``evaluations.date``.

Downgrade (с явными потерями, прежний формат не имеет места для новых
данных): удаляет ``permit_date`` и ``evaluations.date``; оценки без
списка удаляются вместе со связями; пустые даты доклада заполняются
текущей датой; NOT NULL возвращается у ``report_date`` и
``evaluation_list_id``.

Revision ID: b1d2e3f4a5c6
Revises: a9de48b1c2f3
Create Date: 2026-11-12 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID


# revision identifiers, used by Alembic.
revision: str = "b1d2e3f4a5c6"
down_revision: Union[str, None] = "a9de48b1c2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет permit_date и evaluations.date, ослабляет NOT NULL."""
    with op.batch_alter_table("scientific_materials") as batch_op:
        batch_op.add_column(sa.Column("permit_date", sa.Date(), nullable=True))

    with op.batch_alter_table("report_addresses") as batch_op:
        batch_op.alter_column(
            "report_date",
            existing_type=sa.Date(),
            existing_nullable=False,
            nullable=True,
        )

    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.add_column(sa.Column("date", sa.Date(), nullable=True))
        batch_op.alter_column(
            "evaluation_list_id",
            existing_type=PGUUID(as_uuid=True),
            existing_nullable=False,
            nullable=True,
        )

    # Перенос данных: дата выставления существующих оценок = дата
    # их списка оценок (NOT NULL evaluation_list_id гарантирует попадание)
    op.execute(
        "UPDATE evaluations SET date = ("
        "SELECT date FROM evaluation_lists "
        "WHERE evaluation_lists.id = evaluations.evaluation_list_id)"
    )

    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.alter_column(
            "date",
            existing_type=sa.Date(),
            existing_nullable=True,
            nullable=False,
        )


def downgrade() -> None:
    """Возвращает прежнюю схему (оценки без списка теряются)."""
    # Оценки без списка в прежней схеме непредставимы — удаляем их
    # вместе со связями (явная потеря данных, см. docstring)
    op.execute(
        "DELETE FROM evaluation_materials WHERE evaluation_id IN ("
        "SELECT id FROM evaluations WHERE evaluation_list_id IS NULL)"
    )
    op.execute(
        "DELETE FROM evaluation_telegrams WHERE evaluation_id IN ("
        "SELECT id FROM evaluations WHERE evaluation_list_id IS NULL)"
    )
    op.execute("DELETE FROM evaluations WHERE evaluation_list_id IS NULL")

    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.alter_column(
            "evaluation_list_id",
            existing_type=PGUUID(as_uuid=True),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.drop_column("date")

    # Пустые даты доклада прежней схеме непредставимы — подставляем
    # текущую дату (явная потеря точности, см. docstring)
    op.execute(
        "UPDATE report_addresses SET report_date = CURRENT_DATE "
        "WHERE report_date IS NULL"
    )
    with op.batch_alter_table("report_addresses") as batch_op:
        batch_op.alter_column(
            "report_date",
            existing_type=sa.Date(),
            existing_nullable=True,
            nullable=False,
        )

    with op.batch_alter_table("scientific_materials") as batch_op:
        batch_op.drop_column("permit_date")
