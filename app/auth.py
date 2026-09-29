"""
The one account (the owner) and its sessions, the Eat Train Feel way:

- No sign-up. On first start, with no owner yet, the server prints a setup
  link with a token that changes on every restart and is spent once the
  owner exists (`/setup?token=…`).
- The password is kept as scrypt (N=2^15, r=8, p=1) with its own salt.
- A session is a cookie signed with HMAC-SHA256 under GKG_SESSION_SECRET:
  who, until when, and the owner's `epoch`. Changing the password raises the
  epoch, which signs out every browser at once.

`owner.json`: { username, salt, hash, epoch, createdAt }
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time

SESSION_DAYS = 30
COOKIE = "gkg_session"
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
MIN_PASSWORD = 10


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=64).hex()


def make_owner(username: str, password: str) -> dict:
    u = (username or "").strip().lower()
    if not USERNAME.match(u):
        raise ValueError("Username: 2 to 32 lowercase letters, digits, dot, dash or underscore.")
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"Password: at least {MIN_PASSWORD} characters.")
    salt = secrets.token_bytes(16)
    return {"username": u, "salt": salt.hex(), "hash": hash_password(password, salt), "epoch": 1, "createdAt": int(time.time())}


def check_password(owner: dict | None, username: str, password: str) -> bool:
    if not owner:
        # Same work either way, so the answer's timing says nothing.
        hash_password(password or "", b"0" * 16)
        return False
    good = hash_password(password or "", bytes.fromhex(owner["salt"]))
    return hmac.compare_digest(good, owner["hash"]) and (username or "").strip().lower() == owner["username"]


def change_password(owner: dict, password: str) -> dict:
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"Password: at least {MIN_PASSWORD} characters.")
    salt = secrets.token_bytes(16)
    return {**owner, "salt": salt.hex(), "hash": hash_password(password, salt), "epoch": int(owner.get("epoch", 1)) + 1}


def _sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def issue_session(secret: str, owner: dict, now: float | None = None) -> str:
    now = time.time() if now is None else now
    body = base64.urlsafe_b64encode(
        json.dumps({"u": owner["username"], "e": owner.get("epoch", 1), "x": int(now + SESSION_DAYS * 86400)}).encode()
    ).rstrip(b"=").decode()
    return f"{body}.{_sign(secret, body)}"


def read_session(secret: str, owner: dict | None, value: str | None, now: float | None = None) -> str | None:
    """The username of a valid session, or None."""
    if not value or not owner or "." not in value:
        return None
    body, sig = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(secret, body), sig):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, TypeError):
        return None
    now = time.time() if now is None else now
    if data.get("x", 0) < now or data.get("u") != owner["username"] or data.get("e") != owner.get("epoch", 1):
        return None
    return owner["username"]
