"""Bring the database to the current schema on start-up, with the Alembic migrations in app/migrations."""

from importlib.resources import files

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

HEAD = "0008"


def _transactional(engine: Engine) -> Engine:
    """For SQLite, a copy of the engine whose transactions cover DDL too. Python's sqlite3 runs CREATE and ALTER outside
    any transaction, so a migration failing halfway would leave half a schema behind, and the next start would stop at
    "table already exists" (operations review 2026-11-07). Here the driver opens no transaction itself and every
    transaction starts with an explicit BEGIN, as SQLAlchemy's documentation suggests."""
    if engine.dialect.name != "sqlite":
        return engine
    migrating = create_engine(engine.url, connect_args={"check_same_thread": False})

    @event.listens_for(migrating, "connect")
    def _no_implicit_transactions(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(migrating, "begin")
    def _begin(connection):
        connection.exec_driver_sql("BEGIN")

    return migrating


def run(engine: Engine, action, *args) -> None:
    """Run an Alembic command in one transaction: all of it or nothing. SQLite: with link checking off, so migrations
    can rebuild tables that others point to (SQLite ignores the switch inside a transaction, so it is set before)."""
    config = Config()
    config.set_main_option("script_location", str(files("app") / "migrations"))
    sqlite = engine.dialect.name == "sqlite"
    migrating = _transactional(engine)
    try:
        with migrating.connect() as connection:
            driver = connection.connection.driver_connection if sqlite else None
            if driver is not None:
                driver.execute("PRAGMA foreign_keys=OFF")
            try:
                with connection.begin():
                    config.attributes["connection"] = connection
                    action(config, *args)
            finally:
                if driver is not None:
                    driver.execute("PRAGMA foreign_keys=ON")
    finally:
        if migrating is not engine:
            migrating.dispose()


def setup(engine: Engine) -> None:
    run(engine, command.upgrade, "head")
