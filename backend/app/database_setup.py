"""Bring the database to the current schema on start-up, with the Alembic migrations in app/migrations."""

from importlib.resources import files

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

HEAD = "0004"


def run(engine: Engine, action, *args) -> None:
    """Run an Alembic command. SQLite: with link checking off, so migrations can rebuild tables that others point to
    (it can't be switched inside a transaction, so before it starts)."""
    config = Config()
    config.set_main_option("script_location", str(files("app") / "migrations"))
    sqlite = engine.dialect.name == "sqlite"
    with engine.connect() as connection:
        if sqlite:
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
        try:
            with connection.begin():
                config.attributes["connection"] = connection
                action(config, *args)
        finally:
            if sqlite:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()


def setup(engine: Engine) -> None:
    run(engine, command.upgrade, "head")
