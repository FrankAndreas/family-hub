"""One's own login and account: logging in at home and out, who one is, one's own PIN, language and colour, a forgotten
PIN and confirming a new e-mail address. Managing the family's people is in people_api."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from . import addresses, auth, config, mailer, models, pin_reset, pins, schemas
from .database import get_db
from .errors import api_error

router = APIRouter(tags=["login"])


@router.get("/config")
def public_config():
    """What the login screen needs before anyone is logged in: the language for browsers that speak neither."""
    return {"default_language": config.default_language(), "pin_reset": mailer.is_configured()}


@router.get("/people/public", response_model=list[schemas.PersonPublic], dependencies=[Depends(auth.require_home)])
def public_people(db: Session = Depends(get_db)):
    """Names and colours for the login screen at home."""
    return db.query(models.Person).filter(models.Person.active.is_(True)).order_by(models.Person.name_key).all()


@router.post("/login", dependencies=[Depends(auth.require_home)])
def login(body: schemas.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    device = request.cookies.get(pins.DEVICE_COOKIE)
    person = pins.authenticate(db, body.name, body.pin, device)
    pins.remember_device(db, response, person, device)
    db.commit()
    auth.set_cookies(response, *auth.issue_tokens(person))
    return schemas.PersonOut.of(person)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Ends this login, in the hub and in every app (they ask /api/session); other devices stay logged in."""
    auth.end_login(db, request.cookies.get(auth.COOKIE))
    db.commit()
    auth.clear_cookies(response)
    return {"ok": True}


@router.post("/logout-everywhere")
def logout_everywhere(
    response: Response, person: models.Person = Depends(auth.current_person), db: Session = Depends(get_db)
):
    """Ends every login of this person, on every device and in every app."""
    person.token_version += 1
    db.commit()
    auth.clear_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=schemas.PersonOut)
def me(request: Request, person: models.Person = Depends(auth.current_person)):
    return schemas.PersonOut.of(person, not auth.through_tunnel(request))


@router.patch("/me", response_model=schemas.PersonOut)
def change_me(
    body: schemas.MePatch,
    request: Request,
    person: models.Person = Depends(auth.current_person),
    db: Session = Depends(get_db),
):
    # Outside, the Cloudflare login is enough for one's own language and colour; at home it takes the manage cookie
    if not auth.through_tunnel(request):
        auth.require_manager(request, person, db)
    fields = body.model_fields_set
    if "language" in fields:
        person.language = body.language
    if "color" in fields:
        person.color = body.color
    db.commit()
    return schemas.PersonOut.of(person, not auth.through_tunnel(request))


@router.put("/me/pin")
def set_own_pin(
    body: schemas.OwnPinIn,
    response: Response,
    person: models.Person = Depends(auth.require_manager),
    db: Session = Depends(get_db),
):
    # Counts toward the lock like a login: a session alone doesn't let anyone try PINs
    pins.check_pin(db, person, body.old_pin, api_error(401, "wrong_pin"))
    pins.new_pin(person, body.pin)
    db.commit()
    # Other devices are logged out; this one stays
    auth.set_cookies(response, *auth.issue_tokens(person))
    return {"ok": True}


@router.post("/pin-reset", dependencies=[Depends(auth.require_home)])
def ask_pin_reset(body: schemas.PinResetIn, db: Session = Depends(get_db)):
    """Forgot PIN: a link to the person's address, if any. The same answer whatever the case."""
    pin_reset.request_reset(db, body.name)
    return {"ok": True}


@router.post("/pin-reset/confirm", dependencies=[Depends(auth.require_home)])
def confirm_pin_reset(body: schemas.PinResetConfirmIn, db: Session = Depends(get_db)):
    pin_reset.confirm(db, body.token, body.pin)
    db.commit()
    return {"ok": True}


@router.post("/email-confirm", dependencies=[Depends(auth.require_home)])
def confirm_email(body: schemas.EmailConfirmIn, db: Session = Depends(get_db)):
    """The link mailed to a new address: from now on it is the person's address."""
    addresses.confirm(db, body.token)
    db.commit()
    return {"ok": True}
