"""The hub's settings, from the environment (README_DOCKER.md lists them). Read once and checked at startup
(`main.lifespan`); `reload()` reads them again (tests)."""

import functools
import logging
import os
from collections.abc import Mapping
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

logger = logging.getLogger(__name__)

Language = Literal["de", "en"]
# https, or plain http only for a development server on this machine (as an app's address on a tile)
_PUBLIC_URL = re.compile(r"^(https://[^\s/]+|http://(localhost|127\.0\.0\.1)(:\d+)?)(/\S*)?$")


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_url: str = "sqlite:///./data/hub.db"
    # The signing key lives here (and the database, by default)
    data_dir: Path = Path("./data")
    # The language of people who haven't picked one
    default_language: Language = "de"
    # The first parent's PIN on an empty database; random when unset
    initial_admin_pin: str = ""
    # The login cookie's domain at home (e.g. local.<domain>); None: the hub's own address only
    cookie_domain: str | None = None
    # Off only for plain http in development and tests (COOKIE_INSECURE=1)
    cookie_secure: bool = True
    # Cloudflare Access outside: the team's domain and the Access applications' audience tags
    cf_team_domain: str = ""
    cf_audience: tuple[str, ...] = ()
    # Mails through Resend (PIN reset, address confirmation)
    resend_api_key: str = ""
    mail_from: str = ""
    # The hub's address at home, for the links in mails; without a trailing "/"
    hub_public_url: str = ""
    # Browser tests only: mails go to this file instead of Resend
    mail_outbox: str = ""

    @field_validator("hub_public_url")
    @classmethod
    def _an_address(cls, value: str) -> str:
        if value and not _PUBLIC_URL.match(value):
            raise ValueError("HUB_PUBLIC_URL must start with https:// (e.g. https://home.local.<domain>)")
        return value.rstrip("/")

    @property
    def mail_configured(self) -> bool:
        return bool(self.resend_api_key and self.mail_from and self.hub_public_url)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "Settings":
        def env(name: str) -> str:
            return (environ.get(name) or "").strip()

        fields: dict[str, object] = {
            "default_language": "en" if env("DEFAULT_LANGUAGE").lower() == "en" else "de",
            "cookie_domain": env("COOKIE_DOMAIN") or None,
            "cookie_secure": env("COOKIE_INSECURE") != "1",
            "cf_audience": tuple(a.strip() for a in env("CF_AUDIENCE").split(",") if a.strip()),
        }
        for name in (
            "database_url",
            "data_dir",
            "initial_admin_pin",
            "cf_team_domain",
            "resend_api_key",
            "mail_from",
            "hub_public_url",
            "mail_outbox",
        ):
            if env(name.upper()):
                fields[name] = env(name.upper())
        return cls.model_validate(fields)


@functools.cache
def settings() -> Settings:
    return Settings.from_env()


def reload() -> Settings:
    settings.cache_clear()
    return settings()


def log_summary(found: Settings) -> None:
    """What is switched on, at startup; never a secret."""
    if found.cf_team_domain and not found.cf_audience:
        logger.warning("CF_TEAM_DOMAIN is set but CF_AUDIENCE isn't: nobody can log in from outside")
    mail = (found.resend_api_key, found.mail_from, found.hub_public_url)
    if any(mail) and not all(mail):
        logger.warning("Mails need RESEND_API_KEY, MAIL_FROM and HUB_PUBLIC_URL; one is missing, so mails are off")
    logger.info(
        "Login from outside: %s. Mails: %s.",
        "on" if found.cf_team_domain and found.cf_audience else "off",
        "on" if found.mail_configured else "off",
    )


def data_dir() -> Path:
    return settings().data_dir


def default_language() -> Language:
    return settings().default_language
