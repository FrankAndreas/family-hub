"""The last resort to confirm a person's new e-mail address, on the NAS: prints the confirmation link (24 hours, once),
also without the mail settings.

    docker exec hub-backend python -m app.confirm_email <name>
"""

import sys

from . import addresses, auth, database, models


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: python -m app.confirm_email <name>", file=sys.stderr)
        return 2
    with database.SessionLocal() as db:
        person = db.query(models.Person).filter(models.Person.name_key == auth.name_key(argv[0])).first()
        if person is None or not person.active or not person.email_pending:
            print(f"No active person named {argv[0]!r} with an address waiting for confirmation", file=sys.stderr)
            return 1
        name = person.name
        link = addresses.create_link(db, person)
    print(f"Confirmation link for {name}'s new e-mail address, valid for 24 hours, at home only:\n{link}")
    if link.startswith("/"):
        print("(HUB_PUBLIC_URL is not set: open this path on the hub's address, e.g. https://home.local.<domain>)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
