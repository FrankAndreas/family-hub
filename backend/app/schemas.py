from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models import Role


class LoginIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    pin: str = Field(pattern=r"^\d{4}$")


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


PIN = r"^\d{4}$"
COLOR = r"^#[0-9a-fA-F]{6}$"
# Enough to catch typos; Cloudflare Access is what checks the address really works
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    pin: str = Field(pattern=PIN)
    role: Role = Role.CHILD
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL)
    color: str | None = Field(default=None, pattern=COLOR)
    language: Literal["de", "en"] | None = None


class PersonPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    # The parent's own PIN, needed to change their own e-mail address (the way back in when the PIN is forgotten)
    current_pin: str | None = Field(default=None, pattern=r"^\d{4}$")
    role: Role | None = None
    active: bool | None = None
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL)
    color: str | None = Field(default=None, pattern=COLOR)
    language: Literal["de", "en"] | None = None


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
    language: Literal["de", "en"] | None = None
    color: str | None = Field(default=None, pattern=COLOR)


# https only; http only for a development server on this machine
URL = r"^(https://[^\s/]+(/\S*)?|http://(localhost|127\.0\.0\.1)(:\d+)?(/\S*)?)$"
# An app's key: lowercase letters, digits and dashes, starting with a letter, 2 to 20 long
APP_KEY = r"^[a-z][a-z0-9-]{1,19}$"


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


class TilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    icon: str | None = Field(default=None, max_length=16)
    local_url: str | None = Field(default=None, max_length=300, pattern=URL)
    remote_url: str | None = Field(default=None, max_length=300, pattern=URL)
    app_key: str | None = Field(default=None, pattern=APP_KEY)
    people: list[int] | None = None


class TileOut(BaseModel):
    id: int
    name: str
    icon: str
    local_url: str
    remote_url: str | None
    position: int
    app_key: str | None
    people: list[int]

    @field_validator("people", mode="before")
    @classmethod
    def person_ids(cls, value):
        return sorted(p if isinstance(p, int) else p.id for p in value)
