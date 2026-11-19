"""Добавление колонки avatar_file сущностям ОШС

У элементов ОШС (филиал, отдел, рабочая группа, сотрудник) появляется
необязательная колонка ``avatar_file`` — имя файла аватарки в директории
«Аватарки» файлового хранилища. Поле служебное (``info={"system": True}``),
в диалогах редактирования не отображается.

Перенос данных не требуется: колонка новая, значения пустые.

Revision ID: g5d7e9f1a3c4
Revises: c3d4e5f6a7b8
Create Date: 2026-11-19 22:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "g5d7e9f1a3c4"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("branches", "departments", "working_groups", "employees")


def upgrade() -> None:
    """Добавляет колонку avatar_file в таблицы ОШС."""
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column("avatar_file", sa.String(length=255), nullable=True)
            )


def downgrade() -> None:
    """Удаляет колонку avatar_file."""
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("avatar_file")
