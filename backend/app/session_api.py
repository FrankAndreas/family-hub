"""What the apps use: the public key to check a hub login (JWKS), and whether a login still counts (/api/session).

An app reads the login (the `hub_session` cookie at home), may check its signature itself with the JWKS, and asks
/api/session (briefly cached) to honour "log out everywhere", a new PIN and deactivated people."""

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import auth, cloudflare, config, keys, models
from .database import get_db

router = APIRouter(tags=["session"])
_bearer = HTTPBearer(auto_error=False)


@router.get("/api/keys")
@router.get("/.well-known/jwks.json")
def jwks():
    return keys.jwks()


def session_person(person: models.Person) -> dict:
    return {
        "id": person.id,
        "name": person.name,
        "email": person.email,
        "role": person.role.value,
        "color": person.color,
        "language": person.language or config.default_language(),
    }


@router.get("/api/session")
def session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
):
    """The login as an app passes it: the hub login (Bearer) at home, or the Cloudflare Access token (as Cloudflare
    sent it, Cf-Access-Jwt-Assertion) from outside; else the browser's own login."""
    if credentials is not None:
        person = auth.person_for_token(db, credentials.credentials)
    elif cloudflare.HEADER in request.headers:
        person = cloudflare.person_for(request, db)
    else:
        person = auth.current_person_or_none(request, db)
    if person is None:
        return {"valid": False, "person": None}
    return {"valid": True, "person": session_person(person)}
