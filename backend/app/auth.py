"""PINs (Task 2 adds the login)."""

import bcrypt


def get_pin_hash(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def name_key(name: str) -> str:
    """What makes two names the same person's: case and surrounding spaces don't count."""
    return name.strip().casefold()
