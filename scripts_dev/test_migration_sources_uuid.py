"""Проверка миграции источников (UUID + индекс) на временной SQLite-базе.

Сценарий: поднимаем схему до предыдущей ревизии (строковый PK sources),
вставляем тестовые данные (источники, связки, запись Change),
накатываем head, проверяем перенос id -> UUID, индексы и обновление
changes; затем проверяем downgrade и повторный upgrade.
"""

import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config

DB_PATH = Path("scripts_dev/_migration_sources_test.db")
PREV_REVISION = "f4c6a8d0e2b1"


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
            "INSERT INTO territorial_units (id, name, change_id) "
            "VALUES ('TU', 'Единица', NULL)"
        )
        conn.execute(
            "INSERT INTO branches (id, name, short_name, territorial_unit_id, change_id) "
            "VALUES ('F1', 'Филиал', 'Ф1', 'TU', NULL)"
        )
        conn.execute(
            "INSERT INTO scientific_materials (id, type, name, branch_id, change_id) "
            f"VALUES ('{material_id}', 0, 'Материал', 'F1', NULL)"
        )
        conn.execute(
            "INSERT INTO telegrams (id, type, name, branch_id, change_id) "
            f"VALUES ('{telegram_id}', 0, 'Телеграмма', 'F1', NULL)"
        )
        conn.execute(
            "INSERT INTO sources (id, type, comment, change_id) "
            "VALUES ('SRC-001', 0, 'Первый', NULL)"
        )
        conn.execute(
            "INSERT INTO sources (id, type, comment, change_id) "
            "VALUES ('SRC-002', 1, 'Второй', NULL)"
        )
        conn.execute(
            "INSERT INTO material_sources (material_id, source_id) "
            f"VALUES ('{material_id}', 'SRC-001')"
        )
        conn.execute(
            "INSERT INTO telegram_sources (telegram_id, source_id) "
            f"VALUES ('{telegram_id}', 'SRC-002')"
        )
        conn.execute(
            "INSERT INTO changes (entity_name, entity_pk, changed_at, changed_fields, operation_type, exported_at) "
            "VALUES ('Source', 'SRC-001', '2026-01-01 00:00:00', '[]', 1, NULL)"
        )
        conn.commit()

    command.upgrade(config, "head")

    with sqlite3.connect(DB_PATH) as conn:
        source_rows = conn.execute(
            'SELECT id, "index", type, comment FROM sources ORDER BY "index"'
        ).fetchall()
        material_links = conn.execute(
            "SELECT material_id, source_id FROM material_sources"
        ).fetchall()
        telegram_links = conn.execute(
            "SELECT telegram_id, source_id FROM telegram_sources"
        ).fetchall()
        change_pk = conn.execute(
            "SELECT entity_pk FROM changes WHERE entity_name = 'Source'"
        ).fetchone()[0]

    assert len(source_rows) == 2, source_rows
    id_by_index = {index: pk for pk, index, _type, _comment in source_rows}
    assert set(id_by_index) == {"SRC-001", "SRC-002"}, id_by_index
    # На SQLite UUID хранится как 32 символа hex без дефисов.
    for pk in id_by_index.values():
        uuid.UUID(pk)
        assert len(pk) == 32, pk
    assert (material_id, id_by_index["SRC-001"]) in material_links, material_links
    assert (telegram_id, id_by_index["SRC-002"]) in telegram_links, telegram_links
    assert change_pk == str(uuid.UUID(id_by_index["SRC-001"])), (
        change_pk,
        id_by_index,
    )
    print("upgrade OK: id -> UUID, индексы перенесены, связи и changes обновлены")

    command.downgrade(config, PREV_REVISION)

    with sqlite3.connect(DB_PATH) as conn:
        source_ids = {
            row[0] for row in conn.execute("SELECT id FROM sources")
        }
        material_link = conn.execute(
            "SELECT source_id FROM material_sources"
        ).fetchone()[0]
        telegram_link = conn.execute(
            "SELECT source_id FROM telegram_sources"
        ).fetchone()[0]
        change_pk = conn.execute(
            "SELECT entity_pk FROM changes WHERE entity_name = 'Source'"
        ).fetchone()[0]

    assert source_ids == {"SRC-001", "SRC-002"}, source_ids
    assert material_link == "SRC-001", material_link
    assert telegram_link == "SRC-002", telegram_link
    assert change_pk == "SRC-001", change_pk
    print("downgrade OK: строковые id восстановлены из индексов")

    command.upgrade(config, "head")
    print("Повторный upgrade OK")
    try:
        DB_PATH.unlink()
    except PermissionError:
        pass  # Windows: файл освобождается после выхода процесса


if __name__ == "__main__":
    main()
