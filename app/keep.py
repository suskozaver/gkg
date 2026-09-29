"""
Google Keep, through gkeepapi (unofficial: Keep has no public API for
personal accounts).

`GKeepClient` is the only place that touches gkeepapi; `KeepService` keeps one
signed-in client, syncs it in the background, caches its state encrypted in
the data folder and hands out plain notes. Tests swap the client for a fake.

Files:
    keep.json        { email, deviceId, token: <sealed master token>, connectedAt }
    keep-state.bin   gkeepapi's dump, sealed (so a restart does not pull everything again)
"""
from __future__ import annotations

import logging
import secrets
import threading
import time
from typing import Callable, Protocol

from .store import Store
from .vault import Vault, VaultError

log = logging.getLogger("gkg.keep")


class KeepError(Exception):
    pass


class NotConnected(KeepError):
    pass


class KeepClient(Protocol):
    def login(self, email: str, master_token: str, device_id: str, state: dict | None) -> None: ...
    def sync(self) -> None: ...
    def dump(self) -> dict: ...
    def notes(self) -> list[dict]: ...
    def labels(self) -> list[str]: ...
    def set_checked(self, list_id: str, item_id: str, done: bool) -> bool: ...
    def add_item(self, list_id: str, text: str) -> bool: ...


def exchange_oauth_token(email: str, oauth_token: str, device_id: str) -> str:
    """The oauth_token cookie from accounts.google.com/EmbeddedSetup, for a master token (aas_et/…)."""
    import gpsoauth

    res = gpsoauth.exchange_token(email, oauth_token, device_id)
    token = res.get("Token")
    if not token:
        raise KeepError(f"Google did not give a master token ({res.get('Error') or 'no reason given'}). The oauth_token works once and only for a few minutes: get a fresh one.")
    return token


class GKeepClient:
    def __init__(self):
        import gkeepapi

        self._gk = gkeepapi
        self._keep = gkeepapi.Keep()

    def login(self, email, master_token, device_id, state=None):
        try:
            self._keep.authenticate(email, master_token, state=state, sync=True, device_id=device_id)
        except self._gk.exception.LoginException as e:
            raise KeepError(f"Google refused the master token ({e}). Connect again with a new one.") from e
        except self._gk.exception.KeepException:
            if state is None:
                raise
            # A cached state that no longer fits: start over from the server.
            self._keep = self._gk.Keep()
            self._keep.authenticate(email, master_token, state=None, sync=True, device_id=device_id)

    def sync(self):
        try:
            self._keep.sync()
        except self._gk.exception.ResyncRequiredException:
            self._keep.sync(resync=True)

    def dump(self):
        return self._keep.dump()

    def notes(self):
        out = []
        for n in self._keep.all():
            is_list = isinstance(n, self._gk.node.List)
            ts = n.timestamps
            updated = ts.updated.timestamp() if getattr(ts, "updated", None) else 0
            out.append({
                "id": n.id,
                "kind": "list" if is_list else "note",
                "title": n.title or "",
                "pinned": bool(n.pinned),
                "archived": bool(n.archived),
                "trashed": bool(n.trashed or n.deleted),
                "labels": [lb.name for lb in n.labels.all()],
                "updated": int(updated),
                "items": [{"id": i.id, "text": i.text or "", "checked": bool(i.checked), "indented": bool(i.indented)} for i in n.items] if is_list else [],
                "text": "" if is_list else (n.text or ""),
            })
        return out

    def labels(self):
        return sorted((lb.name for lb in self._keep.labels()), key=str.casefold)

    def _list(self, list_id):
        n = self._keep.get(list_id)
        return n if isinstance(n, self._gk.node.List) and not n.trashed and not n.deleted else None

    def set_checked(self, list_id, item_id, done):
        n = self._list(list_id)
        item = next((i for i in n.items if i.id == item_id), None) if n else None
        if item is None:
            return False
        if item.checked != done:
            item.checked = done
        return True

    def add_item(self, list_id, text):
        n = self._list(list_id)
        if n is None:
            return False
        n.add(text, False, self._gk.node.NewListItemPlacementValue.Bottom)
        return True


