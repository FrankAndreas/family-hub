"""The key that signs the logins: Ed25519, made on first start and kept in DATA_DIR (it survives updates, and with it
every login). Apps check logins with its public half (the JWKS at /api/keys), so no secret is shared with them."""

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import config

FILE = "signing-key.pem"
_loaded: dict[Path, tuple[Ed25519PrivateKey, str]] = {}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _raw_public(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def signing_key() -> tuple[Ed25519PrivateKey, str]:
    """The private key and its id (kid: the public key's SHA-256, so a new key gets a new id)."""
    path = config.data_dir() / FILE
    if path not in _loaded:
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            assert isinstance(key, Ed25519PrivateKey)
        else:
            key = Ed25519PrivateKey.generate()
            path.parent.mkdir(parents=True, exist_ok=True)
            pem = key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
            # Only the backend's user may read it
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as file:
                file.write(pem)
        kid = _b64(hashlib.sha256(_raw_public(key.public_key())).digest())[:16]
        _loaded[path] = (key, kid)
    return _loaded[path]


def jwks() -> dict:
    """The public key as a JSON Web Key Set (RFC 8037: OKP, Ed25519)."""
    key, kid = signing_key()
    jwk = {"kty": "OKP", "crv": "Ed25519", "x": _b64(_raw_public(key.public_key())), "kid": kid}
    return {"keys": [{**jwk, "alg": "EdDSA", "use": "sig"}]}
