"""Репозиторий таблиц аудита импорта (Core SQLAlchemy)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import (
    CHAR,
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    inspect,
    insert,
    select,
    text,
    update,
)

from internal_correspondence.text_import.errors import RepositoryError
from internal_correspondence.text_import.models import DuplicateInfo

metadata = MetaData()

_ID_TYPE = BigInteger().with_variant(Integer, "sqlite")

import_log = Table(
    "import_log",
    metadata,
    Column("id", _ID_TYPE, primary_key=True, autoincrement=True),
    Column("year", Integer, nullable=False),
    Column("doc_no", String(50), nullable=False),
    Column("doc_date", Date, nullable=False),
    Column("file_name", Text, nullable=False),
    Column("file_hash", CHAR(64), nullable=False),
    Column("stored_path", Text, nullable=True),
    Column("scheme_name", String(100), nullable=False),
    Column("matched_rule", String(100), nullable=True),
    Column("imported_rows", Integer, nullable=False, server_default="0"),
    Column("matched_rows", Integer, nullable=False, server_default="0"),
    Column("unmatched_rows", Integer, nullable=False, server_default="0"),
    Column("skipped_rows", Integer, nullable=False, server_default="0"),
    Column("rejected_rows", Integer, nullable=False, server_default="0"),
    Column("error_rows", Integer, nullable=False, server_default="0"),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime, nullable=True),
    Column("status", String(20), nullable=False),
)

Index("ix_import_log_year", import_log.c.year)
Index("ix_import_log_file_hash", import_log.c.file_hash)
Index("ix_import_log_doc", import_log.c.doc_no, import_log.c.doc_date)

import_rows = Table(
    "import_rows",
    metadata,
    Column("id", _ID_TYPE, primary_key=True, autoincrement=True),
    Column("year", Integer, nullable=False),
    Column("import_id", _ID_TYPE, ForeignKey("import_log.id", ondelete="CASCADE"), nullable=False),
    Column("source_row_no", Integer, nullable=False),
    Column("raw_line", Text, nullable=False),
    Column("data", JSON, nullable=False),
    Column("status", String(20), nullable=False),
    Column("error", Text, nullable=True),
    Column("branch_code", String(150), nullable=True),
    Column("outgoing_no", String(50), nullable=True),
    Column("year_month", CHAR(6), nullable=True),
    Column("value_code", String(10), nullable=True),
    Column("evaluation_date", Date, nullable=True),
    Column("matched_entity_type", String(20), nullable=True),
    Column("matched_entity_id", Uuid(as_uuid=False), nullable=True),
    Column("created_at", DateTime, nullable=False),
)

Index("ix_import_rows_import", import_rows.c.import_id, import_rows.c.status)
Index(
    "ix_import_rows_entity",
    import_rows.c.matched_entity_type,
    import_rows.c.matched_entity_id,
)
Index("uix_import_rows_no", import_rows.c.import_id, import_rows.c.source_row_no, unique=True)


_CREATE_VIEW = """
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


def ensure_schema(engine: Any) -> None:
    """Создаёт таблицы и представление, если их ещё нет (тесты, пустая БД)."""
    metadata.create_all(engine, checkfirst=True)
    inspector = inspect(engine)
    if "import_matches" in inspector.get_view_names():
        return
    with engine.begin() as connection:
        connection.execute(text(_CREATE_VIEW))


def create_log(session: Any, values: Dict[str, Any]) -> int:
    values = dict(values)
    values.setdefault("started_at", datetime.now())
    values.setdefault("status", "running")
    try:
        result = session.execute(insert(import_log).values(**values))
        session.commit()
        return int(result.inserted_primary_key[0])
    except Exception as exc:  # pragma: no cover - защита от неожиданных драйверов
        session.rollback()
        raise RepositoryError("log_create_failed", str(exc)) from exc


def update_log(session: Any, log_id: int, commit: bool = True, **values: Any) -> None:
    if not values:
        return
    session.execute(update(import_log).where(import_log.c.id == log_id).values(**values))
    if commit:
        session.commit()


def find_duplicate(session: Any, file_hash: str) -> Optional[DuplicateInfo]:
    statement = (
        select(
            import_log.c.id,
            import_log.c.year,
            import_log.c.file_name,
            import_log.c.stored_path,
            import_log.c.started_at,
            import_log.c.status,
        )
        .where(import_log.c.file_hash == file_hash)
        .order_by(import_log.c.started_at.desc())
        .limit(1)
    )
    row = session.execute(statement).first()
    if row is None:
        return None
    return DuplicateInfo(
        import_id=int(row[0]),
        year=int(row[1]),
        file_name=str(row[2]),
        stored_path=row[3],
        started_at=row[4],
        status=str(row[5]),
    )


def insert_rows(session: Any, rows: Iterable[Dict[str, Any]]) -> int:
    payload = list(rows)
    if not payload:
        return 0
    session.execute(insert(import_rows), payload)
    return len(payload)


def matches_view(session: Any, import_id: int) -> List[Any]:
    return list(
        session.execute(
            text("SELECT * FROM import_matches WHERE import_id = :import_id ORDER BY source_row_no"),
            {"import_id": import_id},
        ).mappings()
    )
