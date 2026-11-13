"""Проверка миграции назначений задач на временной SQLite-базе.

Сценарий: поднимаем схему до ревизии b1d2e3f4a5c6 (последняя ревизия
перед added_tasks), вставляем справочники, задачу и историческую связь
«задача — сотрудник», накатываем head, проверяем новую таблицу и
сохранение task_employees, затем откатываемся и проверяем обратное.
"""

import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

DB_PATH = Path("scripts_dev/_migration_task_distribution.db")
PREV_REVISION = "b1d2e3f4a5c6"


def make_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH.as_posix()}")
    return config


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    config = make_config()
    command.upgrade(config, PREV_REVISION)

    department_id = uuid.uuid4().hex
    employee_id = uuid.uuid4().hex
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO territorial_units (id, name, change_id) "
            "VALUES ('TU', 'Единица', NULL)"
        )
        conn.execute(
            "INSERT INTO branches (id, name, short_name, territorial_unit_id, change_id) "
            "VALUES ('F1', 'Филиал', 'Ф1', 'TU', NULL)"
        )
        conn.execute(
            "INSERT INTO departments (id, name, branch_id, active, change_id) "
            f"VALUES ('{department_id}', 'Отдел', 'F1', 1, NULL)"
        )
        conn.execute(
            "INSERT INTO employees "
            "(id, last_name, first_name, department_id, active, change_id) "
            f"VALUES ('{employee_id}', 'Иванов', 'Иван', '{department_id}', 1, NULL)"
        )
        conn.execute(
            "INSERT INTO scientific_tasks (id, name, type, start_date, change_id) "
            "VALUES ('T1', 'Задача 1', 0, '2026-01-01', NULL)"
        )
        conn.execute(
            "INSERT INTO task_employees (task_id, employee_id) VALUES ('T1', ?)",
            (employee_id,),
        )
        conn.commit()

    command.upgrade(config, "head")

    assignment_id = uuid.uuid4().hex
    with sqlite3.connect(DB_PATH) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "added_tasks" in tables, tables
        assert "task_employees" in tables, tables
        conn.execute(
            "INSERT INTO added_tasks "
            "(id, task_id, node_type, node_id, change_id) "
            "VALUES (?, 'T1', 'region', '77', NULL)",
            (assignment_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT task_id, node_type, node_id FROM added_tasks WHERE id = ?",
            (assignment_id,),
        ).fetchone()
        legacy = conn.execute(
            "SELECT task_id, employee_id FROM task_employees"
        ).fetchone()
    assert row == ("T1", "region", "77"), row
    assert legacy == ("T1", employee_id), legacy
    print("upgrade OK: added_tasks создана, task_employees сохранена")

    command.downgrade(config, PREV_REVISION)

    with sqlite3.connect(DB_PATH) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "task_employees" in tables, tables
        assert "added_tasks" not in tables, tables
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(task_employees)")
        }
    assert columns == {"task_id", "employee_id"}, columns
    print("downgrade OK: added_tasks удалена, task_employees сохранена")

    command.upgrade(config, "head")
    print("Повторный upgrade OK")
    try:
        DB_PATH.unlink()
    except PermissionError:
        pass  # Windows: файл освобождается после выхода процесса


if __name__ == "__main__":
    main()
