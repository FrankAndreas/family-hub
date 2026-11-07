"""The family login: a PIN at home, Cloudflare Access outside (spec 2026-10-29).

At home the PIN login sets the cookie `hub_session` for COOKIE_DOMAIN (e.g. local.<domain>), so every app at home gets
it and the addresses through Cloudflare never do. A request that came through the Cloudflare tunnel (it carries
Cf-Connecting-Ip) gets no PIN login and its cookie counts for nothing: outside, only a Cloudflare Access token does.

Here: the hub's tokens and cookies, and who is asking (the dependencies). Checking a PIN is in pins.py.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Request, Response, status
from sqlalchemy.orm import Session

from . import cloudflare, config, database, keys, models
from .errors import api_error
from .timeutil import utcnow

COOKIE = "hub_session"
# Only the hub gets it: managing people, PINs and apps needs it as well (spec 2026-10-30 hub hardening)
MANAGE_COOKIE = "hub_manage"
ISSUER = "family-hub"
ALGORITHM = "EdDSA"
TOKEN_LIFETIME = timedelta(days=30)
# The hub's own pages send it with every change; another page on the family's domain can't make a browser send it
APP_HEADER = "x-requested-with"
APP_HEADER_VALUE = "hub"
# Cloudflare sets it on every request through the tunnel; the DSM reverse proxy at home doesn't
TUNNEL_HEADER = "cf-connecting-ip"


def through_tunnel(request: Request) -> bool:
    return TUNNEL_HEADER in request.headers


def require_app_header(request: Request) -> None:
    """Changes come from the hub's own pages only (security review 2026-10-30). The login cookie is SameSite=lax, so
    every page on the family's domain (any app at home) could otherwise make a browser send it with a change."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(APP_HEADER) != APP_HEADER_VALUE:
        raise api_error(status.HTTP_403_FORBIDDEN, "csrf")


def issue_tokens(person: models.Person) -> tuple[str, str]:
    """A login: the session token every app at home gets, and the manage token only the hub gets (spec 2026-10-30 hub
    hardening). The session's id (jti) lets "Log out" end exactly this login; the manage token names it (sid)."""
    key, kid = keys.signing_key()
    common = {
        "iss": ISSUER,
        "sub": str(person.id),
        "ver": person.token_version,
        "exp": datetime.now(timezone.utc) + TOKEN_LIFETIME,
    }
    jti = uuid.uuid4().hex
    session = jwt.encode({**common, "typ": "session", "jti": jti}, key, algorithm=ALGORITHM, headers={"kid": kid})
    manage = jwt.encode({**common, "typ": "manage", "sid": jti}, key, algorithm=ALGORITHM, headers={"kid": kid})
    return session, manage


def token_claims(token: str | None, typ: str) -> dict | None:
    """The claims of a hub token of this type, if it is ours and not expired; any other token is None."""
    if not token:
        return None
    key, _ = keys.signing_key()
    try:
        claims = jwt.decode(token, key.public_key(), algorithms=[ALGORITHM], issuer=ISSUER)
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == typ else None


def _ended(db: Session, jti: object) -> bool:
    return not isinstance(jti, str) or db.get(models.EndedLogin, jti) is not None


def _person(db: Session, claims: dict) -> models.Person | None:
    try:
        person_id, version = int(claims["sub"]), int(claims["ver"])
    except KeyError, ValueError, TypeError:
        return None
    person = db.get(models.Person, person_id)
    if person is None or not person.active or person.token_version != version:
        return None
    return person


def person_for_token(db: Session, token: str | None) -> models.Person | None:
    """The person a session token names, if it is ours, not expired, not logged out, not ended everywhere
    (token_version) and the person is active."""
    claims = token_claims(token, "session")
    if claims is None or _ended(db, claims.get("jti")):
        return None
    return _person(db, claims)


def end_login(db: Session, token: str | None) -> None:
    """ "Log out": this session token is no login any more, here or in any app (the caller commits). Ended logins that
    would have expired by now are dropped."""
    now = utcnow()
    db.query(models.EndedLogin).filter(models.EndedLogin.expires_at < now).delete()
    claims = token_claims(token, "session")
    jti = claims.get("jti") if claims else None
    if isinstance(jti, str) and db.get(models.EndedLogin, jti) is None:
        expires = datetime.fromtimestamp(int(claims["exp"]), timezone.utc).replace(tzinfo=None)  # type: ignore[index]
        db.add(models.EndedLogin(jti=jti, expires_at=expires))


def set_cookies(response: Response, session: str, manage: str) -> None:
    """The session cookie for every app at home (COOKIE_DOMAIN); the manage cookie for the hub alone (no domain)."""
    settings = config.settings()
    max_age = int(TOKEN_LIFETIME.total_seconds())
    response.set_cookie(
        COOKIE,
        session,
        max_age=max_age,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        MANAGE_COOKIE,
        manage,
        max_age=max_age,
        path="/api",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_cookies(response: Response) -> None:
    settings = config.settings()
    response.delete_cookie(
        COOKIE, domain=settings.cookie_domain, secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(MANAGE_COOKIE, path="/api", secure=settings.cookie_secure, httponly=True, samesite="strict")


def current_person_or_none(request: Request, db: Session) -> models.Person | None:
    """Who is asking: outside the Cloudflare Access token, at home the hub cookie."""
    if through_tunnel(request):
        return cloudflare.person_for(request, db)
    return person_for_token(db, request.cookies.get(COOKIE))


def current_person(request: Request, db: Session = Depends(database.get_db)) -> models.Person:
    person = current_person_or_none(request, db)
    if person is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "not_logged_in")
    return person


def require_manage_at_home(request: Request) -> None:
    """Managing people, PINs and apps happens at home only (the user's choice, 2026-10-29): a parent's mailbox someone
    broke into gets past Cloudflare Access, but must not take over the family's accounts."""
    if through_tunnel(request):
        raise api_error(status.HTTP_403_FORBIDDEN, "manage_at_home_only")


def require_manager(
    request: Request, person: models.Person = Depends(current_person), db: Session = Depends(database.get_db)
) -> models.Person:
    """Whoever changes something in the hub, at home, with the manage cookie of this very login (spec 2026-10-30 hub
    hardening): the session cookie alone, which every app at home gets, manages nothing."""
    require_manage_at_home(request)
    session = token_claims(request.cookies.get(COOKIE), "session")
    manage = token_claims(request.cookies.get(MANAGE_COOKIE), "manage")
    if session is None or manage is None or manage.get("sid") != session.get("jti"):
        raise api_error(status.HTTP_403_FORBIDDEN, "login_again")
    owner = _person(db, manage)
    if owner is None or owner.id != person.id:
        raise api_error(status.HTTP_403_FORBIDDEN, "login_again")
    return person


def require_parent(person: models.Person = Depends(require_manager)) -> models.Person:
    """A parent, at home, with the manage cookie: every parent right is about managing the family."""
    if person.role != models.Role.PARENT:
        raise api_error(status.HTTP_403_FORBIDDEN, "parents_only")
    return person


def require_home(request: Request) -> None:
    if through_tunnel(request):
        raise api_error(status.HTTP_403_FORBIDDEN, "login_at_home_only")
