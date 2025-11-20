from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_sqlite_schema() -> None:
    """Apply lightweight schema upgrades when running on SQLite without Alembic."""

    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)

    def _column_exists(table: str, column: str) -> bool:
        return any(col["name"] == column for col in inspector.get_columns(table))

    statements: list[tuple[str, str]] = []

    if not _column_exists("evaluations", "rubric_id"):
        statements.append(("evaluations", "ALTER TABLE evaluations ADD COLUMN rubric_id INTEGER"))
    if not _column_exists("criterion_scores", "rubric_item_id"):
        statements.append(("criterion_scores", "ALTER TABLE criterion_scores ADD COLUMN rubric_item_id INTEGER"))
    if not _column_exists("criterion_scores", "evidence"):
        statements.append(("criterion_scores", "ALTER TABLE criterion_scores ADD COLUMN evidence TEXT"))
    if not _column_exists("criterion_scores", "justification"):
        statements.append(("criterion_scores", "ALTER TABLE criterion_scores ADD COLUMN justification TEXT"))

    if not statements:
        return

    with engine.begin() as connection:
        for table, ddl in statements:
            connection.execute(text(ddl))
