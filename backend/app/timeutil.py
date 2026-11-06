from datetime import datetime, timezone


def utcnow() -> datetime:
    """Current time as naive UTC, the form stored in the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
