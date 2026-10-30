"""Parents manage the family's people in one place: names, e-mail addresses, PINs, roles. Invented people only."""

from helpers import THROUGH_TUNNEL, add_person, login


def test_parents_add_and_list(client):
    login(client)
    lena = add_person(client, "Lena", email="Lena@Example.ch", color="#f59e0b")
    assert (lena["email"], lena["role"], lena["active"], lena["color"]) == ("lena@example.ch", "CHILD", True, "#f59e0b")
    assert [p["name"] for p in client.get("/api/people").json()] == ["Admin", "Lena"]
    # Lena can log in with her PIN, but can't manage people
    client.post("/api/logout")
    login(client, "Lena", "5678")
    assert client.get("/api/people").status_code == 403
    assert client.post("/api/people", json={"name": "Tim", "pin": "1111", "role": "CHILD"}).status_code == 403


def test_unique_names_and_emails(client):
    login(client)
    add_person(client, "Lena", email="lena@example.ch")
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
    assert (changed["name"], changed["email"]) == ("Lena M.", "lena@example.ch")
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


def test_managing_people_from_outside_needs_cloudflare(client):
    login(client)
    assert client.get("/api/people", headers=THROUGH_TUNNEL).status_code == 401
