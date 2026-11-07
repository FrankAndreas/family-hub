"""The browser tests' backend: the hub as on the NAS, but with cheap PIN hashes (as in the backend tests), so the many
logins don't each wait a quarter of a second for bcrypt. Never used outside the tests."""

import functools

import bcrypt
import uvicorn

bcrypt.gensalt = functools.partial(bcrypt.gensalt, rounds=4)

if __name__ == "__main__":
    # Started in backend/: the app is imported from there
    uvicorn.run("app.main:app", port=8110, app_dir=".")
