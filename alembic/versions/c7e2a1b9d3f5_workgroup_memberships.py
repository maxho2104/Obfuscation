"""История участия сотрудников в рабочих группах

Связь «сотрудник — рабочая группа» переводится с колонок сотрудника
(``working_group_id``, ``workgroup_start_date``, ``workgroup_end_date`` —
одна группа, при переводе старая связь затиралась) на отдельную таблицу
``workgroup_memberships``: каждый перевод — новая запись, прежнее участие
закрывается датой окончания и сохраняется в истории.

Миграция сохраняет данные: каждому сотруднику с заполненной группой
создаётся запись участия с его датами, после чего старые колонки
удаляются из ``employees``.

Downgrade возвращает колонки в ``employees`` и переносит в них самое
позднее участие сотрудника; остальная история теряется (потерьный
downgrade, история участий обратно не восстанавливается).

Revision ID: c7e2a1b9d3f5
Revises: b1d2e3f4a5c6
Create Date: 2026-11-13 22:00:00.000000

"""
import uuid
from datetime import date
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def _as_date(value) -> Optional[date]:
    """Приводит значение даты из сырого SQL к ``date`` (SQLite отдаёт строки)."""
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


# revision identifiers, used by Alembic.
revision: str = "c7e2a1b9d3f5"
down_revision: Union[str, None] = "b1d2e3f4a5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Создаёт таблицу участий и переносит в неё текущие группы сотрудников."""
    op.create_table(
        "workgroup_memberships",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "employee_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "working_group_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("working_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "change_id",
            sa.Integer(),
            sa.ForeignKey("changes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Перенос текущих связей: UUID новых записей генерируем в Python,
    # чтобы миграция работала и на SQLite, и на PostgreSQL.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, working_group_id, workgroup_start_date, workgroup_end_date "
            "FROM employees WHERE working_group_id IS NOT NULL"
        )
    ).fetchall()
    membership_table = sa.table(
        "workgroup_memberships",
        sa.column("id", PGUUID(as_uuid=True)),
        sa.column("employee_id", PGUUID(as_uuid=True)),
        sa.column("working_group_id", PGUUID(as_uuid=True)),
        sa.column("start_date", sa.Date()),
        sa.column("end_date", sa.Date()),
    )
    for employee_id, group_id, start_date, end_date in rows:
        connection.execute(
            membership_table.insert().values(
                id=uuid.uuid4(),
                employee_id=uuid.UUID(str(employee_id)),
                working_group_id=uuid.UUID(str(group_id)),
                # SQLite возвращает даты строками — приводим к date
                start_date=_as_date(start_date),
                end_date=_as_date(end_date),
            )
        )

    with op.batch_alter_table("employees") as batch_op:
        batch_op.drop_column("working_group_id")
        batch_op.drop_column("workgroup_start_date")
        batch_op.drop_column("workgroup_end_date")


def downgrade() -> None:
    """Возвращает колонки в employees (самое позднее участие, история теряется)."""
    with op.batch_alter_table("employees") as batch_op:
        batch_op.add_column(sa.Column("working_group_id", PGUUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column("workgroup_start_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("workgroup_end_date", sa.Date(), nullable=True))
        batch_op.create_foreign_key(
            "fk_employees_working_group_id",
            "working_groups",
            ["working_group_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        "UPDATE employees SET "
        "working_group_id = ("
        "  SELECT m.working_group_id FROM workgroup_memberships m "
        "  WHERE m.employee_id = employees.id "
        "  ORDER BY m.start_date DESC, m.id DESC LIMIT 1), "
        "workgroup_start_date = ("
        "  SELECT m.start_date FROM workgroup_memberships m "
        "  WHERE m.employee_id = employees.id "
        "  ORDER BY m.start_date DESC, m.id DESC LIMIT 1), "
        "workgroup_end_date = ("
        "  SELECT m.end_date FROM workgroup_memberships m "
        "  WHERE m.employee_id = employees.id "
        "  ORDER BY m.start_date DESC, m.id DESC LIMIT 1)"
    )

    op.drop_table("workgroup_memberships")
