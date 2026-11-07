"""The health check Docker and the update script rely on."""

from app import database, models


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_health_fails_without_a_readable_database(client):
    # Operations review 2026-11-07: "ok" only when the backend can read its database
    models.Base.metadata.drop_all(bind=database.engine)
    response = client.get("/health")
    assert response.status_code == 503 and response.json() == {"status": "database unreadable"}
