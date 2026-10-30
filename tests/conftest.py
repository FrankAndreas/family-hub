import os
import sys
import tempfile
from pathlib import Path

# Point the app at a throwaway database and data folder before it is imported, so tests never touch ./data
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DATA_DIR"] = _tmp
os.environ["INITIAL_ADMIN_PIN"] = "1234"
os.environ["DEFAULT_LANGUAGE"] = "de"
# The test client talks plain http: a Secure cookie would never come back
os.environ["COOKIE_INSECURE"] = "1"
# Cloudflare Access starts switched off; tests that need it set the variables with monkeypatch
for _name in ("COOKIE_DOMAIN", "CF_TEAM_DOMAIN", "CF_AUDIENCE"):
    os.environ.pop(_name, None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import functools  # noqa: E402

import bcrypt  # noqa: E402
import pytest  # noqa: E402

# Cheap PIN hashes: bcrypt's default cost makes every login in a test take ~0.25 s
bcrypt.gensalt = functools.partial(bcrypt.gensalt, rounds=4)
from fastapi.testclient import TestClient  # noqa: E402

from app import database, models  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_admin  # noqa: E402
from helpers import APP_HEADER  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts like a fresh install: parent "Admin" with PIN 1234."""
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    with database.SessionLocal() as session:
        seed_admin(session)
    yield


@pytest.fixture
def db():
    with database.SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    return TestClient(app, headers=APP_HEADER)
