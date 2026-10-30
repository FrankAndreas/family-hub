import enum
from datetime import datetime

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .timeutil import utcnow


class Role(str, enum.Enum):
    PARENT = "PARENT"
    CHILD = "CHILD"


class Person(Base):
    """A family member: the one list every family app takes its people from (spec 2026-10-29)."""

    __tablename__ = "people"
    # Never reuse ids: login tokens and the apps' own rows name the person by id
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    # name.casefold(): names are unique and logins match regardless of case ("lena" is "Lena")
    name_key: Mapped[str] = mapped_column(String(50), unique=True)
    # How Cloudflare Access knows the person outside; stored casefolded, unique
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    pin_hash: Mapped[str] = mapped_column(String)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.CHILD)
    # An inactive person can't log in, and the apps hear their logins are no longer valid
    active: Mapped[bool] = mapped_column(default=True)
    # The person's colour on the login screen and in the apps, e.g. "#f59e0b"
    color: Mapped[str | None] = mapped_column(String(7))
    # None: the default language (DEFAULT_LANGUAGE)
    language: Mapped[str | None] = mapped_column(String(2))
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    # Locks in a row: each one doubles the next (see auth.lock_duration); a correct login or a new PIN resets it
    lockouts: Mapped[int] = mapped_column(default=0)
    # Part of every login token; raising it ends all of the person's logins (new PIN, log out everywhere)
    token_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Tile(Base):
    """An app on the start page: its address at home, and outside (None: home only)."""

    __tablename__ = "tiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    # An emoji, e.g. "💰"
    icon: Mapped[str] = mapped_column(String(16), default="")
    local_url: Mapped[str] = mapped_column(String(300))
    remote_url: Mapped[str | None] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(default=0)
