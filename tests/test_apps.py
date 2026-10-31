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
    found = client.get("/api/apps/budget/people", headers=bearer(auth.issue_tokens(admin)[0])).json()
    assert [p["name"] for p in found] == ["Admin", "Lena"]
    assert found[1] == {"id": lena.id, "name": "Lena", "role": "CHILD", "color": "#f59e0b", "language": "de"}
    assert client.get("/api/apps/budget/people", headers=bearer(auth.issue_tokens(max_)[0])).status_code == 403
    assert client.get("/api/apps/nope/people", headers=bearer(auth.issue_tokens(admin)[0])).status_code == 404
    assert client.get("/api/apps/budget/people").status_code == 401


def test_inactive_people_left_out(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    lena = make_person(db, "Lena")
    budget(db, admin, lena)
    lena.active = False
    db.commit()
    found = client.get("/api/apps/budget/people", headers=bearer(auth.issue_tokens(admin)[0])).json()
    assert [p["name"] for p in found] == ["Admin"]


def test_people_from_outside(client, db, access):  # noqa: F811
    mama = make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    budget(db, mama)
    found = client.get("/api/apps/budget/people", headers=outside(token()))
    assert [p["name"] for p in found.json()] == ["Mama"]
    # Through the tunnel a hub token counts for nothing
    tunnel_bearer = {**THROUGH_TUNNEL, **bearer(auth.issue_tokens(mama)[0])}
    assert client.get("/api/apps/budget/people", headers=tunnel_bearer).status_code == 401


def test_renamed_key(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    tile = budget(db, admin)
    tile.app_key = "money"
    db.commit()
    headers = bearer(auth.issue_tokens(admin)[0])
    # The old key is gone; the people stay with the tile
    assert client.get("/api/apps/budget/people", headers=headers).status_code == 404
    assert [p["name"] for p in client.get("/api/apps/money/people", headers=headers).json()] == ["Admin"]


# Apps that need the addresses (the job tracking app: reminders, telling one's own mails apart) get them when a parent
# switches it on for that app's tile; only confirmed ones (2026-10-30)
def test_email_addresses_only_for_apps_allowed_to(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    lena = make_person(db, "Lena", email="lena@example.org")
    max_ = make_person(db, "Max")
    max_.email_pending = "max@example.org"
    tile = budget(db, admin, lena, max_)
    headers = bearer(auth.issue_tokens(admin)[0])
    assert all("email" not in p for p in client.get("/api/apps/budget/people", headers=headers).json())
    tile.share_email = True
    db.commit()
    found = {p["name"]: p["email"] for p in client.get("/api/apps/budget/people", headers=headers).json()}
    assert found == {"Admin": None, "Lena": "lena@example.org", "Max": None}


def test_parents_switch_email_sharing_on_a_tile(client):
    from helpers import login

    login(client)
    body = {"name": "Bewerbungen", "local_url": "https://job.local.example.ch", "app_key": "jobs"}
    tile = client.post("/api/tiles", json=body).json()
    assert tile["share_email"] is False
    assert client.patch(f"/api/tiles/{tile['id']}", json={"share_email": True}).json()["share_email"] is True


# hub#12: a tile may name its app's Cloudflare Access application (its AUD tag). Then a Cloudflare login counts for that
# app only when Cloudflare made it for that application: one leaked from another family app, or the hub, gets nowhere
MEALS_AUD = "a" * 64


def test_an_apps_own_audience_only(client, db, access):  # noqa: F811
    mama = make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    tile = budget(db, mama)
    tile.cf_audience = MEALS_AUD
    db.commit()
    for headers in ({}, THROUGH_TUNNEL):
        own = {**headers, "Cf-Access-Jwt-Assertion": token(aud=MEALS_AUD)}
        other = {**headers, "Cf-Access-Jwt-Assertion": token()}
        assert client.get("/api/session?app=budget", headers=own).json()["access"] is True
        assert client.get("/api/session?app=budget", headers=other).json()["valid"] is False
        assert client.get("/api/apps/budget/people", headers=own).status_code == 200
        assert client.get("/api/apps/budget/people", headers=other).status_code == 401
    # Without the app, or for an app whose tile names no application, every family application counts as before
    assert client.get("/api/session", headers={"Cf-Access-Jwt-Assertion": token()}).json()["valid"] is True
    tile.cf_audience = None
    db.commit()
    assert client.get("/api/session?app=budget", headers=outside(token())).json()["access"] is True
    # The hub's own login is unaffected
    assert client.get("/api/session?app=budget", headers=bearer(auth.issue_tokens(mama)[0])).json()["access"] is True


def test_parents_set_a_tiles_cloudflare_application(client):
    from helpers import login

    login(client)
    body = {"name": "Essen", "local_url": "https://essen.local.example.ch", "app_key": "meals"}
    tile = client.post("/api/tiles", json=body).json()
    assert tile["cf_audience"] is None
    assert client.patch(f"/api/tiles/{tile['id']}", json={"cf_audience": MEALS_AUD}).json()["cf_audience"] == MEALS_AUD
    # Cloudflare's tags are 64 hex characters; anything else is a typo
    assert client.patch(f"/api/tiles/{tile['id']}", json={"cf_audience": "essen"}).status_code == 422
    assert client.patch(f"/api/tiles/{tile['id']}", json={"cf_audience": None}).json()["cf_audience"] is None
