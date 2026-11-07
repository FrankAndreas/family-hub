import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Table, UniqueConstraint, false
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from . import config
from .database import Base
from .timeutil import utcnow


class Role(str, enum.Enum):
    PARENT = "PARENT"
    CHILD = "CHILD"


def name_key(name: str) -> str:
    """What makes two names the same person's: case and surrounding spaces don't count."""
    return name.strip().casefold()


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
    # An address someone entered, waiting until a link mailed to it is opened (security review 2026-10-30): only then
    # it becomes `email`, the Cloudflare login and the way back in with a forgotten PIN
    email_pending: Mapped[str | None] = mapped_column(String(254))
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
    # Locks in a row: each one doubles the next (see pins.lock_duration); a correct login or a new PIN resets it
    lockouts: Mapped[int] = mapped_column(default=0)
    # Part of every login token; raising it ends all of the person's logins (new PIN, log out everywhere)
    token_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def language_or_default(self) -> str:
        """The person's language, or DEFAULT_LANGUAGE if they haven't picked one."""
        return self.language or config.default_language()

    @staticmethod
    def by_name(db: Session, name: str) -> "Person | None":
        return db.query(Person).filter(Person.name_key == name_key(name)).first()


# Who may use which app (spec 2026-10-30, part A): only tiles with an app key take part
tile_access = Table(
    "tile_access",
    Base.metadata,
    Column("tile_id", ForeignKey("tiles.id", ondelete="CASCADE"), primary_key=True),
    Column("person_id", ForeignKey("people.id", ondelete="CASCADE"), primary_key=True),
    # When the person first and last used the app (its key asked for with their login; None: never). Only a parent who
    # used the app is protected against another parent: unticking someone who never did takes nothing from them. Last
    # use is kept to the hour, so an app's every page doesn't write. Unticking or a new key forgets it
    Column("first_used_at", DateTime, nullable=True),
    Column("last_used_at", DateTime, nullable=True),
)


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
    # Set for an app that uses the family login, e.g. "budget": it asks the hub for access and its people by this key.
    # None: a plain link, shown to everyone
    app_key: Mapped[str | None] = mapped_column(String(20), unique=True)
    # The app may see its people's confirmed e-mail addresses (e.g. the job tracking app: reminders, its own mails);
    # other apps get no addresses (2026-10-30)
    share_email: Mapped[bool] = mapped_column(default=False, server_default=false())
    # The AUD tag of the app's Cloudflare Access application (hub#12): a Cloudflare login counts for this app only when
    # made for that application. None: any of CF_AUDIENCE, as for the hub itself
    cf_audience: Mapped[str | None] = mapped_column(String(64))
    people: Mapped[list[Person]] = relationship(secondary=tile_access, order_by=Person.id)
    # The same rows with when each person used the app; read only, `people` changes them
    access: Mapped[list["TileAccess"]] = relationship(viewonly=True, order_by="TileAccess.person_id")

    @property
    def usage(self) -> list["TileAccess"]:
        return [a for a in self.access if a.first_used_at is not None]

    @staticmethod
    def by_key(db: Session, key: str) -> "Tile | None":
        return db.query(Tile).filter(Tile.app_key == key).first()


class TileAccess(Base):
    """A row of tile_access: who may use an app, and when they used it."""

    __table__ = tile_access

    tile_id: Mapped[int]
    person_id: Mapped[int]
    first_used_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]


class KnownDevice(Base):
    """A browser the person logged in with before (security review 2026-10-30): wrong PINs from elsewhere don't lock it,
    so nobody at home can lock a parent out. Its own wrong PINs count against it alone, and a few make it unknown."""

    __tablename__ = "known_devices"
    __table_args__ = (UniqueConstraint("person_id", "secret_hash", name="uq_known_devices_person_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    # SHA-256 of the browser's hub_device cookie; a browser keeps one cookie for everyone who logs in with it
    secret_hash: Mapped[str] = mapped_column(String(64))
    failed_logins: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class EndedLogin(Base):
    """A login ended with "Log out" (spec 2026-10-30 hub hardening): its token's id, kept until the token expires."""

    __tablename__ = "ended_logins"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    expires_at: Mapped[datetime]


class PinReset(Base):
    """A link to set a forgotten PIN, sent by e-mail or printed on the NAS: only its SHA-256 is kept; it works once."""

    __tablename__ = "pin_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class EmailConfirm(Base):
    """A link that confirms a person's new e-mail address: only its SHA-256 is kept; it works once."""

    __tablename__ = "email_confirms"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(254))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
