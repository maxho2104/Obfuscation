"""Уникальность исходящих номеров в разрезе филиала

Ограничения ``uix_material_outgoing``/``uix_telegram_outgoing`` расширены
колонкой ``branch_id``: в центральной базе головного офиса хранятся
документы всех филиалов, каждый из которых ведёт нумерацию независимо —
глобальная уникальность «номер + дата» делала такую базу непригодной.
Данные не затрагиваются (ограничение ослаблено).

Downgrade восстанавливает прежние ограничения и может не выполниться,
если в базе уже есть документы разных филиалов с совпадающими номером
и датой (для центральной базы головного офиса это штатная ситуация) —
в этом случае downgrade осознанно отклоняется с ошибкой СУБД.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-18 23:30:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    ("scientific_materials", "uix_material_outgoing"),
    ("telegrams", "uix_telegram_outgoing"),
)
_COLUMNS = ("branch_id", "outgoing_number", "outgoing_date")


def _constraint_columns(inspector, table: str, name: str):
    """Возвращает колонки уникального ограничения (None — не найдено)."""
    for constraint in inspector.get_unique_constraints(table):
        if constraint["name"] == name:
            return list(constraint["column_names"])
    return None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, name in _TABLES:
        columns = _constraint_columns(inspector, table, name)
        if columns == list(_COLUMNS):
            continue
        with op.batch_alter_table(table) as batch:
            if columns is not None:
                batch.drop_constraint(name, type_="unique")
            batch.create_unique_constraint(name, list(_COLUMNS))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, name in _TABLES:
        columns = _constraint_columns(inspector, table, name)
        if columns == ["outgoing_number", "outgoing_date"]:
            continue
        with op.batch_alter_table(table) as batch:
            if columns is not None:
                batch.drop_constraint(name, type_="unique")
            batch.create_unique_constraint(name, ["outgoing_number", "outgoing_date"])
