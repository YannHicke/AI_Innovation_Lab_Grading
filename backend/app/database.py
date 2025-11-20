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


def ensure_schema() -> None:
    """Apply lightweight schema upgrades for SQLite and Postgres deployments."""

    if settings.database_url.startswith("sqlite"):
        _ensure_sqlite_schema()
    else:
        _ensure_postgres_schema()


def _ensure_sqlite_schema() -> None:
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


def _ensure_postgres_schema() -> None:
    statements = [
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS assignment_id INTEGER REFERENCES assignments(id)",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS grader_id INTEGER REFERENCES users(id)",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS rubric_id INTEGER REFERENCES rubrics(id)",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS student_identifier VARCHAR(255)",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS share_with_student BOOLEAN DEFAULT FALSE",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS rubric_summary TEXT",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS feedback_summary TEXT",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS total_score DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS max_total_score DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS performance_band VARCHAR(50)",
        "ALTER TABLE evaluations ADD COLUMN IF NOT EXISTS rubric_title VARCHAR(255)",
        "ALTER TABLE criterion_scores ADD COLUMN IF NOT EXISTS rubric_item_id INTEGER REFERENCES rubric_items(id)",
        "ALTER TABLE criterion_scores ADD COLUMN IF NOT EXISTS evidence TEXT",
        "ALTER TABLE criterion_scores ADD COLUMN IF NOT EXISTS justification TEXT",
    ]

    with engine.begin() as connection:
        for ddl in statements:
            connection.execute(text(ddl))
