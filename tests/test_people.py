"""Parents manage the family's people in one place: names, e-mail addresses, PINs, roles; each parent only themselves
and the children. Invented people. A comment above a test names the review it came from, if any."""

import threading
import time

from fastapi.testclient import TestClient
from helpers import own_id, APP_HEADER, add_person, budget_tile, login

from app import links, models, people_api, pin_reset
from app.main import app


def test_parents_add_and_list(client):
    login(client)
    lena = add_person(client, "Lena", email="Lena@Example.ch", color="#f59e0b")
    # The address counts once confirmed (security review 2026-10-30); until then it waits
    assert (lena["email_pending"], lena["role"], lena["active"], lena["color"]) == (
        "lena@example.ch",
        "CHILD",
        True,
        "#f59e0b",
    )
    assert lena["email"] is None
    assert [p["name"] for p in client.get("/api/people").json()] == ["Admin", "Lena"]
    # Lena can log in with her PIN, but can't manage people
    client.post("/api/logout")
    login(client, "Lena", "5678")
    assert client.get("/api/people").status_code == 403
    assert client.post("/api/people", json={"name": "Tim", "pin": "1111", "role": "CHILD"}).status_code == 403


def test_unique_names_and_emails(client, db):
    login(client)
    lena = add_person(client, "Lena", email="lena@example.ch")
    # Confirmed (security review 2026-10-30): from now on the address is Lena's
    person = db.get(models.Person, lena["id"])
    person.email, person.email_pending = person.email_pending, None
    db.commit()
    taken = client.post("/api/people", json={"name": " lena ", "pin": "1111", "role": "CHILD"})
    assert taken.status_code == 409 and taken.json()["detail"] == "name_taken"
    taken = client.post("/api/people", json={"name": "Tim", "pin": "1111", "role": "CHILD", "email": "LENA@example.ch"})
    assert taken.status_code == 409 and taken.json()["detail"] == "email_taken"
    for bad in ({"pin": "12"}, {"email": "no-at-sign"}, {"color": "red"}, {"name": ""}):
        body = {"name": "Tim", "pin": "1111", "role": "CHILD", **bad}
        assert client.post("/api/people", json=body).status_code == 422, bad


def test_edit_and_deactivate(client):
    login(client)
    lena = add_person(client, "Lena")
    changed = client.patch(f"/api/people/{lena['id']}", json={"name": "Lena M.", "email": "lena@example.ch"}).json()
    assert (changed["name"], changed["email_pending"]) == ("Lena M.", "lena@example.ch")
    client.patch(f"/api/people/{lena['id']}", json={"email": None})
    assert client.get("/api/people").json()[1]["email"] is None
    assert client.patch(f"/api/people/{lena['id']}", json={"active": False}).json()["active"] is False
    assert client.post("/api/login", json={"name": "Lena M.", "pin": "5678"}).status_code == 401


def test_last_parent_is_kept(client):
    login(client)
    admin = client.get("/api/me").json()
    for change in ({"role": "CHILD"}, {"active": False}):
        response = client.patch(f"/api/people/{admin['id']}", json=change)
        assert response.status_code == 400 and response.json()["detail"] == "last_parent", change
    # With a second parent it's allowed
    add_person(client, "Mama", role="PARENT")
    assert client.patch(f"/api/people/{admin['id']}", json={"active": False}).status_code == 200


def test_pins(client):
    login(client)
    lena = add_person(client, "Lena")
    # A parent sets anyone's PIN; it ends that person's logins and lifts a lock
    assert client.put(f"/api/people/{lena['id']}/pin", json={"pin": "2468"}).status_code == 200
    client.post("/api/logout")
    login(client, "Lena", "2468")
    # Everyone changes their own with the old one
    assert client.put("/api/me/pin", json={"old_pin": "0000", "pin": "1357"}).status_code == 401
    assert client.put("/api/me/pin", json={"old_pin": "2468", "pin": "1357"}).status_code == 200
    # Changing the own PIN keeps this device logged in
    assert client.get("/api/me").status_code == 200
    client.post("/api/logout")
    login(client, "Lena", "1357")


def test_own_language_and_colour(client):
    login(client)
    me = client.patch("/api/me", json={"language": "en", "color": "#10b981"}).json()
    assert (me["language"], me["language_chosen"], me["color"]) == ("en", True, "#10b981")


# Each parent changes only themselves and the children (hub hardening, spec 2026-10-30, part 2)


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


def test_own_pin_only_with_the_old_one(client):
    # A browser left logged in must not be enough to set a parent's own PIN: that goes through /me/pin
    login(client)
    refused = client.put(f"/api/people/{own_id(client)}/pin", json={"pin": "9999"})
    assert refused.status_code == 403 and refused.json()["detail"] == "own_pin_needs_old_pin"


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


# Privacy review 2026-11-07: someone who left the family for good can be removed, with everything the hub kept about
# them; their name and address are free again. Only once inactive, and never another parent
def test_delete_someone_who_left(client, db):
    login(client)
    lena = add_person(client, "Lena", email="lena@example.ch")
    person = db.get(models.Person, lena["id"])
    person.email, person.email_pending = person.email_pending, None
    tile = budget_tile(db, person)
    db.commit()
    login(client, "Lena", "5678")
    links.create(db, pin_reset.KIND, person)
    db.commit()
    login(client)

    refused = client.delete(f"/api/people/{lena['id']}")
    assert refused.status_code == 409 and refused.json()["detail"] == "person_active"
    client.patch(f"/api/people/{lena['id']}", json={"active": False})
    assert client.delete(f"/api/people/{lena['id']}").json() == {"deleted": lena["id"]}

    db.expire_all()
    assert db.get(models.Person, lena["id"]) is None
    for table in (models.KnownDevice, models.PinReset, models.EmailConfirm):
        assert db.query(table).filter_by(person_id=lena["id"]).count() == 0, table
    assert db.get(models.Tile, tile.id).people == []
    assert [p["name"] for p in client.get("/api/people").json()] == ["Admin"]
    # A new Lena is someone else to the apps: a deleted person's id never comes back (AUTOINCREMENT)
    assert add_person(client, "Lena", email="lena@example.ch")["id"] > lena["id"]
    assert client.delete(f"/api/people/{lena['id']}").status_code == 404


def test_delete_only_who_one_may_change(client):
    login(client)
    mia = add_person(client, "Mia", role="PARENT")
    refused = client.delete(f"/api/people/{mia['id']}")
    assert refused.status_code == 403 and refused.json()["detail"] == "other_parent"
    tim = add_person(client, "Tim")
    client.patch(f"/api/people/{tim['id']}", json={"active": False})
    client.post("/api/logout")
    login(client, "Mia", "5678")
    # Mia manages the children too; a child manages no one
    add_person(client, "Ben")
    client.post("/api/logout")
    login(client, "Ben", "5678")
    assert client.delete(f"/api/people/{tim['id']}").status_code == 403
