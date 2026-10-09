"""Лёгкие миграции SQLite без Alembic (добавление колонок)."""
import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.database import Base


def _column_names(conn: Connection, table: str) -> set[str]:
    insp = sa.inspect(conn)
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def run_sqlite_migrations(conn: Connection) -> None:
    employers = _column_names(conn, "employers")
    if employers and "contact_emails" not in employers:
        conn.execute(sa.text("ALTER TABLE employers ADD COLUMN contact_emails JSON DEFAULT '[]'"))

    interviews = _column_names(conn, "interviews")
    if interviews and "feedback_emails" not in interviews:
        conn.execute(sa.text("ALTER TABLE interviews ADD COLUMN feedback_emails JSON DEFAULT '[]'"))


def ensure_schema(conn: Connection) -> None:
    Base.metadata.create_all(bind=conn)
    run_sqlite_migrations(conn)
