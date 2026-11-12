"""Проверка миграции b1d2e3f4a5c6 (подготовка схемы к диалогам) на временной SQLite-базе.

Сценарий: поднимаем схему до предыдущей ревизии, вставляем тестовые
данные (адресация с датой, список оценок с оценкой), накатываем head,
проверяем новые колонки и перенос даты оценки из списка, затем проверяем
downgrade и повторный upgrade.
"""

import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

DB_PATH = Path("scripts_dev/_migration_test_editing.db")
PREV_REVISION = "a9de48b1c2f3"


def make_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH.as_posix()}")
    return config


def _notnull(columns: dict, name: str) -> int:
    """Возвращает флаг NOT NULL колонки из PRAGMA table_info."""
    return next(row[3] for row in columns if row[1] == name)


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    config = make_config()
    command.upgrade(config, PREV_REVISION)

    telegram_id = uuid.uuid4().hex
    address_id = uuid.uuid4().hex
    list_id = uuid.uuid4().hex
    evaluation_id = uuid.uuid4().hex
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO territorial_units (id, name, change_id) "
            "VALUES ('TU', 'Единица', NULL)"
        )
        conn.execute(
            "INSERT INTO branches (id, name, short_name, territorial_unit_id, change_id) "
            "VALUES ('F1', 'Филиал', 'Ф1', 'TU', NULL)"
        )
        conn.execute("INSERT INTO leaders (id, active, change_id) VALUES ('L1', 1, NULL)")
        conn.execute(
            "INSERT INTO telegrams (id, type, name, branch_id, change_id) "
            f"VALUES ('{telegram_id}', 0, 'Телеграмма', 'F1', NULL)"
        )
        conn.execute(
            "INSERT INTO report_addresses (id, report_date, telegram_id, leader_id, change_id) "
            f"VALUES ('{address_id}', '2026-03-05', '{telegram_id}', 'L1', NULL)"
        )
        conn.execute(
            "INSERT INTO evaluation_lists (id, number, date, change_id) "
            f"VALUES ('{list_id}', 'ОЦ-1', '2026-05-10', NULL)"
        )
        conn.execute(
            "INSERT INTO evaluations (id, value, evaluation_list_id, change_id) "
            f"VALUES ('{evaluation_id}', 2, '{list_id}', NULL)"
        )
        conn.commit()

    command.upgrade(config, "head")

    with sqlite3.connect(DB_PATH) as conn:
        material_cols = conn.execute("PRAGMA table_info(scientific_materials)").fetchall()
        address_cols = conn.execute("PRAGMA table_info(report_addresses)").fetchall()
        evaluation_cols = conn.execute("PRAGMA table_info(evaluations)").fetchall()
        evaluation_date = conn.execute(
            "SELECT date FROM evaluations WHERE id = ?", (evaluation_id,)
        ).fetchone()[0]
        address_date = conn.execute(
            "SELECT report_date FROM report_addresses WHERE id = ?", (address_id,)
        ).fetchone()[0]
        # Новая схема должна допускать пустую дату доклада и оценку без списка
        conn.execute(
            "INSERT INTO report_addresses (id, report_date, telegram_id, leader_id, change_id) "
            f"VALUES ('{uuid.uuid4().hex}', NULL, '{telegram_id}', 'L1', NULL)"
        )
        conn.execute(
            "INSERT INTO evaluations (id, value, date, evaluation_list_id, change_id) "
            f"VALUES ('{uuid.uuid4().hex}', 1, '2026-06-01', NULL, NULL)"
        )
        conn.commit()

    assert "permit_date" in {row[1] for row in material_cols}
    assert _notnull(material_cols, "permit_date") == 0
    assert _notnull(address_cols, "report_date") == 0
    assert _notnull(evaluation_cols, "date") == 1
    assert _notnull(evaluation_cols, "evaluation_list_id") == 0
    assert evaluation_date == "2026-05-10", evaluation_date
    assert address_date == "2026-03-05", address_date
    print("upgrade OK: колонки добавлены, дата оценки перенесена из списка")

    command.downgrade(config, PREV_REVISION)

    with sqlite3.connect(DB_PATH) as conn:
        material_cols = conn.execute("PRAGMA table_info(scientific_materials)").fetchall()
        address_cols = conn.execute("PRAGMA table_info(report_addresses)").fetchall()
        evaluation_cols = conn.execute("PRAGMA table_info(evaluations)").fetchall()
        listless_left = conn.execute(
            "SELECT COUNT(*) FROM evaluations WHERE evaluation_list_id IS NULL"
        ).fetchone()[0]
        address_date = conn.execute(
            "SELECT report_date FROM report_addresses WHERE id = ?", (address_id,)
        ).fetchone()[0]

    assert "permit_date" not in {row[1] for row in material_cols}
    assert "date" not in {row[1] for row in evaluation_cols}
    assert _notnull(address_cols, "report_date") == 1
    assert _notnull(evaluation_cols, "evaluation_list_id") == 1
    assert listless_left == 0, listless_left
    assert address_date is not None, address_date
    print("downgrade OK: колонки удалены, NOT NULL возвращён, потери задокументированы выполнены")

    command.upgrade(config, "head")
    print("Повторный upgrade OK")
    try:
        DB_PATH.unlink()
    except PermissionError:
        pass  # Windows: файл освобождается после выхода процесса


if __name__ == "__main__":
    main()
