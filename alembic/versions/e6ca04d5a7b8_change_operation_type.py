"""Change: тип операции и дата экспорта

Добавляет таблице ``changes``:
- ``operation_type`` (smallint, not null, default 1) — тип операции над
  сущностью: 0 — создание, 1 — изменение, 2 — удаление; заменяет
  специальный маркер ``__DELETED__`` в ``changed_fields``;
- ``exported_at`` (datetime, nullable) — дата записи сущности в
  экспортный файл; запись Change после экспорта сохраняется и
  удаляется по истечении срока хранения (приложение, настройка).

Перенос данных: записи с маркером ``__DELETED__`` в ``changed_fields``
становятся удалениями (operation_type=2, changed_fields очищается);
остальные считаются изменениями (operation_type=1).

Downgrade возвращает маркер удаления в changed_fields и удаляет колонки.

Revision ID: e6ca04d5a7b8
Revises: d5b9e3c4f6a7
Create Date: 2026-11-11 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e6ca04d5a7b8"
down_revision: Union[str, None] = "d5b9e3c4f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет колонки operation_type и exported_at, переносит маркер удаления."""
    with op.batch_alter_table("changes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "operation_type",
                sa.SmallInteger(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(sa.Column("exported_at", sa.DateTime(), nullable=True))

    # __DELETED__ (константа DELETION_MARKER, удалена из core.constants)
    # экранируем подчёркивания, т.к. в LIKE это служебный символ
    op.execute(
        "UPDATE changes SET operation_type = 2, changed_fields = '[]' "
        r"WHERE changed_fields LIKE '%\_\_DELETED\_\_%' ESCAPE '\'"
    )


def downgrade() -> None:
    """Возвращает маркер удаления и удаляет колонки."""
    op.execute(
        'UPDATE changes SET changed_fields = \'["__DELETED__"]\' '
        "WHERE operation_type = 2"
    )
    with op.batch_alter_table("changes") as batch_op:
        batch_op.drop_column("exported_at")
        batch_op.drop_column("operation_type")
