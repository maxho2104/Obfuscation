"""Инфраструктура импорта оценок из текстовых файлов

Создаются таблицы аудита импорта и staging-строк, а также представление
``import_matches`` — выборка совпавших строк. Год хранится колонкой,
поэтому новые годы не требуют DDL и миграций.

Revision ID: a7d4e2f6b9c1
Revises: f3b1c9d2e4a7
Create Date: 2026-11-14 01:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a7d4e2f6b9c1"
down_revision: Union[str, None] = "f3b1c9d2e4a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _bigint_pk() -> sa.types.TypeEngine:
    """BIGSERIAL в PostgreSQL и INTEGER PRIMARY KEY в SQLite."""
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    """Создаёт таблицы импорта и представление совпадений."""
    op.create_table(
        "import_log",
        sa.Column("id", _bigint_pk(), primary_key=True, autoincrement=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("doc_no", sa.String(length=50), nullable=False),
        sa.Column("doc_date", sa.Date(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=True),
        sa.Column("scheme_name", sa.String(length=100), nullable=False),
        sa.Column("matched_rule", sa.String(length=100), nullable=True),
        sa.Column("imported_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unmatched_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
    )
    op.create_index("ix_import_log_year", "import_log", ["year"], unique=False)
    op.create_index(
        "ix_import_log_file_hash", "import_log", ["file_hash"], unique=False
    )
    op.create_index(
        "ix_import_log_doc", "import_log", ["doc_no", "doc_date"], unique=False
    )

    op.create_table(
        "import_rows",
        sa.Column("id", _bigint_pk(), primary_key=True, autoincrement=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("import_id", _bigint_pk(), nullable=False),
        sa.Column("source_row_no", sa.Integer(), nullable=False),
        sa.Column("raw_line", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("branch_code", sa.String(length=150), nullable=True),
        sa.Column("outgoing_no", sa.String(length=50), nullable=True),
        sa.Column("year_month", sa.CHAR(length=6), nullable=True),
        sa.Column("value_code", sa.String(length=10), nullable=True),
        sa.Column("evaluation_date", sa.Date(), nullable=True),
        sa.Column("matched_entity_type", sa.String(length=20), nullable=True),
        sa.Column("matched_entity_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_id"], ["import_log.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_rows_import", "import_rows", ["import_id", "status"], unique=False
    )
    op.create_index(
        "ix_import_rows_entity",
        "import_rows",
        ["matched_entity_type", "matched_entity_id"],
        unique=False,
    )
    op.create_index(
        "uix_import_rows_no",
        "import_rows",
        ["import_id", "source_row_no"],
        unique=True,
    )

    op.execute(
        """
        CREATE VIEW import_matches AS
        SELECT r.id, r.year, r.import_id, r.source_row_no,
               l.doc_no, l.doc_date,
               r.branch_code, r.outgoing_no, r.year_month,
               r.value_code, r.evaluation_date,
               r.matched_entity_type, r.matched_entity_id, r.created_at
        FROM import_rows r
        JOIN import_log l ON l.id = r.import_id
        WHERE r.status = 'matched'
        """
    )


def downgrade() -> None:
    """Удаляет представление и таблицы импорта."""
    op.execute("DROP VIEW IF EXISTS import_matches")
    op.drop_index("uix_import_rows_no", table_name="import_rows")
    op.drop_index("ix_import_rows_entity", table_name="import_rows")
    op.drop_index("ix_import_rows_import", table_name="import_rows")
    op.drop_table("import_rows")
    op.drop_index("ix_import_log_doc", table_name="import_log")
    op.drop_index("ix_import_log_file_hash", table_name="import_log")
    op.drop_index("ix_import_log_year", table_name="import_log")
    op.drop_table("import_log")
