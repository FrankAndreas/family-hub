"""What an app pulls from the hub: the people who may use it (spec 2026-10-30, part A).

Asked with the login of whoever uses the app at that moment (as /api/session), so an app needs no password of its own.
No PIN data, and e-mail addresses only for an app whose tile allows it (`share_email`), and only confirmed ones: most
apps only need to know and show their people."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import config, models, session_api
from .database import get_db
from .errors import api_error

router = APIRouter(tags=["apps"])


@router.get("/api/apps/{key}/people")
def app_people(key: str, person: models.Person | None = Depends(session_api.app_caller), db: Session = Depends(get_db)):
    if person is None:
        raise api_error(401, "not_logged_in")
    tile = db.query(models.Tile).filter(models.Tile.app_key == key).first()
    if tile is None:
        raise api_error(404, "app_not_found")
    if person not in tile.people:
        raise api_error(403, "no_access")
    return [
        {
            "id": p.id,
            "name": p.name,
            "role": p.role.value,
            "color": p.color,
            "language": p.language or config.default_language(),
            **({"email": p.email} if tile.share_email else {}),
        }
        for p in sorted(tile.people, key=lambda p: p.name_key)
        if p.active
    ]
