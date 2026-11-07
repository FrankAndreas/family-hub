"""When each person last used an app, and what that locks: a parent can't take an app away from another parent who
used it (security review 2026-10-30, finding 1). Invented people."""

from fastapi.testclient import TestClient
from helpers import own_id, APP_HEADER, add_person, login

from app.main import app


# Security review 2026-10-30, finding 1: through the tiles one parent could cut the other off an app or replace it
def _shared_tile(client, mia_id):
    admin_id = own_id(client)
    body = {"name": "Budget", "local_url": "https://budget.local.example.ch", "app_key": "budget"}
    tile = client.post("/api/tiles", json={**body, "people": [admin_id, mia_id]}).json()
    return tile, admin_id


def _mia_uses(client, mia, key="budget"):
    """Mia opens the app: it asks the hub with her login."""
    mia_client = TestClient(app, headers=APP_HEADER)
    login(mia_client, mia["name"], "2468")
    assert mia_client.get(f"/api/session?app={key}").json()["access"] is True
    return mia_client


def test_a_parent_cant_take_an_app_from_another(client):
    login(client)
    mia = add_person(client, "Mia", role="PARENT", pin="2468")
    lena = add_person(client, "Lena")
    tile, admin_id = _shared_tile(client, mia["id"])
    _mia_uses(client, mia)
    removed = client.patch(f"/api/tiles/{tile['id']}", json={"people": [admin_id]})
    assert removed.status_code == 403 and removed.json()["detail"] == "tile_other_parent"
    moved = client.patch(f"/api/tiles/{tile['id']}", json={"app_key": "other"})
    assert moved.status_code == 403 and moved.json()["detail"] == "tile_key_in_use"
    deleted = client.delete(f"/api/tiles/{tile['id']}")
    assert deleted.status_code == 403 and deleted.json()["detail"] == "tile_other_parent"
    # Children and oneself: as before
    added = client.patch(f"/api/tiles/{tile['id']}", json={"people": [admin_id, mia["id"], lena["id"]]})
    assert added.status_code == 200
    assert client.patch(f"/api/tiles/{tile['id']}", json={"people": [mia["id"]]}).status_code == 200


def test_a_parent_who_never_used_the_app_can_be_removed(client):
    # Unticking someone who never opened the app, deleting it or correcting its key takes nothing from them
    login(client)
    mia = add_person(client, "Mia", role="PARENT", pin="2468")
    tile, admin_id = _shared_tile(client, mia["id"])
    client.get("/api/session?app=budget")  # only the admin uses it
    fixed = client.patch(f"/api/tiles/{tile['id']}", json={"app_key": "planner"})
    assert fixed.status_code == 200 and fixed.json()["app_key"] == "planner"
    assert client.patch(f"/api/tiles/{tile['id']}", json={"people": [admin_id]}).status_code == 200
    other, _ = _shared_tile(client, mia["id"])
    assert client.delete(f"/api/tiles/{other['id']}").status_code == 200


def test_last_used_per_person(client):
    login(client)
    mia = add_person(client, "Mia", role="PARENT", pin="2468")
    tile, admin_id = _shared_tile(client, mia["id"])
    assert client.get("/api/tiles/manage").json()[0]["usage"] == []
    _mia_uses(client, mia)
    usage = client.get("/api/tiles/manage").json()[0]["usage"]
    assert [u["person_id"] for u in usage] == [mia["id"]]
    assert usage[0]["last_used_at"].endswith("Z") and usage[0]["first_used_at"] == usage[0]["last_used_at"]


def test_last_used_is_refreshed_at_most_hourly(client, monkeypatch):
    from datetime import datetime

    from app import timeutil

    login(client)
    _shared_tile(client, own_id(client))
    now = datetime(2026, 11, 6, 8, 0)
    monkeypatch.setattr(timeutil, "utcnow", lambda: now)
    client.get("/api/session?app=budget")
    now = datetime(2026, 11, 6, 8, 30)
    client.get("/api/session?app=budget")
    assert client.get("/api/tiles/manage").json()[0]["usage"][0]["last_used_at"] == "2026-11-06T08:00:00Z"
    now = datetime(2026, 11, 6, 9, 30)
    client.get("/api/apps/budget/people")
    usage = client.get("/api/tiles/manage").json()[0]["usage"][0]
    assert (usage["first_used_at"], usage["last_used_at"]) == ("2026-11-06T08:00:00Z", "2026-11-06T09:30:00Z")


def test_only_logins_with_access_count(client):
    login(client)
    mia = add_person(client, "Mia", role="PARENT", pin="2468")
    body = {"name": "Budget", "local_url": "https://budget.local.example.ch", "app_key": "budget"}
    client.post("/api/tiles", json=body)
    TestClient(app).get("/api/session?app=budget")
    mia_client = TestClient(app, headers=APP_HEADER)
    login(mia_client, mia["name"], "2468")
    assert mia_client.get("/api/session?app=budget").json()["access"] is False
    assert client.get("/api/tiles/manage").json()[0]["usage"] == []


def test_new_key_or_untick_forgets_the_use(client):
    login(client)
    mia = add_person(client, "Mia", role="PARENT", pin="2468")
    tile, admin_id = _shared_tile(client, mia["id"])
    client.get("/api/session?app=budget")
    assert client.patch(f"/api/tiles/{tile['id']}", json={"app_key": "money"}).json()["usage"] == []
    client.get("/api/session?app=money")
    client.patch(f"/api/tiles/{tile['id']}", json={"people": [mia["id"]]})
    assert client.patch(f"/api/tiles/{tile['id']}", json={"people": [admin_id, mia["id"]]}).json()["usage"] == []


# The settings page shows the rules without knowing them (#25): the backend says what the parent asking can't change
def test_the_answer_says_what_is_locked(client):
    login(client)
    mia = add_person(client, "Mia", role="PARENT", pin="2468")
    kid = add_person(client, "Kid", pin="1357")
    tile, admin_id = _shared_tile(client, mia["id"])
    assert client.get("/api/tiles/manage").json()[0]["locked_people"] == []
    mia_client = _mia_uses(client, mia)
    assert client.get("/api/tiles/manage").json()[0]["locked_people"] == [mia["id"]]
    renamed = client.patch(f"/api/tiles/{tile['id']}", json={"name": "Geld"}).json()
    assert renamed["locked_people"] == [mia["id"]]
    # Mia herself may untick herself: nothing is locked for her
    assert mia_client.get("/api/tiles/manage").json()[0]["locked_people"] == []
    can_edit = {p["id"]: p["can_edit"] for p in client.get("/api/people").json()}
    assert (can_edit[admin_id], can_edit[kid["id"]], can_edit[mia["id"]]) == (True, True, False)
