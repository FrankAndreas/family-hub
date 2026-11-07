"""Startup: settings read and checked, the database brought up to date, a first parent; none of it on import."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect

from app import config, database, main, models


def test_settings_from_the_environment():
    found = config.Settings.from_env(
        {
            "DEFAULT_LANGUAGE": " EN ",
            "COOKIE_INSECURE": "1",
            "COOKIE_DOMAIN": "",
            "CF_AUDIENCE": "aud-1, ,aud-2",
            "HUB_PUBLIC_URL": "https://home.local.example.ch/",
        }
    )
    assert found.default_language == "en"
    assert found.cookie_secure is False
    assert found.cookie_domain is None
    assert found.cf_audience == ("aud-1", "aud-2")
    assert found.hub_public_url == "https://home.local.example.ch"
    assert not found.mail_configured
    # Unknown languages stay German, as before
    assert config.Settings.from_env({"DEFAULT_LANGUAGE": "fr"}).default_language == "de"


@pytest.mark.parametrize(
    "address", ["home.local.example.ch", "http://home.local.example.ch", "ftp://home.local.example.ch"]
)
def test_a_wrong_address_stops_the_start(address):
    # The links in mails reset PINs: never over plain http, except a development server on this machine
    with pytest.raises(ValidationError, match="HUB_PUBLIC_URL"):
        config.Settings.from_env({"HUB_PUBLIC_URL": address})
    assert config.Settings.from_env({"HUB_PUBLIC_URL": "http://localhost:3110"}).hub_public_url


def test_half_a_mail_setup_is_reported(caplog):
    config.log_summary(config.Settings.from_env({"RESEND_API_KEY": "secret-key"}))
    assert "mails are off" in caplog.text
    assert "secret-key" not in caplog.text


def test_start_sets_up_a_fresh_database(db):
    models.Base.metadata.drop_all(bind=database.engine)
    with TestClient(main.app):
        # The app's lifespan ran start(): schema migrated, first parent seeded
        assert "alembic_version" in inspect(database.engine).get_table_names()
        assert models.Person.by_name(db, "Admin") is not None
