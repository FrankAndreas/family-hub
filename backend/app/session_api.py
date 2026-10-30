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


def caller(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.Person | None:
    """The login as an app passes it: the hub login (Bearer) at home, or the Cloudflare Access token (as Cloudflare
    sent it, Cf-Access-Jwt-Assertion) from outside; else the browser's own login."""
    if auth.through_tunnel(request):
        # From outside only Cloudflare's token counts: a hub token there may be a stolen home cookie, which the app
        # passed on (apps pass Cf-Connecting-Ip on with it; see README "For apps")
        person = cloudflare.person_for(request, db)
    elif credentials is not None:
        person = auth.person_for_token(db, credentials.credentials)
    elif cloudflare.HEADER in request.headers:
        person = cloudflare.person_for(request, db)
    else:
        person = auth.current_person_or_none(request, db)
    return person


def has_access(db: Session, person: models.Person, app_key: str) -> bool:
    tile = db.query(models.Tile).filter(models.Tile.app_key == app_key).first()
    return tile is not None and person in tile.people


@router.get("/api/session")
def session(
    app: str | None = None,
    person: models.Person | None = Depends(caller),
    db: Session = Depends(get_db),
):
    """Whether a login still counts; with ?app=<key> also whether the person may use that app. `valid` stays about the
    login, so an app can tell "not logged in" (send to the hub) from "no access" (say so) without a loop."""
    if person is None:
        return {"valid": False, "person": None}
    found: dict = {"valid": True, "person": session_person(person)}
    if app is not None:
        found["access"] = has_access(db, person, app)
    return found
