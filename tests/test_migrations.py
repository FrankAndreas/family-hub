from sqlalchemy import create_engine, inspect

from app import database_setup, models


def _migrated(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/m.db")
    database_setup.setup(engine)
    return engine


def test_fresh_database_upgrades_to_head(tmp_path):
    engine = _migrated(tmp_path)
    assert {"people", "tiles", "alembic_version"} <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == database_setup.HEAD


def test_setup_is_idempotent(tmp_path):
    engine = _migrated(tmp_path)
    database_setup.setup(engine)


def test_migration_matches_models(tmp_path):
    """The migrations create exactly the columns the models declare (catches a forgotten migration)."""
    inspector = inspect(_migrated(tmp_path))
    for table in models.Base.metadata.sorted_tables:
        assert {c["name"] for c in inspector.get_columns(table.name)} == set(table.columns.keys()), table.name


def test_constraints_are_named(tmp_path):
    """Named constraints, so later batch migrations on SQLite can drop or change them."""
    inspector = inspect(_migrated(tmp_path))
    for table in models.Base.metadata.sorted_tables:
        for unique in inspector.get_unique_constraints(table.name):
            assert unique["name"], table.name
