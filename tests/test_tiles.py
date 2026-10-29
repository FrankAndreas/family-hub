"""The start page's tiles: at home every app with its home address, outside only those with an outside address."""

from test_cloudflare import access, outside, token  # noqa: F401

from helpers import add_person, login, make_person

BUDGET = {"name": "Budget", "icon": "💰", "local_url": "https://budget.local.example.ch", "remote_url": None}
MEALS = {
    "name": "Essen",
    "icon": "🍲",
    "local_url": "https://essen.local.example.ch",
    "remote_url": "https://essen.example.ch",
}


def add(client, tile):
    response = client.post("/api/tiles", json=tile)
    assert response.status_code == 201, response.text
    return response.json()


def test_home_shows_all_with_home_addresses(client):
    assert client.get("/api/tiles").status_code == 401
    login(client)
    budget, meals = add(client, BUDGET), add(client, MEALS)
    assert client.get("/api/tiles").json() == [
        {"id": budget["id"], "name": "Budget", "icon": "💰", "url": BUDGET["local_url"], "home_only": True},
        {"id": meals["id"], "name": "Essen", "icon": "🍲", "url": MEALS["local_url"], "home_only": False},
    ]


def test_outside_shows_only_outside_tiles(client, db, access):  # noqa: F811
    make_person(db, "Mama", role="PARENT", email="mama@example.ch")
    login(client)
    add(client, BUDGET)
    meals = add(client, MEALS)
    client.post("/api/logout")
    found = client.get("/api/tiles", headers=outside(token())).json()
    # The home-only app and every home address stay unknown outside
    assert found == [{"id": meals["id"], "name": "Essen", "icon": "🍲", "url": MEALS["remote_url"], "home_only": False}]


def test_parents_manage_tiles(client):
    login(client)
    budget, meals = add(client, BUDGET), add(client, MEALS)
    changed = client.patch(f"/api/tiles/{budget['id']}", json={"remote_url": "https://budget.example.ch"}).json()
    assert changed["remote_url"] == "https://budget.example.ch"
    assert client.put("/api/tiles/order", json=[meals["id"], budget["id"]]).status_code == 200
    assert [t["name"] for t in client.get("/api/tiles").json()] == ["Essen", "Budget"]
    assert [t["local_url"] for t in client.get("/api/tiles/manage").json()][0] == MEALS["local_url"]
    assert client.delete(f"/api/tiles/{budget['id']}").status_code == 200
    assert [t["name"] for t in client.get("/api/tiles").json()] == ["Essen"]
    add_person(client, "Lena")
    client.post("/api/logout")
    login(client, "Lena", "5678")
    assert client.post("/api/tiles", json=BUDGET).status_code == 403
    assert client.get("/api/tiles/manage").status_code == 403


def test_addresses_must_be_https(client):
    login(client)
    for bad in ("http://budget.local.example.ch", "javascript:alert(1)", "budget.local.example.ch"):
        assert client.post("/api/tiles", json={**BUDGET, "local_url": bad}).status_code == 422, bad
    # A development address on this machine
    add(client, {**BUDGET, "local_url": "http://localhost:5173"})
