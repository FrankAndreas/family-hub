"""Apps pull their people from the hub: everyone with access to the app (spec 2026-10-30, part A)."""

from test_cloudflare import access, outside, token  # noqa: F401
from test_session import bearer

from helpers import THROUGH_TUNNEL, make_person
from app import auth, models


def budget(db, *people):
    tile = models.Tile(name="Budget", local_url="https://budget.local.example.ch", app_key="budget")
    tile.people.extend(people)
    db.add(tile)
    db.commit()
    return tile


def test_people_of_an_app(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    lena = make_person(db, "Lena", color="#f59e0b")
    max_ = make_person(db, "Max")
    budget(db, lena, admin)
    found = client.get("/api/apps/budget/people", headers=bearer(auth.issue_token(admin))).json()
    assert [p["name"] for p in found] == ["Admin", "Lena"]
    assert found[1] == {"id": lena.id, "name": "Lena", "role": "CHILD", "color": "#f59e0b", "language": "de"}
    assert client.get("/api/apps/budget/people", headers=bearer(auth.issue_token(max_))).status_code == 403
    assert client.get("/api/apps/nope/people", headers=bearer(auth.issue_token(admin))).status_code == 404
    assert client.get("/api/apps/budget/people").status_code == 401


def test_inactive_people_left_out(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    lena = make_person(db, "Lena")
    budget(db, admin, lena)
    lena.active = False
    db.commit()
    found = client.get("/api/apps/budget/people", headers=bearer(auth.issue_token(admin))).json()
    assert [p["name"] for p in found] == ["Admin"]


def test_people_from_outside(client, db, access):  # noqa: F811
    mama = make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    budget(db, mama)
    found = client.get("/api/apps/budget/people", headers=outside(token()))
    assert [p["name"] for p in found.json()] == ["Mama"]
    # Through the tunnel a hub token counts for nothing
    tunnel_bearer = {**THROUGH_TUNNEL, **bearer(auth.issue_token(mama))}
    assert client.get("/api/apps/budget/people", headers=tunnel_bearer).status_code == 401


def test_renamed_key(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    tile = budget(db, admin)
    tile.app_key = "money"
    db.commit()
    headers = bearer(auth.issue_token(admin))
    # The old key is gone; the people stay with the tile
    assert client.get("/api/apps/budget/people", headers=headers).status_code == 404
    assert [p["name"] for p in client.get("/api/apps/money/people", headers=headers).json()] == ["Admin"]
