"""Проверка миграции истории участий в рабочих группах на временной SQLite-базе.

Сценарий: поднимаем схему до предыдущей ревизии (с колонками группы
в ``employees``), вставляем тестовые данные, накатываем head, проверяем
перенос в ``workgroup_memberships``, затем проверяем downgrade.
"""

import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

DB_PATH = Path("scripts_dev/_migration_test.db")
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
    group_old = uuid.uuid4().hex
    employee_with = uuid.uuid4().hex
    employee_without = uuid.uuid4().hex
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
            "INSERT INTO departments (id, name, short_name, active, branch_id, change_id) "
            f"VALUES ('{department_id}', 'Отдел', 'О1', 1, 'F1', NULL)"
        )
        conn.execute(
            "INSERT INTO working_groups (id, name, comment, active, department_id, change_id) "
            f"VALUES ('{group_old}', 'Группа', NULL, 1, '{department_id}', NULL)"
        )
        conn.execute(
            "INSERT INTO employees (id, last_name, first_name, middle_name, position, active, "
            "academic_title_id, department_id, working_group_id, "
            "workgroup_start_date, workgroup_end_date, change_id) "
            f"VALUES ('{employee_with}', 'Иванов', 'Иван', NULL, NULL, 1, "
            f"NULL, '{department_id}', '{group_old}', '2024-01-01', '2024-12-31', NULL)"
        )
        conn.execute(
            "INSERT INTO employees (id, last_name, first_name, middle_name, position, active, "
            "academic_title_id, department_id, working_group_id, "
            "workgroup_start_date, workgroup_end_date, change_id) "
            f"VALUES ('{employee_without}', 'Петров', 'Пётр', NULL, NULL, 1, "
            f"NULL, '{department_id}', NULL, NULL, NULL, NULL)"
        )
        conn.commit()

    command.upgrade(config, "head")

    with sqlite3.connect(DB_PATH) as conn:
        memberships = conn.execute(
            "SELECT employee_id, working_group_id, start_date, end_date, change_id "
            "FROM workgroup_memberships"
        ).fetchall()
        employee_cols = {row[1] for row in conn.execute("PRAGMA table_info(employees)")}

    assert len(memberships) == 1, memberships
    emp_id, wg_id, start, end, change_id = memberships[0]
    assert emp_id.replace("-", "") == employee_with, memberships
    assert wg_id.replace("-", "") == group_old, memberships
    assert start == "2024-01-01", memberships
    assert end == "2024-12-31", memberships
    assert change_id is None, memberships
    assert "working_group_id" not in employee_cols
    assert "workgroup_start_date" not in employee_cols
    assert "workgroup_end_date" not in employee_cols
    print("upgrade OK: участие перенесено, старые колонки удалены")

    command.downgrade(config, PREV_REVISION)

    with sqlite3.connect(DB_PATH) as conn:
        restored = conn.execute(
            "SELECT working_group_id, workgroup_start_date, workgroup_end_date "
            "FROM employees WHERE id = ?", (employee_with,)
        ).fetchone()
        empty = conn.execute(
            "SELECT working_group_id FROM employees WHERE id = ?", (employee_without,)
        ).fetchone()

    assert restored[0] == group_old, restored
    assert restored[1] == "2024-01-01", restored
    assert restored[2] == "2024-12-31", restored
    assert empty[0] is None, empty
    print("downgrade OK: колонки возвращены, последнее участие восстановлено")

    command.upgrade(config, "head")
    print("Повторный upgrade OK")
    try:
        DB_PATH.unlink()
    except PermissionError:
        pass  # Windows: файл освобождается после выхода процесса


if __name__ == "__main__":
    main()
