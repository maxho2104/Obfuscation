"""Проверка миграции avatar_file на временной SQLite-базе.

Сценарий: поднимаем схему до актуальной головы (c3d4e5f6a7b8, последняя
ревизия перед avatar_file), вставляем филиал, накатываем head — у таблиц
ОШС появляется колонка avatar_file; откатываемся — колонка исчезает;
повторный upgrade — колонка снова появляется.
"""

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

DB_PATH = Path("scripts_dev/_migration_avatar.db")
PREV_REVISION = "c3d4e5f6a7b8"
TABLES = ("branches", "departments", "working_groups", "employees")


def make_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH.as_posix()}")
    return config


def avatar_columns() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        return {
            table: {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            for table in TABLES
        }


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    config = make_config()
    command.upgrade(config, PREV_REVISION)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO territorial_units (id, name, change_id) "
            "VALUES ('TU', 'Единица', NULL)"
        )
        conn.execute(
            "INSERT INTO branches (id, name, short_name, territorial_unit_id, change_id) "
            "VALUES ('F1', 'Филиал', 'Ф1', 'TU', NULL)"
        )
        conn.commit()

    command.upgrade(config, "head")
    columns = avatar_columns()
    for table in TABLES:
        assert "avatar_file" in columns[table], (table, columns[table])
    print("upgrade OK: колонка avatar_file добавлена в таблицы ОШС")

    command.downgrade(config, PREV_REVISION)
    columns = avatar_columns()
    for table in TABLES:
        assert "avatar_file" not in columns[table], (table, columns[table])
    print("downgrade OK: колонка avatar_file удалена")

    command.upgrade(config, "head")
    columns = avatar_columns()
    for table in TABLES:
        assert "avatar_file" in columns[table], (table, columns[table])
    print("Повторный upgrade OK")
    try:
        DB_PATH.unlink()
    except PermissionError:
        pass  # Windows: файл освобождается после выхода процесса


if __name__ == "__main__":
    main()
