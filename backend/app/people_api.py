"""Logging in at home, logging out, and who one is."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from . import auth, config, models, schemas
from .database import get_db

router = APIRouter(tags=["people"])


def person_out(person: models.Person) -> schemas.PersonOut:
    return schemas.PersonOut(
        id=person.id,
        name=person.name,
        email=person.email,
        role=person.role,
        active=person.active,
        color=person.color,
        language=person.language or config.default_language(),
        language_chosen=person.language is not None,
    )


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
def me(person: models.Person = Depends(auth.current_person)):
    return person_out(person)
