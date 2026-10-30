from datetime import date, datetime, timezone

from . import config


def utcnow() -> datetime:
    """Current time as naive UTC, the form stored in the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def today() -> date:
    """Today at home (TZ), which decides what counts as eaten; tests replace it."""
    return datetime.now(config.tz()).date()
