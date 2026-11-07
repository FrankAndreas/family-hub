from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, AliasChoices, BaseModel, ConfigDict, Field, field_serializer, field_validator

from . import models
from .config import Language
from .models import Role

PIN = r"^\d{4}$"
COLOR = r"^#[0-9a-fA-F]{6}$"
# Enough to catch typos; Cloudflare Access is what checks the address really works
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# Stored casefolded: Cloudflare's "Lena@Example.ch" is the same person as "lena@example.ch"
Email = Annotated[str, Field(max_length=254, pattern=EMAIL), AfterValidator(str.casefold)]


class LoginIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    pin: str = Field(pattern=PIN)


class PersonPublic(BaseModel):
    name: str
    color: str | None


class PersonOut(BaseModel):
    id: int
    name: str
    email: str | None
    # Entered, waiting until the link mailed to it is opened
    email_pending: str | None = None
    role: Role
    active: bool
    color: str | None
    language: str
    # Whether the person picked the language themselves (else the default)
    language_chosen: bool
    # Managing people, PINs and apps happens at home only: the settings page shows it outside
    at_home: bool = True
    # Whether the parent asking may change this person: themselves and the children, never another parent
    can_edit: bool = True

    @classmethod
    def of(cls, person: models.Person, at_home: bool = True, can_edit: bool = True) -> "PersonOut":
        return cls(
            at_home=at_home,
            can_edit=can_edit,
            id=person.id,
            name=person.name,
            email=person.email,
            email_pending=person.email_pending,
            role=person.role,
            active=person.active,
            color=person.color,
            language=person.language_or_default,
            language_chosen=person.language is not None,
        )


# What the apps get (README "For apps"): the same person for /api/session and /api/apps/<key>/people


class AppPerson(BaseModel):
    """A person as an app sees it. `email` only for an app whose tile allows it: left out otherwise, not null."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: Role
    color: str | None
    # The person's choice or the default; read from a Person, or from this model's own output
    language: str = Field(validation_alias=AliasChoices("language_or_default", "language"))
    email: str | None = None


class SessionOut(BaseModel):
    """Whether a login still counts. `access` (with ?app=<key>) is left out without a key; `renew` is there with a
    valid login: true in a hub login's last week (send the browser through the hub once, which renews it)."""

    valid: bool
    person: AppPerson | None
    access: bool | None = None
    renew: bool | None = None


class TileLink(BaseModel):
    """A tile on the start page: the address for where one is (home or outside)."""

    id: int
    name: str
    icon: str
    url: str
    home_only: bool


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    pin: str = Field(pattern=PIN)
    role: Role = Role.CHILD
    email: Email | None = None
    color: str | None = Field(default=None, pattern=COLOR)
    language: Language | None = None


class PersonPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    # The parent's own PIN, needed to change their own e-mail address (the way back in when the PIN is forgotten)
    current_pin: str | None = Field(default=None, pattern=PIN)
    role: Role | None = None
    active: bool | None = None
    email: Email | None = None
    color: str | None = Field(default=None, pattern=COLOR)
    language: Language | None = None


class PinIn(BaseModel):
    pin: str = Field(pattern=PIN)


class EmailConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=100)


class PinResetIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class PinResetConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=100)
    pin: str = Field(pattern=PIN)


class OwnPinIn(BaseModel):
    old_pin: str = Field(pattern=PIN)
    pin: str = Field(pattern=PIN)


class MePatch(BaseModel):
    language: Language | None = None
    color: str | None = Field(default=None, pattern=COLOR)


# https only; http only for a development server on this machine
URL = r"^(https://[^\s/]+(/\S*)?|http://(localhost|127\.0\.0\.1)(:\d+)?(/\S*)?)$"
# An app's key: lowercase letters, digits and dashes, starting with a letter, 2 to 20 long
APP_KEY = r"^[a-z][a-z0-9-]{1,19}$"
# Cloudflare Access's Application Audience (AUD) tag
CF_AUDIENCE = r"^[0-9a-f]{64}$"


class TileIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    icon: str = Field(default="", max_length=16)
    local_url: str = Field(max_length=300, pattern=URL)
    # None: the app is reachable at home only
    remote_url: str | None = Field(default=None, max_length=300, pattern=URL)
    # Only for apps that use the family login; lowercase, e.g. "budget"
    app_key: str | None = Field(default=None, pattern=APP_KEY)
    # Ids of the people who may use the app (with an app key)
    people: list[int] = []
    # The app may see its people's confirmed e-mail addresses
    share_email: bool = False
    # The AUD tag of the app's Cloudflare Access application (None: any of CF_AUDIENCE)
    cf_audience: str | None = Field(default=None, pattern=CF_AUDIENCE)


class TilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    icon: str | None = Field(default=None, max_length=16)
    local_url: str | None = Field(default=None, max_length=300, pattern=URL)
    remote_url: str | None = Field(default=None, max_length=300, pattern=URL)
    app_key: str | None = Field(default=None, pattern=APP_KEY)
    people: list[int] | None = None
    share_email: bool | None = None
    cf_audience: str | None = Field(default=None, pattern=CF_AUDIENCE)


class TileUsage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    person_id: int
    first_used_at: datetime
    last_used_at: datetime

    @field_serializer("first_used_at", "last_used_at")
    def as_utc(self, value: datetime) -> str:
        # Stored as naive UTC
        return value.replace(microsecond=0).isoformat() + "Z"


class TileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    icon: str
    local_url: str
    remote_url: str | None
    position: int
    app_key: str | None
    people: list[int]
    share_email: bool
    cf_audience: str | None
    # Who used the app under its current key, and when
    usage: list[TileUsage]
    # The other parents who used it: only they can untick themselves, and meanwhile the app keeps its key and can't
    # be deleted (tiles_api.locked_people). For the parent asking
    locked_people: list[int] = []

    @field_validator("people", mode="before")
    @classmethod
    def person_ids(cls, value):
        return sorted(p if isinstance(p, int) else p.id for p in value)
