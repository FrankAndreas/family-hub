"""Parents change only themselves and the children (spec 2026-10-30 hub hardening, part 2). Invented people."""

import threading
import time

from fastapi.testclient import TestClient
from helpers import APP_HEADER, add_person, login

from app import people_api
from app.main import app


def own_id(client) -> int:
    return client.get("/api/me").json()["id"]


def test_parent_cant_change_another_parent(client):
    login(client)
    mia = add_person(client, "Mia", role="PARENT")
    refused = client.patch(f"/api/people/{mia['id']}", json={"color": "#000000"})
    assert refused.status_code == 403 and refused.json()["detail"] == "other_parent"
    assert client.put(f"/api/people/{mia['id']}/pin", json={"pin": "9999"}).status_code == 403
    assert client.patch(f"/api/people/{mia['id']}", json={"active": False}).status_code == 403


def test_parent_still_manages_children(client):
    login(client)
    lena = add_person(client, "Lena")
    assert client.patch(f"/api/people/{lena['id']}", json={"name": "Lea"}).status_code == 200
    assert client.put(f"/api/people/{lena['id']}/pin", json={"pin": "2468"}).status_code == 200


def test_parent_changes_themselves(client):
    login(client)
    assert client.patch(f"/api/people/{own_id(client)}", json={"color": "#123456"}).status_code == 200


def test_own_email_needs_pin(client):
    login(client)
    me = own_id(client)
    missing = client.patch(f"/api/people/{me}", json={"email": "admin@example.org"})
    assert missing.status_code == 400 and missing.json()["detail"] == "pin_needed"
    wrong = client.patch(f"/api/people/{me}", json={"email": "admin@example.org", "current_pin": "0000"})
    assert wrong.status_code == 401 and wrong.json()["detail"] == "wrong_pin"
    right = client.patch(f"/api/people/{me}", json={"email": "admin@example.org", "current_pin": "1234"})
    assert right.status_code == 200 and right.json()["email"] == "admin@example.org"
    lena = add_person(client, "Lena")
    assert client.patch(f"/api/people/{lena['id']}", json={"email": "lena@example.org"}).status_code == 200


def test_last_parent_check_holds_in_parallel(client, monkeypatch):
    login(client)
    add_person(client, "Mia", pin="5678", role="PARENT")
    mia = TestClient(app, headers=APP_HEADER)
    login(mia, "Mia", "5678")
    real = people_api._check_last_parent

    def slow(*args):
        real(*args)
        # Both would pass the check before either one is saved
        time.sleep(0.2)

    monkeypatch.setattr(people_api, "_check_last_parent", slow)
    codes: list[int] = []

    def become_child(who):
        codes.append(who.patch(f"/api/people/{own_id(who)}", json={"role": "CHILD"}).status_code)

    threads = [threading.Thread(target=become_child, args=(who,)) for who in (client, mia)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(codes) == [200, 400]


def test_own_pin_only_with_the_old_one(client):
    # A browser left logged in must not be enough to set a parent's own PIN: that goes through /me/pin
    login(client)
    refused = client.put(f"/api/people/{own_id(client)}/pin", json={"pin": "9999"})
    assert refused.status_code == 403 and refused.json()["detail"] == "own_pin_needs_old_pin"


# Security review 2026-10-30, finding 1: through the tiles one parent could cut the other off an app or replace it
def _shared_tile(client, mia_id):
    admin_id = own_id(client)
    body = {"name": "Budget", "local_url": "https://budget.local.example.ch", "app_key": "budget"}
    tile = client.post("/api/tiles", json={**body, "people": [admin_id, mia_id]}).json()
    return tile, admin_id


def test_a_parent_cant_take_an_app_from_another(client):
    login(client)
    mia = add_person(client, "Mia", role="PARENT")
    lena = add_person(client, "Lena")
    tile, admin_id = _shared_tile(client, mia["id"])
    removed = client.patch(f"/api/tiles/{tile['id']}", json={"people": [admin_id]})
    assert removed.status_code == 403 and removed.json()["detail"] == "other_parent"
    assert client.patch(f"/api/tiles/{tile['id']}", json={"app_key": "other"}).status_code == 403
    assert client.delete(f"/api/tiles/{tile['id']}").status_code == 403
    # Children and oneself: as before
    added = client.patch(f"/api/tiles/{tile['id']}", json={"people": [admin_id, mia["id"], lena["id"]]})
    assert added.status_code == 200
    assert client.patch(f"/api/tiles/{tile['id']}", json={"people": [mia["id"]]}).status_code == 200
