import logging

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

logger = logging.getLogger(__name__)

_is_sqlite = "sqlite" in settings.database_url

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:
    # APScheduler's BackgroundScheduler runs jobs in a thread pool, so two
    # agents can genuinely be mid-write at the same moment (e.g. a manual
    # /api/refresh sweep overlapping a regularly-scheduled interval job) —
    # SQLite allows only one writer at a time and, with the default
    # busy_timeout of 0, the second writer fails immediately with
    # "database is locked" instead of just waiting its turn. WAL mode lets
    # readers stop blocking writers (and vice versa), and a real
    # busy_timeout makes a genuine writer-vs-writer collision retry for a
    # few seconds instead of raising outright — same fix either process
    # (agents writing, or a request reading concurrently) needed.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def _add_missing_columns() -> None:
    """`Base.metadata.create_all()` only creates missing *tables* — it never
    alters an existing table's columns. There's no Alembic in this project
    (see agents/README.md-adjacent notes), so for the narrow case of adding
    a nullable/defaulted column to an existing table, just ALTER it directly
    if it's missing. Anything more involved than "add a column" should get
    a real migration tool instead of extending this."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # brand-new table — create_all() already handled it
        existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            col_type = column.type.compile(engine.dialect)
            default_clause = ""
            if column.default is not None and getattr(column.default, "is_scalar", False):
                default_clause = f" DEFAULT {column.default.arg!r}"
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}{default_clause}"
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("Migrated: added column %s.%s", table.name, column.name)


def init_db() -> None:
    from app import models  # noqa: F401 - ensure models are registered

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
