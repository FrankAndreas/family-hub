"""Logging in at home, logging out, and who one is."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from . import auth, config, models, schemas
from .database import get_db
from .errors import api_error

router = APIRouter(tags=["people"])


def person_out(person: models.Person, at_home: bool = True) -> schemas.PersonOut:
    return schemas.PersonOut(
        at_home=at_home,
        id=person.id,
        name=person.name,
        email=person.email,
        role=person.role,
        active=person.active,
        color=person.color,
        language=person.language or config.default_language(),
        language_chosen=person.language is not None,
    )


@router.get("/config")
def public_config():
    """What the login screen needs before anyone is logged in: the language for browsers that speak neither."""
    return {"default_language": config.default_language()}


@router.get("/people/public", response_model=list[schemas.PersonPublic], dependencies=[Depends(auth.require_home)])
def public_people(db: Session = Depends(get_db)):
    """Names and colours for the login screen at home."""
    return db.query(models.Person).filter(models.Person.active.is_(True)).order_by(models.Person.name_key).all()


@router.post("/login", dependencies=[Depends(auth.require_home)])
def login(body: schemas.LoginIn, response: Response, db: Session = Depends(get_db)):
    person = auth.authenticate(db, body.name, body.pin)
    auth.set_cookie(response, auth.issue_token(person))
    return person_out(person)


@router.post("/logout")
def logout(response: Response):
    auth.clear_cookie(response)
    return {"ok": True}


@router.post("/logout-everywhere")
def logout_everywhere(
    response: Response, person: models.Person = Depends(auth.current_person), db: Session = Depends(get_db)
):
    """Ends every login of this person, on every device and in every app."""
    person.token_version += 1
    db.commit()
    auth.clear_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=schemas.PersonOut)
def me(request: Request, person: models.Person = Depends(auth.current_person)):
    return person_out(person, not auth.through_tunnel(request))


# Managing the family's people: parents, and everyone for their own PIN, language and colour


def _get(db: Session, person_id: int) -> models.Person:
    person = db.get(models.Person, person_id)
    if person is None:
        raise api_error(404, "person_not_found")
    return person


def _check_free(db: Session, name: str | None, email: str | None, except_id: int | None = None) -> None:
    others = db.query(models.Person)
    if except_id is not None:
        others = others.filter(models.Person.id != except_id)
    if name is not None and others.filter(models.Person.name_key == auth.name_key(name)).first():
        raise api_error(409, "name_taken")
    if email and others.filter(models.Person.email == email.strip().casefold()).first():
        raise api_error(409, "email_taken")


def _new_pin(person: models.Person, pin: str) -> None:
    """A new PIN ends every login made with the old one and lifts a lock."""
    person.pin_hash = auth.get_pin_hash(pin)
    person.token_version += 1
    person.failed_logins = 0
    person.lockouts = 0
    person.locked_until = None


@router.get("/people", response_model=list[schemas.PersonOut], dependencies=[Depends(auth.require_parent)])
def list_people(db: Session = Depends(get_db)):
    return [person_out(p) for p in db.query(models.Person).order_by(models.Person.name_key)]


@router.post("/people", status_code=201, response_model=schemas.PersonOut, dependencies=[Depends(auth.require_parent)])
def add_person(body: schemas.PersonIn, db: Session = Depends(get_db)):
    _check_free(db, body.name, body.email)
    person = models.Person(
        name=body.name.strip(),
        name_key=auth.name_key(body.name),
        email=body.email.strip().casefold() if body.email else None,
        pin_hash=auth.get_pin_hash(body.pin),
        role=body.role,
        color=body.color,
        language=body.language,
    )
    db.add(person)
    db.commit()
    return person_out(person)


@router.patch("/people/{person_id}", response_model=schemas.PersonOut, dependencies=[Depends(auth.require_parent)])
def change_person(person_id: int, body: schemas.PersonPatch, db: Session = Depends(get_db)):
    person = _get(db, person_id)
    fields = body.model_fields_set
    _check_free(db, body.name if "name" in fields else None, body.email if "email" in fields else None, person.id)
    stays_parent = (body.role or person.role) == models.Role.PARENT and (
        person.active if body.active is None else body.active
    )
    if person.role == models.Role.PARENT and person.active and not stays_parent:
        others = db.query(models.Person).filter(
            models.Person.role == models.Role.PARENT, models.Person.active.is_(True), models.Person.id != person.id
        )
        if others.count() == 0:
            raise api_error(400, "last_parent")
    if body.name is not None:
        person.name, person.name_key = body.name.strip(), auth.name_key(body.name)
    if "email" in fields:
        person.email = body.email.strip().casefold() if body.email else None
    if body.role is not None:
        person.role = body.role
    if body.active is not None and body.active != person.active:
        person.active = body.active
        # Deactivated: every app hears the logins are over
        person.token_version += 1
    if "color" in fields:
        person.color = body.color
    if "language" in fields:
        person.language = body.language
    db.commit()
    return person_out(person)


@router.put("/people/{person_id}/pin", dependencies=[Depends(auth.require_parent)])
def set_pin(person_id: int, body: schemas.PinIn, db: Session = Depends(get_db)):
    _new_pin(_get(db, person_id), body.pin)
    db.commit()
    return {"ok": True}


@router.put("/me/pin", dependencies=[Depends(auth.require_manage_at_home)])
def set_own_pin(
    body: schemas.OwnPinIn,
    response: Response,
    person: models.Person = Depends(auth.current_person),
    db: Session = Depends(get_db),
):
    # Counts toward the lock like a login: a session alone doesn't let anyone try PINs
    auth.check_pin(db, person, body.old_pin, api_error(401, "wrong_pin"))
    _new_pin(person, body.pin)
    db.commit()
    # Other devices are logged out; this one stays
    auth.set_cookie(response, auth.issue_token(person))
    return {"ok": True}


@router.patch("/me", response_model=schemas.PersonOut)
def change_me(
    body: schemas.MePatch,
    request: Request,
    person: models.Person = Depends(auth.current_person),
    db: Session = Depends(get_db),
):
    fields = body.model_fields_set
    if "language" in fields:
        person.language = body.language
    if "color" in fields:
        person.color = body.color
    db.commit()
    return person_out(person, not auth.through_tunnel(request))
