"""The start page's tiles. At home every app links to its home address; outside (through the tunnel) only the apps
with an outside address are shown, and no home address ever leaves the house."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import update
from sqlalchemy.orm import Session

from . import auth, models, schemas
from .database import get_db
from .errors import api_error

router = APIRouter(tags=["tiles"])


def _ordered(db: Session) -> list[models.Tile]:
    return db.query(models.Tile).order_by(models.Tile.position, models.Tile.id).all()


def _get(db: Session, tile_id: int) -> models.Tile:
    tile = db.get(models.Tile, tile_id)
    if tile is None:
        raise api_error(404, "tile_not_found")
    return tile


def _people(db: Session, ids: list[int]) -> list[models.Person]:
    found = db.query(models.Person).filter(models.Person.id.in_(ids)).all()
    if len(found) != len(set(ids)):
        raise api_error(400, "person_not_found")
    return found


def _protected(tile: models.Tile, actor: models.Person) -> set[int]:
    """The other parents who used the app under its current key: only they themselves can untick themselves, and
    while they are ticked the app can't be deleted nor its key changed. Someone who never used it loses nothing."""
    parents = {p.id for p in tile.people if p.role == models.Role.PARENT and p.id != actor.id}
    return parents & {a.person_id for a in tile.usage}


def _check_key(db: Session, key: str | None, tile_id: int | None = None) -> None:
    if key is None:
        return
    other = models.Tile.by_key(db, key)
    if other is not None and other.id != tile_id:
        raise api_error(409, "app_key_taken")


@router.get("/tiles")
def tiles(request: Request, person: models.Person = Depends(auth.current_person), db: Session = Depends(get_db)):
    outside = auth.through_tunnel(request)
    return [
        {
            "id": t.id,
            "name": t.name,
            "icon": t.icon,
            "url": t.remote_url if outside else t.local_url,
            "home_only": t.remote_url is None,
        }
        for t in _ordered(db)
        # Outside only apps with an outside address; an app with a key only for the people who may use it
        if (not outside or t.remote_url) and (t.app_key is None or person in t.people)
    ]


@router.get("/tiles/manage", response_model=list[schemas.TileOut], dependencies=[Depends(auth.require_parent)])
def manage_tiles(db: Session = Depends(get_db)):
    return _ordered(db)


@router.post("/tiles", status_code=201, response_model=schemas.TileOut, dependencies=[Depends(auth.require_parent)])
def add_tile(body: schemas.TileIn, db: Session = Depends(get_db)):
    _check_key(db, body.app_key)
    last = db.query(models.Tile).order_by(models.Tile.position.desc()).first()
    tile = models.Tile(
        **body.model_dump(exclude={"people"}),
        people=_people(db, body.people),
        position=(last.position + 1) if last else 0,
    )
    db.add(tile)
    db.commit()
    return tile


@router.patch("/tiles/{tile_id}", response_model=schemas.TileOut)
def change_tile(
    tile_id: int,
    body: schemas.TilePatch,
    actor: models.Person = Depends(auth.require_parent),
    db: Session = Depends(get_db),
):
    tile = _get(db, tile_id)
    # A parent can't take an app away from another parent who uses it (security review 2026-10-30): not by unticking
    # them, and not by moving the app's key to another tile. A key typed wrong or someone who never opened the app can
    # be corrected: that takes nothing from anyone
    protected = _protected(tile, actor)
    if protected and body.people is not None and not protected <= set(body.people):
        raise api_error(403, "tile_other_parent")
    key_changes = "app_key" in body.model_fields_set and body.app_key != tile.app_key
    if protected and key_changes:
        raise api_error(403, "tile_key_in_use")
    if key_changes:
        _check_key(db, body.app_key, tile.id)
    for field in body.model_fields_set:
        value = getattr(body, field)
        if field == "people":
            if value is not None:
                tile.people = _people(db, value)
            continue
        # Name, icon and the home address can't be emptied; the outside address, the app key and the AUD tag can
        if value is None and field not in ("remote_url", "app_key", "cf_audience"):
            continue
        setattr(tile, field, value)
    if key_changes:
        # Under the new key nobody has used the app yet
        db.flush()
        db.execute(
            update(models.tile_access)
            .where(models.tile_access.c.tile_id == tile.id)
            .values(first_used_at=None, last_used_at=None)
        )
    db.commit()
    return tile


@router.delete("/tiles/{tile_id}")
def delete_tile(tile_id: int, actor: models.Person = Depends(auth.require_parent), db: Session = Depends(get_db)):
    tile = _get(db, tile_id)
    if _protected(tile, actor):
        raise api_error(403, "tile_other_parent")
    db.delete(tile)
    db.commit()
    return {"deleted": tile_id}


@router.put("/tiles/order", dependencies=[Depends(auth.require_parent)])
def order_tiles(ids: list[int], db: Session = Depends(get_db)):
    found = {t.id: t for t in db.query(models.Tile)}
    if sorted(ids) != sorted(found):
        raise api_error(400, "tile_order_incomplete")
    for position, tile_id in enumerate(ids):
        found[tile_id].position = position
    db.commit()
    return {"ok": True}
