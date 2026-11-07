"""What the apps use: the public key to check a hub login (JWKS), and whether a login still counts (/api/session).

An app reads the login (the `hub_session` cookie at home), may check its signature itself with the JWKS, and asks
/api/session (briefly cached) to honour "log out everywhere", a new PIN and deactivated people."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import auth, cloudflare, keys, models, schemas, timeutil
from .database import get_db

router = APIRouter(tags=["session"])
USE_RESOLUTION = timedelta(hours=1)
_bearer = HTTPBearer(auto_error=False)


@router.get("/api/keys")
@router.get("/.well-known/jwks.json")
def jwks():
    return keys.jwks()


def _login(
    request: Request, credentials: HTTPAuthorizationCredentials | None, db: Session, app_key: str | None
) -> models.Person | None:
    """The login as an app passes it: the hub login (Bearer) at home, or the Cloudflare Access token (as Cloudflare
    sent it, Cf-Access-Jwt-Assertion) from outside; else the browser's own login. A Cloudflare token for an app whose
    tile names its Access application counts only when made for that application (hub#12)."""
    tile = models.Tile.by_key(db, app_key) if app_key else None
    audience = tile.cf_audience if tile else None
    if auth.through_tunnel(request):
        # From outside only Cloudflare's token counts: a hub token there may be a stolen home cookie, which the app
        # passed on (apps pass Cf-Connecting-Ip on with it; see README "For apps")
        person = cloudflare.person_for(request, db, audience)
    elif credentials is not None:
        person = auth.person_for_token(db, credentials.credentials)
    elif cloudflare.HEADER in request.headers:
        person = cloudflare.person_for(request, db, audience)
    else:
        person = auth.current_person_or_none(request, db)
    if person is not None and tile is not None:
        _note_use(db, tile, person)
    return person


def _note_use(db: Session, tile: models.Tile, person: models.Person) -> None:
    """The app asked for its key with this person's login: they use it (see tiles_api.change_tile). Kept to the hour,
    so not every page of an app writes."""
    access = db.get(models.TileAccess, (tile.id, person.id))
    if access is None:
        return
    now = timeutil.utcnow()
    if access.last_used_at is not None and now - access.last_used_at < USE_RESOLUTION:
        return
    access.first_used_at = access.first_used_at or now
    access.last_used_at = now
    db.commit()


def caller(
    request: Request,
    app: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.Person | None:
    """The login for /api/session?app=<key>."""
    return _login(request, credentials, db, app)


def app_caller(
    request: Request,
    key: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.Person | None:
    """The login for /api/apps/<key>/..."""
    return _login(request, credentials, db, key)


def has_access(db: Session, person: models.Person, app_key: str) -> bool:
    tile = models.Tile.by_key(db, app_key)
    return tile is not None and person in tile.people


@router.get("/api/session", response_model=schemas.SessionOut, response_model_exclude_unset=True)
def session(
    app: str | None = None,
    person: models.Person | None = Depends(caller),
    db: Session = Depends(get_db),
):
    """Whether a login still counts; with ?app=<key> also whether the person may use that app. `valid` stays about the
    login, so an app can tell "not logged in" (send to the hub) from "no access" (say so) without a loop."""
    if person is None:
        return schemas.SessionOut(valid=False, person=None)
    found = schemas.SessionOut(valid=True, person=schemas.AppPerson.model_validate(person))
    if app is not None:
        found.access = has_access(db, person, app)
    return found
