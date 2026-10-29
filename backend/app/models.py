import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String

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

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    # name.casefold(): names are unique and logins match regardless of case ("lena" is "Lena")
    name_key = Column(String(50), unique=True, nullable=False)
    # How Cloudflare Access knows the person outside; stored casefolded, unique
    email = Column(String(254), unique=True)
    pin_hash = Column(String, nullable=False)
    role = Column(Enum(Role), default=Role.CHILD, nullable=False)
    # An inactive person can't log in, and the apps hear their logins are no longer valid
    active = Column(Boolean, default=True, nullable=False)
    # The person's colour on the login screen and in the apps, e.g. "#f59e0b"
    color = Column(String(7))
    # None: the default language (DEFAULT_LANGUAGE)
    language = Column(String(2))
    failed_logins = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime)
    # Locks in a row: each one doubles the next (see auth.lock_duration); a correct login or a new PIN resets it
    lockouts = Column(Integer, default=0, nullable=False)
    # Part of every login token; raising it ends all of the person's logins (new PIN, log out everywhere)
    token_version = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class Tile(Base):
    """An app on the start page: its address at home, and outside (None: home only)."""

    __tablename__ = "tiles"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    # An emoji, e.g. "💰"
    icon = Column(String(16), nullable=False, default="")
    local_url = Column(String(300), nullable=False)
    remote_url = Column(String(300))
    position = Column(Integer, nullable=False, default=0)
