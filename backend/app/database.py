import os

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/hub.db")


def ensure_sqlite_folder(url: str) -> None:
    """SQLite creates the database file but not its folder (e.g. backend/data in a fresh clone)."""
    database = make_url(url).database if url.startswith("sqlite") else None
    if database and database != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(database)), exist_ok=True)


def enable_foreign_keys(engine: Engine) -> None:
    """SQLite ignores foreign keys (and ON DELETE SET NULL / CASCADE) unless asked on every connection."""

    @event.listens_for(engine, "connect")
    def _enforce(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


ensure_sqlite_folder(SQLALCHEMY_DATABASE_URL)
# check_same_thread is needed for SQLite with FastAPI's thread pool
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
enable_foreign_keys(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Named constraints, so later batch migrations on SQLite can refer to them by name
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
