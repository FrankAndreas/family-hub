import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Response
from sqlalchemy.exc import SQLAlchemyError

from . import apps_api, auth, config, database, database_setup, keys, login_api, people_api, session_api, tiles_api
from .seed import seed_admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def start() -> None:
    """Everything before the first request: settings checked, the database at the current schema, the signing key and
    a first parent on a fresh database. Importing the app does none of it (tests set up their own database)."""
    settings = config.reload()
    config.log_summary(settings)
    database.ensure_sqlite_folder(settings.database_url)
    # Create or upgrade the schema (Alembic migrations in app/migrations)
    database_setup.setup(database.engine)
    # The signing key, made now if new (not by two first requests at once)
    keys.signing_key()
    with database.SessionLocal() as db:
        initial_pin = seed_admin(db)
    if initial_pin:
        logger.warning("Created parent 'Admin' with INITIAL PIN %s. Log in and change it in the settings.", initial_pin)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start()
    yield


app = FastAPI(
    title="family-hub API", version="0.1.0", lifespan=lifespan, dependencies=[Depends(auth.require_app_header)]
)
app.include_router(login_api.router, prefix="/api")
app.include_router(people_api.router, prefix="/api")
app.include_router(session_api.router)
app.include_router(apps_api.router)
app.include_router(tiles_api.router, prefix="/api")


@app.get("/health")
def health(response: Response):
    """For Docker's health check and the update script: the backend answers and can read its database (operations
    review 2026-11-07)."""
    try:
        with database.engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1 FROM people LIMIT 1")
    except SQLAlchemyError:
        logger.exception("Health check: the database can't be read")
        response.status_code = 503
        return {"status": "database unreadable"}
    return {"status": "ok"}
