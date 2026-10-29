import logging

from fastapi import FastAPI

from . import database, database_setup
from .seed import seed_admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Create or upgrade the schema (Alembic migrations in app/migrations)
database_setup.setup(database.engine)

# A fresh database gets a first parent to log in with
with database.SessionLocal() as _db:
    _initial_pin = seed_admin(_db)
if _initial_pin:
    logger.warning("Created parent 'Admin' with INITIAL PIN %s. Log in and change it in the settings.", _initial_pin)

app = FastAPI(title="family-hub API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}
