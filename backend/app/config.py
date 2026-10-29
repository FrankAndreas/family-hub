import os
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

Language = Literal["de", "en"]


def env(name: str, default: str = "") -> str:
    """An environment variable, stripped; read on every call so tests can change it."""
    return (os.getenv(name) or default).strip()


def data_dir() -> Path:
    return Path(env("DATA_DIR", "./data"))


def default_language() -> Language:
    """The language of people who haven't picked one; anything but "en" means German."""
    return "en" if env("DEFAULT_LANGUAGE", "de").lower() == "en" else "de"


def tz() -> ZoneInfo:
    return ZoneInfo(env("TZ", "Europe/Zurich"))
