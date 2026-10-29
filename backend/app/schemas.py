from typing import Literal

from pydantic import BaseModel, Field

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
    role: Role
    active: bool
    color: str | None
    language: str
    # Whether the person picked the language themselves (else the default)
    language_chosen: bool


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
    role: Role | None = None
    active: bool | None = None
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL)
    color: str | None = Field(default=None, pattern=COLOR)
    language: Literal["de", "en"] | None = None


class PinIn(BaseModel):
    pin: str = Field(pattern=PIN)


class OwnPinIn(BaseModel):
    old_pin: str = Field(pattern=PIN)
    pin: str = Field(pattern=PIN)


class MePatch(BaseModel):
    language: Literal["de", "en"] | None = None
    color: str | None = Field(default=None, pattern=COLOR)
