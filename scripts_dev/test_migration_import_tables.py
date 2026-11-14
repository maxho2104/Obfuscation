"""Проверка миграции инфраструктуры импорта оценок на SQLite.

Сценарий: поднимаем схему до f3b1c9d2e4a7, накатываем head, проверяем
таблицы import_log/import_rows и представление import_matches, вставляем
журнал и строку, затем откатываемся и проверяем удаление объектов.
"""

import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

DB_PATH = Path("scripts_dev/_migration_import_tables.db")
PREV_REVISION = "f3b1c9d2e4a7"


def make_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH.as_posix()}")
    return config


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    config = make_config()
    command.upgrade(config, PREV_REVISION)
    command.upgrade(config, "head")

    with sqlite3.connect(DB_PATH) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        views = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            )
        }
        assert "import_log" in tables, tables
        assert "import_rows" in tables, tables
        assert "import_matches" in views, views
        evaluation_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(evaluations)")
        }
        assert "effect" in evaluation_columns, evaluation_columns

        conn.execute(
            "INSERT INTO import_log "
            "(year, doc_no, doc_date, file_name, file_hash, scheme_name, "
            " matched_rule, started_at, status) "
            "VALUES (2026, 'DOC-1', '2026-03-10', 'data.txt', ?, 'fixed', "
            "'material', '2026-03-10 10:00:00', 'committed')",
            ("a" * 64,),
        )
        log_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        entity_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO import_rows "
            "(year, import_id, source_row_no, raw_line, data, status, "
            " branch_code, outgoing_no, year_month, value_code, evaluation_date, "
            " matched_entity_type, matched_entity_id, created_at) "
            "VALUES (2026, ?, 2, 'line', '{}', 'matched', '01-1-01', "
            "'1234567890', '202603', 'П', '2026-03-05', 'material', ?, "
            "'2026-03-10 10:00:00')",
            (log_id, entity_id),
        )
        conn.commit()
        matched = conn.execute(
            "SELECT doc_no, branch_code, value_code FROM import_matches"
        ).fetchone()
    assert matched == ("DOC-1", "01-1-01", "П"), matched
    print("upgrade OK: import_log, import_rows и import_matches созданы")

    command.downgrade(config, PREV_REVISION)
    with sqlite3.connect(DB_PATH) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        views = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            )
        }
        assert "import_log" not in tables, tables
        assert "import_rows" not in tables, tables
        assert "import_matches" not in views, views
    print("downgrade OK: объекты импорта удалены")

    command.upgrade(config, "head")
    print("Повторный upgrade OK")
    try:
        DB_PATH.unlink()
    except PermissionError:
        pass  # Windows: файл освобождается после выхода процесса


if __name__ == "__main__":
    main()
