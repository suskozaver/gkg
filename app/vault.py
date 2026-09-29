"""
Encryption at rest for the Keep master token and the cached notes.

The key is GKG_DATA_KEY from .env (a Fernet key: 32 random bytes, url-safe
base64). It is never in the data folder, so the volume or a backup of it is
useless without .env. The server itself can decrypt, and has to: it syncs
with Keep on its own.

Make a key:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import gzip
import json

from cryptography.fernet import Fernet, InvalidToken


class VaultError(Exception):
    pass


class Vault:
    def __init__(self, key: str | None):
        self._f = None
        if key:
            try:
                self._f = Fernet(key.strip().encode())
            except (ValueError, TypeError) as e:
                raise VaultError("GKG_DATA_KEY is not a valid Fernet key.") from e

    @property
    def ready(self) -> bool:
        return self._f is not None

    def _need(self) -> Fernet:
        if self._f is None:
            raise VaultError("GKG_DATA_KEY is not set, so nothing can be stored encrypted.")
        return self._f

    def seal(self, text: str) -> str:
        return self._need().encrypt(text.encode("utf-8")).decode()

    def open(self, token: str) -> str:
        try:
            return self._need().decrypt(token.encode()).decode("utf-8")
        except InvalidToken as e:
            raise VaultError("Cannot decrypt: GKG_DATA_KEY is not the key this was sealed with.") from e

    def seal_json(self, value) -> bytes:
        return self._need().encrypt(gzip.compress(json.dumps(value, separators=(",", ":")).encode()))

    def open_json(self, data: bytes):
        try:
            return json.loads(gzip.decompress(self._need().decrypt(data)))
        except InvalidToken as e:
            raise VaultError("Cannot decrypt: GKG_DATA_KEY is not the key this was sealed with.") from e
