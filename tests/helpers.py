"""Invented people only: the repository is public."""

ADMIN = "Admin"
ADMIN_PIN = "1234"
# Cloudflare sets this on every request that comes through the tunnel; the DSM reverse proxy at home doesn't
THROUGH_TUNNEL = {"Cf-Connecting-Ip": "203.0.113.7"}


def login(client, name=ADMIN, pin=ADMIN_PIN):
    """Log in at home: the client keeps the login cookie."""
    response = client.post("/api/login", json={"name": name, "pin": pin})
    assert response.status_code == 200, response.text
    return response


def add_person(client, name, pin="5678", role="CHILD", email=None, **fields) -> dict:
    body = {"name": name, "pin": pin, "role": role, "email": email, **fields}
    response = client.post("/api/people", json=body)
    assert response.status_code == 201, response.text
    return response.json()