class KeepService:
    def __init__(self, store: Store, vault: Vault, *, interval: int = 120, client_factory: Callable[[], KeepClient] = GKeepClient,
                 exchange: Callable[[str, str, str], str] = exchange_oauth_token):
        self.store = store
        self.vault = vault
        self.interval = max(30, int(interval))
        self._factory = client_factory
        self._exchange = exchange
        self._client: KeepClient | None = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self.notes: list[dict] = []
        self.labels: list[str] = []
        self.state = "off"  # off, starting, ok, error
        self.error = ""
        self.synced_at = 0.0

    # ── Status ─────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._client is not None

    def status(self) -> dict:
        meta = self.store.read("keep.json") or {}
        return {"state": self.state, "error": self.error, "email": meta.get("email", ""), "connectedAt": meta.get("connectedAt", 0),
                "syncedAt": int(self.synced_at), "notes": len(self.notes)}

    # ── Background ─────────────────────────────────────────────────────────

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="keep-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run(self) -> None:
        self.resume()
        while not self._stop.is_set():
            self._wake.wait(self.interval)
            self._wake.clear()
            if self._stop.is_set():
                break
            if self.connected:
                self.sync_now()
            elif (self.store.read("keep.json") or {}).get("token"):
                self.resume()

    def resume(self) -> None:
        """Sign in again with the stored token, from the cached state when there is one."""
        with self._lock:
            # Read inside the lock, so a Disconnect in between cannot be undone.
            meta = self.store.read("keep.json")
            if not meta or not meta.get("token"):
                self.state = "off"
                return
            self.state = "starting"
            try:
                token = self.vault.open(meta["token"])
                state = None
                blob = self.store.read_bytes("keep-state.bin")
                if blob:
                    try:
                        state = self.vault.open_json(blob)
                    except (VaultError, ValueError, OSError):
                        state = None
                client = self._factory()
                client.login(meta["email"], token, meta["deviceId"], state)
                self._client = client
                self._after_sync()
            except Exception as e:  # noqa: BLE001 — any failure is shown, the loop tries again later
                self._fail(e)

    # ── Connecting ─────────────────────────────────────────────────────────

    def connect(self, email: str, secret: str) -> None:
        """Connect with a master token (aas_et/…) or with the oauth_token cookie, which is exchanged for one."""
        email = (email or "").strip()
        secret = (secret or "").strip()
        if "@" not in email:
            raise KeepError("That is not an email address.")
        if not secret:
            raise KeepError("Paste the oauth_token (or a master token).")
        if not self.vault.ready:
            raise KeepError("GKG_DATA_KEY is not set in .env, so the token cannot be stored encrypted. Set it and restart.")
        device_id = secrets.token_hex(8)
        master = secret if secret.startswith("aas_et/") else self._exchange(email, secret, device_id)
        client = self._factory()
        client.login(email, master, device_id, None)
        with self._lock:
            self.store.write("keep.json", {"email": email, "deviceId": device_id, "token": self.vault.seal(master), "connectedAt": int(time.time())})
            self.store.delete("keep-state.bin")
            self._client = client
            self._after_sync()

    def disconnect(self) -> None:
        with self._lock:
            self._client = None
            self.store.delete("keep.json")
            self.store.delete("keep-state.bin")
            self.notes, self.labels = [], []
            self.state, self.error, self.synced_at = "off", "", 0.0

    # ── Syncing ────────────────────────────────────────────────────────────

    def sync_now(self) -> bool:
        with self._lock:
            if self._client is None:
                return False
            try:
                self._client.sync()
                self._after_sync()
                return True
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                return False

    def fresh(self, max_age: int = 30) -> None:
        """Sync first when the last one is older than max_age seconds (the watch just opened)."""
        if self.connected and time.time() - self.synced_at > max_age:
            self.sync_now()

    def apply(self, changes: list[dict]) -> dict:
        """Changes from the watch, then one sync. Setting `done` is idempotent, so a watch that
        sends the same change again (it did not hear back) does no harm."""
        with self._lock:
            if self._client is None:
                raise NotConnected("Keep is not connected.")
            applied = skipped = 0
            for c in changes:
                if c["op"] == "check":
                    ok = self._client.set_checked(c["list"], c["item"], c["done"])
                else:
                    ok = self._client.add_item(c["list"], c["text"])
                applied, skipped = (applied + 1, skipped) if ok else (applied, skipped + 1)
            try:
                self._client.sync()
            except Exception as e:  # noqa: BLE001
                self._fail(e)
                raise KeepError("Could not sync with Keep. The change is kept and goes with the next sync.") from e
            self._after_sync()
            return {"applied": applied, "skipped": skipped}

    def _after_sync(self) -> None:
        self.notes = self._client.notes()
        self.labels = self._client.labels()
        self.synced_at = time.time()
        self.state, self.error = "ok", ""
        try:
            self.store.write_bytes("keep-state.bin", self.vault.seal_json(self._client.dump()))
        except Exception as e:  # noqa: BLE001 — the cache is a nicety
            log.warning("could not cache Keep state: %s", e)

    def _fail(self, e: Exception) -> None:
        self.state = "error"
        self.error = str(e) or e.__class__.__name__
        log.warning("Keep: %s", self.error)
