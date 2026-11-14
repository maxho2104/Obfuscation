"""Проверка миграции очистки устаревших служебных колонок.

Создаёт временную SQLite-базу, доводит её до ревизии a7d4e2f6b9c1,
имитирует «старую» схему с row_version и changes.created_at/updated_at,
затем применяет c8f1a3d5e7b9 и проверяет удаление колонок, а также
обратный откат и повторный upgrade.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

PREVIOUS_REVISION = "a7d4e2f6b9c1"
CLEANUP_REVISION = "c8f1a3d5e7b9"


def _columns(engine, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table_name)}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="migration_legacy_") as tmp:
        db_path = Path(tmp) / "legacy.db"
        url = f"sqlite:///{db_path.as_posix()}"
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url)

        command.upgrade(config, PREVIOUS_REVISION)
        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE evaluation_lists "
                    "ADD COLUMN row_version INTEGER NOT NULL DEFAULT 1"
                )
            )
            connection.execute(text("ALTER TABLE changes ADD COLUMN created_at DATETIME"))
            connection.execute(text("ALTER TABLE changes ADD COLUMN updated_at DATETIME"))
        assert "row_version" in _columns(engine, "evaluation_lists")
        print("Подготовлена старая схема: evaluation_lists.row_version, changes.created_at/updated_at")

        command.upgrade(config, "head")
        assert "row_version" not in _columns(engine, "evaluation_lists")
        changes_columns = _columns(engine, "changes")
        assert "created_at" not in changes_columns
        assert "updated_at" not in changes_columns
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == CLEANUP_REVISION
        print("upgrade OK: устаревшие колонки удалены, ревизия", version)

        command.downgrade(config, PREVIOUS_REVISION)
        assert "row_version" in _columns(engine, "evaluation_lists")
        assert "created_at" in _columns(engine, "changes")
        print("downgrade OK: служебные колонки возвращены")

        command.upgrade(config, "head")
        assert "row_version" not in _columns(engine, "evaluation_lists")
        engine.dispose()
        print("Повторный upgrade OK")


if __name__ == "__main__":
    main()
