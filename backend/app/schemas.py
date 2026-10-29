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
