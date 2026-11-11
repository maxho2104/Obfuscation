"""Проверка миграции N-N задач на временной SQLite-базе.

Сценарий: поднимаем схему до предыдущей ревизии (с колонками task_id),
вставляем тестовые данные, накатываем head, проверяем перенос,
затем проверяем downgrade.
"""

import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

DB_PATH = Path("scripts_dev/_migration_test.db")
PREV_REVISION = "b7c4d2f0a1e9"


def make_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH.as_posix()}")
    return config


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    config = make_config()
    command.upgrade(config, PREV_REVISION)

    material_id = uuid.uuid4().hex
    telegram_id = uuid.uuid4().hex
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO territorial_units (id, name, change_id, row_version) "
            "VALUES ('TU', 'Единица', NULL, 1)"
        )
        conn.execute(
            "INSERT INTO branches (id, name, short_name, territorial_unit_id, change_id, row_version) "
            "VALUES ('F1', 'Филиал', 'Ф1', 'TU', NULL, 1)"
        )
        conn.execute(
            "INSERT INTO scientific_tasks (id, name, type, start_date, change_id, row_version) "
            "VALUES ('T1', 'Задача 1', 'ОЗ', '2026-01-01', NULL, 1)"
        )
        conn.execute(
            "INSERT INTO scientific_materials "
            "(id, type, name, branch_id, task_id, change_id, row_version) "
            f"VALUES ('{material_id}', 'С', 'Материал', 'F1', 'T1', NULL, 1)"
        )
        conn.execute(
            "INSERT INTO telegrams "
            "(id, type, name, branch_id, task_id, change_id, row_version) "
            f"VALUES ('{telegram_id}', 'Т', 'Телеграмма', 'F1', 'T1', NULL, 1)"
        )
        conn.commit()

    command.upgrade(config, "head")

    with sqlite3.connect(DB_PATH) as conn:
        material_links = conn.execute("SELECT material_id, task_id FROM material_tasks").fetchall()
        telegram_links = conn.execute("SELECT telegram_id, task_id FROM telegram_tasks").fetchall()
        material_cols = {row[1] for row in conn.execute("PRAGMA table_info(scientific_materials)")}
        telegram_cols = {row[1] for row in conn.execute("PRAGMA table_info(telegrams)")}

    assert material_links == [(material_id, "T1")], material_links
    assert telegram_links == [(telegram_id, "T1")], telegram_links
    assert "task_id" not in material_cols
    assert "task_id" not in telegram_cols
    print("upgrade OK: связи перенесены, колонки удалены")

    command.downgrade(config, PREV_REVISION)

    with sqlite3.connect(DB_PATH) as conn:
        material_task = conn.execute(
            "SELECT task_id FROM scientific_materials WHERE id = ?", (material_id,)
        ).fetchone()[0]
        telegram_task = conn.execute(
            "SELECT task_id FROM telegrams WHERE id = ?", (telegram_id,)
        ).fetchone()[0]

    assert material_task == "T1", material_task
    assert telegram_task == "T1", telegram_task
    print("downgrade OK: колонки возвращены, данные восстановлены")

    command.upgrade(config, "head")
    print("Повторный upgrade OK")
    try:
        DB_PATH.unlink()
    except PermissionError:
        pass  # Windows: файл освобождается после выхода процесса


if __name__ == "__main__":
    main()
