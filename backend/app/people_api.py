"""Managing the family's people (parents only, at home): adding them, their details, PINs and roles. One's own login
and account are in login_api."""

import threading

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from . import addresses, auth, models, pin_reset, pins, schemas
from .database import get_db
from .errors import api_error

router = APIRouter(tags=["people"])


def may_change(actor: models.Person, person: models.Person) -> bool:
    """A parent changes the children and themselves, never another parent (spec 2026-10-30 hub hardening): between
    separated parents, one must not take over the other's account."""
    return person.role != models.Role.PARENT or person.id == actor.id


def _get(db: Session, person_id: int) -> models.Person:
    person = db.get(models.Person, person_id)
    if person is None:
        raise api_error(404, "person_not_found")
    return person


def _check_free(db: Session, name: str | None, email: str | None, except_id: int | None = None) -> None:
    others = db.query(models.Person)
    if except_id is not None:
        others = others.filter(models.Person.id != except_id)
    if name is not None and others.filter(models.Person.name_key == models.name_key(name)).first():
        raise api_error(409, "name_taken")
    if email and others.filter(models.Person.email == email).first():
        raise api_error(409, "email_taken")


@router.get("/people", response_model=list[schemas.PersonOut])
def list_people(actor: models.Person = Depends(auth.require_parent), db: Session = Depends(get_db)):
    return [
        schemas.PersonOut.of(p, can_edit=may_change(actor, p))
        for p in db.query(models.Person).order_by(models.Person.name_key)
    ]


@router.post("/people", status_code=201, response_model=schemas.PersonOut, dependencies=[Depends(auth.require_parent)])
def add_person(body: schemas.PersonIn, db: Session = Depends(get_db)):
    _check_free(db, body.name, body.email)
    person = models.Person(
        name=body.name.strip(),
        name_key=models.name_key(body.name),
        pin_hash=pins.get_pin_hash(body.pin),
        role=body.role,
        color=body.color,
        language=body.language,
    )
    db.add(person)
    db.flush()
    confirm_due = addresses.set_address(db, person, body.email)
    db.commit()
    if confirm_due:
        addresses.send_confirmation(db, person)
    return schemas.PersonOut.of(person)


# One change of parents at a time: the "last parent" check reads the others, and two parents making themselves children
# at once would both pass it. The backend is one process, so a lock in memory is enough
_parents_lock = threading.Lock()


def _check_last_parent(db: Session, person: models.Person, body: schemas.PersonPatch) -> None:
    """The family keeps an active parent: the last one can't become a child or inactive."""
    stays_parent = (body.role or person.role) == models.Role.PARENT and (
        person.active if body.active is None else body.active
    )
    if person.role == models.Role.PARENT and person.active and not stays_parent:
        others = db.query(models.Person).filter(
            models.Person.role == models.Role.PARENT, models.Person.active.is_(True), models.Person.id != person.id
        )
        if others.count() == 0:
            raise api_error(400, "last_parent")


def _not_another_parent(actor: models.Person, person: models.Person) -> None:
    if not may_change(actor, person):
        raise api_error(403, "other_parent")


@router.patch("/people/{person_id}", response_model=schemas.PersonOut)
def change_person(
    person_id: int,
    body: schemas.PersonPatch,
    actor: models.Person = Depends(auth.require_parent),
    db: Session = Depends(get_db),
):
    person = _get(db, person_id)
    _not_another_parent(actor, person)
    fields = body.model_fields_set
    new_email = body.email if "email" in fields else person.email
    # The address the form shows may be the one still waiting for confirmation: saving it again changes nothing, but
    # mails a new link when the last one expired (the "link expired" message says to save the address again)
    send_again = False
    if "email" in fields and new_email is not None and new_email == person.email_pending:
        fields = fields - {"email"}
        send_again = addresses.link_lost(db, person)
    if person.id == actor.id and "email" in fields and new_email != person.email:
        # The address is the way back in when the PIN is forgotten: a browser left logged in isn't enough to change it
        if not body.current_pin:
            raise api_error(400, "pin_needed")
        pins.check_pin(db, actor, body.current_pin, api_error(401, "wrong_pin"))
    _check_free(db, body.name if "name" in fields else None, body.email if "email" in fields else None, person.id)
    with _parents_lock:
        # What other requests saved meanwhile
        db.refresh(person)
        _check_last_parent(db, person, body)
        if body.name is not None:
            person.name, person.name_key = body.name.strip(), models.name_key(body.name)
        confirm_due = "email" in fields and addresses.set_address(db, person, new_email)
        if body.role is not None:
            person.role = body.role
        if body.active is not None and body.active != person.active:
            person.active = body.active
            # Deactivated: every app hears the logins are over; open reset links end too
            person.token_version += 1
            pin_reset.end_links(db, person)
        if "color" in fields:
            person.color = body.color
        if "language" in fields:
            person.language = body.language
        db.commit()
    if confirm_due or send_again:
        addresses.send_confirmation(db, person)
    return schemas.PersonOut.of(person)


@router.delete("/people/{person_id}")
def delete_person(person_id: int, actor: models.Person = Depends(auth.require_parent), db: Session = Depends(get_db)):
    """Someone who left the family for good, gone from the hub with their PIN, address, devices, links and app access
    (privacy review 2026-11-07); their name and address are free again. Only once inactive, so the logins already
    ended and a slip of the finger can't remove someone in use. Never another parent. Each app keeps what it holds about
    the person (hidden, as for someone inactive) until it's deleted there."""
    person = _get(db, person_id)
    _not_another_parent(actor, person)
    if person.active:
        raise api_error(409, "person_active")
    db.delete(person)
    db.commit()
    return {"deleted": person_id}


@router.put("/people/{person_id}/pin")
def set_pin(
    person_id: int,
    body: schemas.PinIn,
    actor: models.Person = Depends(auth.require_parent),
    db: Session = Depends(get_db),
):
    person = _get(db, person_id)
    _not_another_parent(actor, person)
    if person.id == actor.id:
        # One's own PIN only with the old one (PUT /me/pin) or a reset link
        raise api_error(403, "own_pin_needs_old_pin")
    pins.new_pin(person, body.pin)
    db.commit()
    return {"ok": True}
