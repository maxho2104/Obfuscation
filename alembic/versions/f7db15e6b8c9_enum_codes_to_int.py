"""Коды перечислений: строки -> целые числа

Колонки с кодами перечислений переводятся с VARCHAR на SMALLINT:
значения IntEnum из core/constants.py (0, 1, 2...), краткий текст
(«С», «ДОК», «Б»...) по-прежнему определяется пакетом предметной
области по семантическому ключу.

Перенос данных: строковые коды пакета scientific-network преобразуются
в числа по фиксированному соответствию; неизвестные коды становятся
NULL (в колонках NOT NULL это прерывает миграцию с ошибкой — такие
значения нужно очистить вручную; после миграции validate_enum_codes
предупреждает оператора об оставшихся расхождениях с пакетом).

Downgrade возвращает строковые коды; числа вне диапазона -> NULL.

Revision ID: f7db15e6b8c9
Revises: e6ca04d5a7b8
Create Date: 2026-11-11 14:30:00.000000

"""
from typing import Dict, Optional

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f7db15e6b8c9"
down_revision = "e6ca04d5a7b8"
branch_labels = None
depends_on = None

# (таблица, колонка, {строковый код: число}, nullable)
ENUM_COLUMNS = [
    (
        "scientific_materials",
        "type",
        {"С": 0, "ДОК": 1, "СПР": 2, "ОП": 3, "ТДОК": 4, "Д": 5},
        False,
    ),
    ("telegrams", "type", {"Т": 0, "ОХР": 1, "ОДР": 2}, False),
    ("telegrams", "report_type", {"ДР": 0, "СДР": 1}, True),
    ("scientific_tasks", "type", {"ОЗ": 0, "ДЗ": 1}, False),
    ("sources", "type", {"ЭО": 0, "НТ": 1}, False),
    ("evaluations", "value", {"Б": 0, "И": 1, "П": 2, "В": 3}, False),
]


def _convert_column(
    table: str,
    column: str,
    mapping: Dict[str, int],
    nullable: bool,
    target_type: sa.types.TypeEngine,
    reverse: bool,
) -> None:
    """Меняет тип колонки с переносом значений через временную колонку.

    reverse=False: строковые коды -> числа; reverse=True: числа -> строки.
    """
    tmp = f"{column}__conv"
    with op.batch_alter_table(table) as batch_op:
        batch_op.add_column(sa.Column(tmp, target_type, nullable=True))
    if reverse:
        cases = " ".join(f"WHEN {value} THEN '{code}'" for code, value in mapping.items())
    else:
        cases = " ".join(f"WHEN '{code}' THEN {value}" for code, value in mapping.items())
    op.execute(f"UPDATE {table} SET {tmp} = CASE {column} {cases} ELSE NULL END")
    with op.batch_alter_table(table) as batch_op:
        batch_op.drop_column(column)
        batch_op.alter_column(tmp, new_column_name=column, nullable=nullable)


def upgrade() -> None:
    """Переводит колонки с кодами перечислений на SMALLINT."""
    for table, column, mapping, nullable in ENUM_COLUMNS:
        _convert_column(table, column, mapping, nullable, sa.SmallInteger(), False)


def downgrade() -> None:
    """Возвращает строковые коды (числа вне диапазона теряются — NULL)."""
    for table, column, mapping, nullable in ENUM_COLUMNS:
        _convert_column(table, column, mapping, nullable, sa.String(50), True)
