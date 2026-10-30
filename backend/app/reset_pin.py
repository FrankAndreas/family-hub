"""The last resort for a forgotten PIN, on the NAS: prints a reset link (30 minutes, once), also without the mail
settings and for people without an e-mail address.

    docker exec hub-backend python -m app.reset_pin <name>
"""

import sys

from . import auth, database, models, pin_reset


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: python -m app.reset_pin <name>", file=sys.stderr)
        return 2
    with database.SessionLocal() as db:
        person = db.query(models.Person).filter(models.Person.name_key == auth.name_key(argv[0])).first()
        if person is None or not person.active:
            print(f"No active person named {argv[0]!r}", file=sys.stderr)
            return 1
        name = person.name
        link = pin_reset.create_link(db, person)
    print(f"Reset link for {name}, valid for 30 minutes, at home only:\n{link}")
    if link.startswith("/"):
        print("(HUB_PUBLIC_URL is not set: open this path on the hub's address, e.g. https://home.local.<domain>)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
