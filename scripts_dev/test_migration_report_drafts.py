"""Проверяет миграцию черновиков отчётов на временной SQLite-базе."""

import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config


DB_PATH = Path("scripts_dev/_migration_report_drafts.db")
PREVIOUS_REVISION = "c7e2a1b9d3f5"


def _config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH.as_posix()}")
    return config


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    config = _config()
    command.upgrade(config, PREVIOUS_REVISION)

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "INSERT INTO territorial_units (id, name, change_id) "
            "VALUES ('TU', 'Единица', NULL)"
        )
        connection.execute(
            "INSERT INTO branches "
            "(id, name, short_name, territorial_unit_id, change_id) "
            "VALUES ('BR', 'Филиал', 'Ф', 'TU', NULL)"
        )
        connection.commit()

    command.upgrade(config, "head")
    draft_id = str(uuid.uuid4())
    with sqlite3.connect(DB_PATH) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(report_drafts)")
        }
        connection.execute(
            "INSERT INTO report_drafts "
            "(id, report_type, year, period_number, conclusion, created_at, "
            "updated_at, branch_id, change_id) VALUES (?, 0, 2026, 7, ?, ?, ?, 'BR', NULL)",
            (draft_id, "Вывод", "2026-11-15 12:00:00", "2026-11-15 12:00:00"),
        )
        try:
            connection.execute(
                "INSERT INTO report_drafts "
                "(id, report_type, year, period_number, created_at, updated_at, "
                "branch_id, change_id) VALUES (?, 0, 2026, 7, ?, ?, 'BR', NULL)",
                (
                    str(uuid.uuid4()),
                    "2026-11-15 12:00:00",
                    "2026-11-15 12:00:00",
                ),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Не сработала уникальность периода черновика")

    assert {
        "id",
        "report_type",
        "year",
        "period_number",
        "conclusion",
        "branch_id",
        "change_id",
    }.issubset(columns)

    command.downgrade(config, PREVIOUS_REVISION)
    with sqlite3.connect(DB_PATH) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='report_drafts'"
        ).fetchone()
    assert table is None

    command.upgrade(config, "head")
    print("Миграция report_drafts: upgrade/downgrade/upgrade OK")
    try:
        DB_PATH.unlink()
    except PermissionError:
        pass


if __name__ == "__main__":
    main()
