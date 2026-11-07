"""What the apps use: the public key to check a hub login (JWKS), and whether a login still counts (/api/session).

An app reads the login (the `hub_session` cookie at home), may check its signature itself with the JWKS, and asks
/api/session (briefly cached) to honour "log out everywhere", a new PIN and deactivated people."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import auth, cloudflare, keys, models, schemas, timeutil
from .database import get_db

router = APIRouter(tags=["session"])
USE_RESOLUTION = timedelta(hours=1)
# In its last week a hub login tells the app to send the browser through the hub once, which renews it (auth.renew): a
# login in use doesn't run out, also for someone who only ever opens an app (app integration review 2026-11-07)
RENEW_HINT = timedelta(days=7)
_bearer = HTTPBearer(auto_error=False)


@router.get("/api/keys")
@router.get("/.well-known/jwks.json")
def jwks():
    return keys.jwks()


@dataclass
class AppLogin:
    """Who an app asks about, and the app (its tile) when it named a known key."""

    person: models.Person | None
    tile: models.Tile | None
    # A hub login at home in its last RENEW_HINT
    renew: bool = False


def _login(
    request: Request, credentials: HTTPAuthorizationCredentials | None, db: Session, app_key: str | None
) -> AppLogin:
    """The login as an app passes it: the hub login (Bearer) at home, or the Cloudflare Access token (as Cloudflare
    sent it, Cf-Access-Jwt-Assertion) from outside; else the browser's own login. A Cloudflare token for an app whose
    tile names its Access application counts only when made for that application (hub#12).

    Home and outside are told apart only by Cf-Connecting-Ip (security review 2026-11-07): at home a Cloudflare token
    counts for nothing, so one that leaked can't be used there without going through Cloudflare."""
    tile = models.Tile.by_key(db, app_key) if app_key else None
    audience = tile.cf_audience if tile else None
    if auth.through_tunnel(request):
        # From outside only Cloudflare's token counts: a hub token there may be a stolen home cookie, which the app
        # passed on (apps pass Cf-Connecting-Ip on with it; see README "For apps")
        person = cloudflare.person_for(request, db, audience)
    elif credentials is not None:
        person = auth.person_for_token(db, credentials.credentials)
        return AppLogin(person, tile, person is not None and _ends_soon(credentials.credentials))
    else:
        person = auth.current_person_or_none(request, db)
    return AppLogin(person, tile)


def _ends_soon(token: str) -> bool:
    claims = auth.token_claims(token, "session")
    exp = claims.get("exp") if claims else None
    return isinstance(exp, int) and datetime.fromtimestamp(exp, timezone.utc) - datetime.now(timezone.utc) < RENEW_HINT


def note_use(db: Session, login: AppLogin) -> None:
    """The app asked for its key with this person's login: they use it (see tiles_api.change_tile). Kept to the hour,
    so not every page of an app writes. The caller commits."""
    if login.person is None or login.tile is None:
        return
    access = db.get(models.TileAccess, (login.tile.id, login.person.id))
    if access is None:
        return
    now = timeutil.utcnow()
    if access.last_used_at is not None and now - access.last_used_at < USE_RESOLUTION:
        return
    access.first_used_at = access.first_used_at or now
    access.last_used_at = now


def caller(
    request: Request,
    app: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AppLogin:
    """The login for /api/session?app=<key>."""
    return _login(request, credentials, db, app)


def app_caller(
    request: Request,
    key: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AppLogin:
    """The login for /api/apps/<key>/..."""
    return _login(request, credentials, db, key)


def hidden_fields(tile: models.Tile | None) -> set[str] | None:
    """What an app doesn't see of a person: the e-mail address, unless its tile allows it (`share_email`). Without the
    address, not as null: also the person's own, or every app would learn each address as its owner logs in."""
    return None if tile is not None and tile.share_email else {"email"}


@router.get("/api/session", response_model=schemas.SessionOut, response_model_exclude_unset=True)
def session(app: str | None = None, login: AppLogin = Depends(caller), db: Session = Depends(get_db)):
    """Whether a login still counts; with ?app=<key> also whether the person may use that app. `valid` stays about the
    login, so an app can tell "not logged in" (send to the hub) from "no access" (say so) without a loop."""
    note_use(db, login)
    db.commit()
    if login.person is None:
        return schemas.SessionOut(valid=False, person=None)
    # Validated again from what the app may see, so a left-out field stays out of the answer (exclude_unset)
    shown = schemas.AppPerson.model_validate(login.person).model_dump(exclude=hidden_fields(login.tile))
    found = schemas.SessionOut(valid=True, person=schemas.AppPerson.model_validate(shown), renew=login.renew)
    if app is not None:
        found.access = login.tile is not None and login.person in login.tile.people
    return found
