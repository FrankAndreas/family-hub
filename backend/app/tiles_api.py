"""The start page's tiles. At home every app links to its home address; outside (through the tunnel) only the apps
with an outside address are shown, and no home address ever leaves the house."""

from fastapi import APIRouter, Depends, Request
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


@router.get("/tiles", dependencies=[Depends(auth.current_person)])
def tiles(request: Request, db: Session = Depends(get_db)):
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
        if not outside or t.remote_url
    ]


@router.get("/tiles/manage", response_model=list[schemas.TileOut], dependencies=[Depends(auth.require_parent)])
def manage_tiles(db: Session = Depends(get_db)):
    return _ordered(db)


@router.post("/tiles", status_code=201, response_model=schemas.TileOut, dependencies=[Depends(auth.require_parent)])
def add_tile(body: schemas.TileIn, db: Session = Depends(get_db)):
    last = db.query(models.Tile).order_by(models.Tile.position.desc()).first()
    tile = models.Tile(**body.model_dump(), position=(last.position + 1) if last else 0)
    db.add(tile)
    db.commit()
    return tile


@router.patch("/tiles/{tile_id}", response_model=schemas.TileOut, dependencies=[Depends(auth.require_parent)])
def change_tile(tile_id: int, body: schemas.TilePatch, db: Session = Depends(get_db)):
    tile = _get(db, tile_id)
    for field in body.model_fields_set:
        value = getattr(body, field)
        # Name, icon and the home address can't be emptied; the outside address can (home only)
        if value is None and field != "remote_url":
            continue
        setattr(tile, field, value)
    db.commit()
    return tile


@router.delete("/tiles/{tile_id}", dependencies=[Depends(auth.require_parent)])
def delete_tile(tile_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, tile_id))
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
