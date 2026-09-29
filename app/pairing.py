"""
Linking a watch: the device-code kind a TV uses (ported from Eat Train Feel's
server/watch.mjs).

The watch asks for a pairing: a 6-digit code it shows for three minutes, and a
secret it keeps. The owner types the code on the web, signed in, which binds
the pairing; the watch, asking with its secret every few seconds, is then
handed a token of its own, once, and never needs the code again. Pairings
live in memory (the caller's dict): a restart costs a new code, nothing more.

The file (`watches.json`) keeps only a hash of each token:

    { "watches": [{ "id", "name"?, "tokenHash", "linkedAt", "lastSeenAt" }] }

Times are milliseconds. No I/O here: plain data in, plain data out, tested in
tests/test_pairing.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

CODE_MS = 3 * 60_000
MAX_WATCHES = 5
MAX_PAIRINGS = 50
# A watch not heard from for this long is unlinked by itself: lost, sold, forgotten.
IDLE_MS = 90 * 24 * 3600_000
# Wrong codes: this many in a day locks linking for a day.
FAIL_MAX = 5
FAIL_WINDOW_MS = 24 * 3600_000
LOCK_MS = 24 * 3600_000
# Wrong codes from everyone together, per hour: past this, linking pauses.
GLOBAL_FAIL_MAX = 100
GLOBAL_WINDOW_MS = 3600_000
MAX_WATCH_NAME = 30


def hash_token(s: str) -> str:
    return hashlib.sha256(str(s).encode()).hexdigest()


def _same(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(str(a), str(b))


def _b64(n: int) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(n)).rstrip(b"=").decode()


def normalize(raw) -> dict:
    watches = []
    if isinstance(raw, dict) and isinstance(raw.get("watches"), list):
        for w in raw["watches"]:
            if not isinstance(w, dict) or not isinstance(w.get("id"), str) or not isinstance(w.get("tokenHash"), str):
                continue
            clean = {
                "id": w["id"],
                "tokenHash": w["tokenHash"],
                "linkedAt": int(w.get("linkedAt") or 0),
                "lastSeenAt": int(w.get("lastSeenAt") or 0),
            }
            if isinstance(w.get("name"), str) and w["name"]:
                clean["name"] = w["name"][:MAX_WATCH_NAME]
            watches.append(clean)
    return {"watches": watches}


# ── Pairing ────────────────────────────────────────────────────────────────

def sweep(pairings: dict, now: int) -> None:
    for code in [c for c, p in pairings.items() if p["expiresAt"] <= now and not p["token"]]:
        del pairings[code]
    # A linked pairing the watch never came back for goes too, a little later.
    for code in [c for c, p in pairings.items() if p["expiresAt"] + CODE_MS <= now]:
        del pairings[code]


def new_pairing(pairings: dict, now: int) -> dict | None:
    """A fresh pairing for a watch that asked, or None when too many are waiting."""
    sweep(pairings, now)
    if len(pairings) >= MAX_PAIRINGS:
        return None
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        if code not in pairings:
            break
    secret = _b64(24)
    pairings[code] = {"secretHash": hash_token(secret), "expiresAt": now + CODE_MS, "token": None, "watchId": None, "user": None}
    return {"code": code, "secret": secret, "expiresIn": CODE_MS // 1000}


def claim(pairings: dict, raw, *, code: str, user: str, now: int) -> dict:
    """The owner typed a code. The watch gets its token on its next question;
    the file gets the watch now, with only a hash of that token."""
    sweep(pairings, now)
    c = re.sub(r"\D", "", str(code or ""))
    p = pairings.get(c)
    if not p or p["token"] or p["expiresAt"] <= now:
        return {"error": "That code does not match a watch. Check it, or get a new one on the watch."}
    file = normalize(raw)
    watch_id = secrets.token_hex(6)
    token = _b64(32)
    watches = sorted(
        file["watches"] + [{"id": watch_id, "tokenHash": hash_token(token), "linkedAt": now, "lastSeenAt": now}],
        key=lambda w: w["linkedAt"],
    )[-MAX_WATCHES:]
    p.update(token=token, watchId=watch_id, user=user)
    return {"file": {"watches": watches}, "watchId": watch_id}


def status(pairings: dict, secret: str, now: int) -> dict | None:
    """The watch asking about its pairing: waiting, linked (its token, once), or gone (None)."""
    sweep(pairings, now)
    h = hash_token(secret or "")
    for code, p in list(pairings.items()):
        if not _same(p["secretHash"], h):
            continue
        if p["token"]:
            del pairings[code]
            return {"status": "linked", "token": p["token"], "username": p["user"]}
        if p["expiresAt"] <= now:
            return None
        return {"status": "waiting", "expiresIn": max(0, round((p["expiresAt"] - now) / 1000))}
    return None


# ── Wrong codes ────────────────────────────────────────────────────────────

def link_gate(entry: dict | None, now: int) -> dict:
    until = int((entry or {}).get("lockedUntil") or 0)
    return {"locked": True, "retryAfter": -(-(until - now) // 1000)} if until > now else {"locked": False}


def link_failed(entry: dict | None, now: int) -> dict:
    """One more wrong code: the new entry, locked for a day at the fifth in a day."""
    fails = [t for t in (entry or {}).get("fails", []) if now - t < FAIL_WINDOW_MS] + [now]
    if len(fails) >= FAIL_MAX:
        return {"fails": [], "lockedUntil": now + LOCK_MS}
    return {"fails": fails, "lockedUntil": 0, "left": FAIL_MAX - len(fails)}


def global_fails(times: list, now: int) -> dict:
    recent = [t for t in times if now - t < GLOBAL_WINDOW_MS]
    return {"times": recent, "paused": len(recent) >= GLOBAL_FAIL_MAX}


# ── Linked watches ─────────────────────────────────────────────────────────

def expire(raw, now: int) -> dict:
    file = normalize(raw)
    return {"watches": [w for w in file["watches"] if now - max(w["lastSeenAt"], w["linkedAt"]) < IDLE_MS]}


def watch_of(raw, token: str) -> dict | None:
    h = hash_token(token or "")
    return next((w for w in normalize(raw)["watches"] if _same(w["tokenHash"], h)), None)


def seen(raw, watch_id: str, now: int) -> dict:
    file = normalize(raw)
    return {"watches": [{**w, "lastSeenAt": now} if w["id"] == watch_id else w for w in file["watches"]]}


def rename(raw, watch_id: str, name: str) -> dict:
    file = normalize(raw)
    clean = re.sub(r"\s+", " ", str(name or "")).strip()[:MAX_WATCH_NAME]
    if not any(w["id"] == watch_id for w in file["watches"]):
        return {"error": "No such watch."}
    out = []
    for w in file["watches"]:
        if w["id"] == watch_id:
            w = {k: v for k, v in w.items() if k != "name"}
            if clean:
                w["name"] = clean
        out.append(w)
    return {"file": {"watches": out}}


def unlink(raw, watch_id: str) -> dict:
    file = normalize(raw)
    return {"watches": [w for w in file["watches"] if w["id"] != watch_id]}
