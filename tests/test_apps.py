"""Apps pull their people from the hub: everyone with access to the app (spec 2026-10-30, part A)."""

from helpers import THROUGH_TUNNEL, bearer, budget_tile, make_person, outside, token

from app import auth, models


def test_people_of_an_app(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    lena = make_person(db, "Lena", color="#f59e0b")
    max_ = make_person(db, "Max")
    budget_tile(db, lena, admin)
    found = client.get("/api/apps/budget/people", headers=bearer(auth.issue_tokens(admin)[0])).json()
    assert [p["name"] for p in found] == ["Admin", "Lena"]
    assert found[1] == {"id": lena.id, "name": "Lena", "role": "CHILD", "color": "#f59e0b", "language": "de"}
    assert client.get("/api/apps/budget/people", headers=bearer(auth.issue_tokens(max_)[0])).status_code == 403
    assert client.get("/api/apps/nope/people", headers=bearer(auth.issue_tokens(admin)[0])).status_code == 404
    assert client.get("/api/apps/budget/people").status_code == 401


def test_inactive_people_left_out(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    lena = make_person(db, "Lena")
    budget_tile(db, admin, lena)
    lena.active = False
    db.commit()
    found = client.get("/api/apps/budget/people", headers=bearer(auth.issue_tokens(admin)[0])).json()
    assert [p["name"] for p in found] == ["Admin"]


def test_people_from_outside(client, db, access):
    mama = make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    budget_tile(db, mama)
    found = client.get("/api/apps/budget/people", headers=outside(token()))
    assert [p["name"] for p in found.json()] == ["Mama"]
    # Through the tunnel a hub token counts for nothing
    tunnel_bearer = {**THROUGH_TUNNEL, **bearer(auth.issue_tokens(mama)[0])}
    assert client.get("/api/apps/budget/people", headers=tunnel_bearer).status_code == 401


def test_renamed_key(client, db):
    admin = db.query(models.Person).filter_by(name="Admin").one()
    tile = budget_tile(db, admin)
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
    tile = budget_tile(db, admin, lena, max_)
    headers = bearer(auth.issue_tokens(admin)[0])
    assert all("email" not in p for p in client.get("/api/apps/budget/people", headers=headers).json())
    tile.share_email = True
    db.commit()
    found = {p["name"]: p["email"] for p in client.get("/api/apps/budget/people", headers=headers).json()}
    assert found == {"Admin": None, "Lena": "lena@example.org", "Max": None}


# hub#12: a tile may name its app's Cloudflare Access application (its AUD tag). Then a Cloudflare login counts for that
# app only when Cloudflare made it for that application: one leaked from another family app, or the hub, gets nowhere
MEALS_AUD = "a" * 64


def test_an_apps_own_audience_only(client, db, access):
    mama = make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    tile = budget_tile(db, mama)
    tile.cf_audience = MEALS_AUD
    db.commit()
    own, other = outside(token(aud=MEALS_AUD)), outside(token())
    assert client.get("/api/session?app=budget", headers=own).json()["access"] is True
    assert client.get("/api/session?app=budget", headers=other).json()["valid"] is False
    assert client.get("/api/apps/budget/people", headers=own).status_code == 200
    assert client.get("/api/apps/budget/people", headers=other).status_code == 401
    # Without the app, or for an app whose tile names no application, every family application counts as before
    assert client.get("/api/session", headers=outside(token())).json()["valid"] is True
    tile.cf_audience = None
    db.commit()
    assert client.get("/api/session?app=budget", headers=outside(token())).json()["access"] is True
    # The hub's own login is unaffected
    assert client.get("/api/session?app=budget", headers=bearer(auth.issue_tokens(mama)[0])).json()["access"] is True


# The apps' contract is in the OpenAPI document (#25), so it can't drift from the code unnoticed
def test_the_apps_contract_is_documented(client):
    paths = client.get("/openapi.json").json()["paths"]

    def answer(path):
        return paths[path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert answer("/api/session")["$ref"].endswith("/SessionOut")
    assert answer("/api/apps/{key}/people")["items"]["$ref"].endswith("/AppPerson")
    assert answer("/api/tiles")["items"]["$ref"].endswith("/TileLink")
