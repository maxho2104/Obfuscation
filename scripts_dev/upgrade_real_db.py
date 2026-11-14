"""Приведение существующей SQLite-базы к текущей схеме.

Скрипт нужен для баз, созданных старой версией приложения через
``create_all`` (без таблицы ``alembic_version``). Он добавляет недостающие
колонки, переводит строковые коды перечислений в целые числа и ставит
ревизию ``f3b1c9d2e4a7``.

Перед запуском сделайте резервную копию файла БД.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects.postgresql import UUID as PGUUID

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

REVISION = "f3b1c9d2e4a7"


def _convert_column(
    op: Operations,
    table: str,
    column: str,
    mapping: Dict[str, int],
    nullable: bool,
) -> None:
    """Переводит строковые коды колонки в целые числа."""
    tmp = f"{column}__conv"
    with op.batch_alter_table(table) as batch_op:
        batch_op.add_column(sa.Column(tmp, sa.SmallInteger(), nullable=True))
    cases = " ".join(f"WHEN '{code}' THEN {value}" for code, value in mapping.items())
    op.execute(f"UPDATE {table} SET {tmp} = CASE {column} {cases} ELSE NULL END")
    with op.batch_alter_table(table) as batch_op:
        batch_op.drop_column(column)
        batch_op.alter_column(tmp, new_column_name=column, nullable=nullable)


def upgrade_database(path: Path) -> None:
    """Дополняет схему и фиксирует текущую ревизию Alembic."""
    engine = create_engine(f"sqlite:///{path.as_posix()}", future=True)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        context = MigrationContext.configure(connection)
        op = Operations(context)
        inspector = inspect(connection)

        def columns(table: str) -> set:
            return {column["name"] for column in inspector.get_columns(table)}

        change_columns = columns("changes")
        if "operation_type" not in change_columns:
            op.add_column(
                "changes",
                sa.Column(
                    "operation_type",
                    sa.SmallInteger(),
                    nullable=False,
                    server_default="1",
                ),
            )
        if "exported_at" not in change_columns:
            op.add_column(
                "changes",
                sa.Column("exported_at", sa.DateTime(), nullable=True),
            )

        connection.exec_driver_sql(
            "UPDATE changes SET operation_type = 2, changed_fields = '[]' "
            "WHERE changed_fields LIKE '%__DELETED__%'"
        )

        if "permit_date" not in columns("scientific_materials"):
            op.add_column(
                "scientific_materials",
                sa.Column("permit_date", sa.Date(), nullable=True),
            )

        if "date" not in columns("evaluations"):
            op.add_column(
                "evaluations",
                sa.Column("date", sa.Date(), nullable=True),
            )
        connection.exec_driver_sql(
            "UPDATE evaluations SET date = ("
            "SELECT date FROM evaluation_lists "
            "WHERE evaluation_lists.id = evaluations.evaluation_list_id) "
            "WHERE date IS NULL"
        )
        with op.batch_alter_table("evaluations") as batch_op:
            batch_op.alter_column(
                "date",
                existing_type=sa.Date(),
                existing_nullable=True,
                nullable=False,
            )
            batch_op.alter_column(
                "evaluation_list_id",
                existing_type=PGUUID(as_uuid=True),
                existing_nullable=False,
                nullable=True,
            )

        with op.batch_alter_table("report_addresses") as batch_op:
            batch_op.alter_column(
                "report_date",
                existing_type=sa.Date(),
                existing_nullable=False,
                nullable=True,
            )

        for table, column, mapping, nullable in ENUM_COLUMNS:
            values = [
                row[0]
                for row in connection.exec_driver_sql(
                    f"SELECT DISTINCT {column} FROM {table} LIMIT 5"
                )
            ]
            if all(isinstance(value, int) for value in values):
                continue
            _convert_column(op, table, column, mapping, nullable)

        connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.stamp(config, REVISION)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="путь к файлу SQLite")
    args = parser.parse_args(argv[1:])
    path = Path(args.database).resolve()
    if not path.exists():
        parser.error(f"файл не найден: {path}")
    upgrade_database(path)
    print(f"Схема обновлена, ревизия: {REVISION}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
