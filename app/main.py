"""
GKG — Google Keep on a Garmin watch. One process: the web pages for the owner
and the JSON API for the watch.

Web (signed in, except login and setup):
    GET  /                         status, link a watch, linked watches, what the watch shows
    GET  /login   POST /login      sign in                      POST /logout
    GET  /setup?token=…            the owner account, once (the link is printed at start)
    GET  /keep                     connect Keep: POST /keep/connect, /keep/disconnect, /keep/sync
    GET  /settings POST /settings  what the watch shows
    GET  /account POST /account/password
    POST /watches/link             { code } from the watch
    POST /watches/{id}/rename      POST /watches/{id}/unlink

Watch (JSON):
    POST /api/watch/pair           a 6-digit code (3 minutes) and a secret
    POST /api/watch/status         { secret }: waiting, or linked (its token, once); 404 when gone
    GET  /api/watch/lists?rev=     Bearer: the lists, or { rev, same: true } when nothing changed
    POST /api/watch/changes        Bearer, { changes: [...] }: ticks (only in the lists it was given), then the lists
    GET  /api/health               { ok, app: "gkg", version }; nothing about data
"""
from __future__ import annotations

import ipaddress
import logging
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from fastapi import Body, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, pairing, view
from .keep import KeepError, KeepService, NotConnected
from .limits import LoginLock, Window
from .store import Store
from .vault import Vault

HERE = Path(__file__).parent
VERSION = (HERE.parent / "VERSION").read_text().strip() if (HERE.parent / "VERSION").exists() else "0.0.0"
log = logging.getLogger("gkg")

# The biggest request body taken (the watch's changes are a few kilobytes at most).
MAX_BODY = 64 * 1024
# Placeholders from .env.example and anything this short would make a session cookie forgeable.
WEAK_SECRETS = {"replace-me", "changeme", "secret"}
DEFAULT_PROXIES = "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'none'; "
                               "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    # same-origin, not no-referrer: with no-referrer a browser posts forms with Origin: null,
    # and the Origin check (same_origin) would refuse every one of them.
    "Referrer-Policy": "same-origin",
}


@dataclass
class Config:
    data_dir: str = "/data"
    origin: str = ""
    session_secret: str = ""
    data_key: str = ""
    sync_seconds: int = 120
    # Peers allowed to say who the client is (X-Real-IP): the reverse proxy in front.
    trusted_proxies: str = DEFAULT_PROXIES

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            data_dir=os.environ.get("GKG_DATA_DIR", "/data"),
            origin=os.environ.get("GKG_ORIGIN", "").rstrip("/"),
            session_secret=os.environ.get("GKG_SESSION_SECRET", ""),
            data_key=os.environ.get("GKG_DATA_KEY", ""),
            sync_seconds=int(os.environ.get("GKG_SYNC_SECONDS", "120") or 120),
            trusted_proxies=os.environ.get("GKG_TRUSTED_PROXIES", DEFAULT_PROXIES),
        )


@dataclass
class State:
    config: Config
    store: Store
    keep: KeepService
    secret: str
    setup_token: str | None = None
    pairings: dict = field(default_factory=dict)
    link_entry: dict = field(default_factory=dict)
    link_global: list = field(default_factory=list)
    login_lock: LoginLock = field(default_factory=LoginLock)
    pair_limit: Window = field(default_factory=lambda: Window(30, 3600))
    status_limit: Window = field(default_factory=lambda: Window(120, 60))
    watch_limit: Window = field(default_factory=lambda: Window(60, 60))
    bad_token_limit: Window = field(default_factory=lambda: Window(30, 60))
    password_lock: LoginLock = field(default_factory=LoginLock)
    # Pairings and watches.json are read and written from several request threads.
    lock: threading.RLock = field(default_factory=threading.RLock)


def now_ms() -> int:
    return int(time.time() * 1000)


def create_app(config: Config | None = None, keep: KeepService | None = None, start_sync: bool = True) -> FastAPI:
    config = config or Config.from_env()
    if config.session_secret and (len(config.session_secret) < 32 or config.session_secret.lower() in WEAK_SECRETS):
        raise SystemExit("GKG_SESSION_SECRET is a placeholder or too short (at least 32 characters): anyone could forge a sign-in. "
                         "Make one with: python -c \"import secrets; print(secrets.token_hex(32))\"")
    store = Store(config.data_dir)
    try:
        vault = Vault(config.data_key or None)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"{e} Make one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"") from e
    proxies = [ipaddress.ip_network(n.strip(), strict=False) for n in config.trusted_proxies.split(",") if n.strip()]
    keep = keep or KeepService(store, vault, interval=config.sync_seconds)
    secret = config.session_secret or secrets.token_hex(32)
    st = State(config=config, store=store, keep=keep, secret=secret)
    if not store.read("owner.json"):
        st.setup_token = secrets.token_urlsafe(18)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        print(f"GKG {VERSION} — data in {config.data_dir}", flush=True)
        if not config.session_secret:
            print("  GKG_SESSION_SECRET is not set, so one was invented for this run: the next restart signs you out.", flush=True)
        if not vault.ready:
            print("  GKG_DATA_KEY is not set: Keep cannot be connected until it is.", flush=True)
        if st.setup_token:
            print("", flush=True)
            print("  No account yet. Create the owner here:", flush=True)
            print(f"      {config.origin}/setup?token={st.setup_token}", flush=True)
            print("  The token changes on every restart and is spent once the account exists.", flush=True)
            print("", flush=True)
        if start_sync:
            keep.start()
        yield
        keep.stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.gkg = st

    @app.middleware("http")
    async def guard(req: Request, call_next):
        # Big bodies are refused before they are read; a body without a length is not taken.
        length = req.headers.get("content-length")
        if req.method in ("POST", "PUT", "PATCH"):
            if length is None and req.headers.get("transfer-encoding"):
                return PlainTextResponse("Length required.", status_code=411)
            if length is not None and (not length.isdigit() or int(length) > MAX_BODY):
                return PlainTextResponse("Too large.", status_code=413)
        resp = await call_next(req)
        for k, v in HEADERS.items():
            resp.headers.setdefault(k, v)
        return resp
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["ago"] = ago
    templates.env.filters["date"] = lambda t: time.strftime("%-d. %-m. %Y %H:%M", time.localtime(t / 1000 if t > 1e11 else t)) if t else "—"
    secure = config.origin.startswith("https://")

    # ── Helpers ────────────────────────────────────────────────────────────

    def owner() -> dict | None:
        return store.read("owner.json")

    def who(req: Request) -> str | None:
        return auth.read_session(st.secret, owner(), req.cookies.get(auth.COOKIE))

    def client_ip(req: Request) -> str:
        """The client's address: X-Real-IP only when the request comes from a trusted proxy."""
        peer = req.client.host if req.client else ""
        try:
            trusted = any(ipaddress.ip_address(peer) in n for n in proxies)
        except ValueError:
            trusted = False
        real = (req.headers.get("x-real-ip") or "").strip()
        if trusted and real:
            try:
                return str(ipaddress.ip_address(real))
            except ValueError:
                pass
        return peer or "?"

    def same_origin(req: Request) -> bool:
        """A form post must say it comes from this site: Origin, or Referer when a browser leaves Origin out."""
        src = req.headers.get("origin") or ""
        if not src or src == "null":
            src = req.headers.get("referer") or ""
        if not src:
            return False
        want = urlparse(config.origin).netloc if config.origin else req.headers.get("host", "")
        return bool(want) and urlparse(src).netloc == want

    def safe_next(nxt: str) -> str:
        """Where to go after signing in: a path on this site, nothing else."""
        ok = nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt and len(nxt) < 200 and all(ord(c) > 32 for c in nxt)
        return nxt if ok else "/"

    def token_ok(given: str) -> bool:
        return bool(st.setup_token) and secrets.compare_digest(given.encode("utf-8"), (st.setup_token or "").encode("utf-8"))

    def page(req: Request, name: str, **ctx) -> HTMLResponse:
        flash = unquote(req.cookies.get("gkg_flash", ""))
        resp = templates.TemplateResponse(req, name, {"version": VERSION, "user": who(req), "flash": flash, "path": req.url.path, **ctx})
        if flash:
            resp.delete_cookie("gkg_flash", path="/")
        return resp

    def back(to: str, message: str = "", ok: bool = True) -> RedirectResponse:
        r = RedirectResponse(to, status_code=303)
        if message:
            r.set_cookie("gkg_flash", quote(("✓ " if ok else "! ") + message), max_age=60, path="/", httponly=True, samesite="lax", secure=secure)
        return r

    def to_login(req: Request) -> RedirectResponse:
        return RedirectResponse(f"/login?next={quote(req.url.path)}", status_code=303)

    def watches_file() -> dict:
        with st.lock:
            raw = store.read("watches.json")
            file = pairing.expire(raw, now_ms())
            if raw is not None and file != pairing.normalize(raw):
                store.write("watches.json", file)
            return file

    def settings() -> dict:
        return view.clean_settings(store.read("settings.json"))

    def current_view() -> dict:
        v = view.watch_view(keep.notes, settings())
        return {**v, "rev": view.rev_of(v), "syncedAt": int(keep.synced_at)}

    # ── Health ─────────────────────────────────────────────────────────────

    @app.get("/api/health")
    def health():
        # The watch asks this before a code, to be sure the address set in Garmin Connect is a GKG server.
        return {"ok": True, "app": "gkg", "version": VERSION}

    # ── Setup and sign-in ──────────────────────────────────────────────────

    @app.get("/setup", response_class=HTMLResponse)
    def setup_page(req: Request, token: str = ""):
        if owner() or not token_ok(token):
            return RedirectResponse("/login", status_code=303)
        return page(req, "setup.html", token=token)

    @app.post("/setup")
    def setup(req: Request, token: str = Form(""), username: str = Form(""), password: str = Form(""), password2: str = Form("")):
        if not same_origin(req) or owner() or not token_ok(token):
            return RedirectResponse("/login", status_code=303)
        if password != password2:
            return back(f"/setup?token={quote(token)}", "The two passwords are not the same.", False)
        try:
            o = auth.make_owner(username, password)
        except ValueError as e:
            return back(f"/setup?token={quote(token)}", str(e), False)
        store.write("owner.json", o)
        st.setup_token = None
        r = back("/keep", "Account ready. Now connect Keep.")
        r.set_cookie(auth.COOKIE, auth.issue_session(st.secret, o), max_age=auth.SESSION_DAYS * 86400, path="/", httponly=True, samesite="lax", secure=secure)
        return r

    @app.get("/login", response_class=HTMLResponse)
    def login_page(req: Request, next: str = "/"):
        if who(req):
            return RedirectResponse("/", status_code=303)
        return page(req, "login.html", next=safe_next(next), setup=bool(st.setup_token))

    @app.post("/login")
    def login(req: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/")):
        nxt = safe_next(next)
        if not same_origin(req):
            return back("/login", "Sign in from this site.", False)
        ip = client_ip(req)
        wait = st.login_lock.blocked(ip)
        if wait:
            return back(f"/login?next={quote(nxt)}", f"Too many wrong passwords. Try again in {max(1, wait // 60)} min.", False)
        o = owner()
        if not auth.check_password(o, username, password):
            st.login_lock.failed(ip)
            return back(f"/login?next={quote(nxt)}", "Wrong username or password.", False)
        st.login_lock.succeeded(ip)
        r = RedirectResponse(nxt, status_code=303)
        r.set_cookie(auth.COOKIE, auth.issue_session(st.secret, o), max_age=auth.SESSION_DAYS * 86400, path="/", httponly=True, samesite="lax", secure=secure)
        return r

    @app.post("/logout")
    def logout(req: Request):
        if not same_origin(req):
            return RedirectResponse("/", status_code=303)
        r = RedirectResponse("/login", status_code=303)
        r.delete_cookie(auth.COOKIE, path="/")
        return r

    # ── Pages ──────────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    def home(req: Request):
        if not who(req):
            return to_login(req)
        return page(req, "home.html", keep=keep.status(), watches=watches_file()["watches"], view=current_view())

    @app.get("/keep", response_class=HTMLResponse)
    def keep_page(req: Request):
        if not who(req):
            return to_login(req)
        return page(req, "keep.html", keep=keep.status(), vault_ready=vault.ready)

    @app.post("/keep/connect")
    def keep_connect(req: Request, email: str = Form(""), token: str = Form("")):
        if not who(req) or not same_origin(req):
            return to_login(req)
        try:
            keep.connect(email, token)
        except KeepError as e:
            return back("/keep", str(e), False)
        except Exception as e:  # noqa: BLE001
            log.exception("connect")
            return back("/keep", f"Could not connect: {e}", False)
        return back("/settings", f"Keep connected: {len(keep.notes)} notes. Now pick what the watch shows.")

    @app.post("/keep/disconnect")
    def keep_disconnect(req: Request):
        if not who(req) or not same_origin(req):
            return to_login(req)
        keep.disconnect()
        return back("/keep", "Keep disconnected. The token and the cached notes are deleted. To be sure, also sign out the device in your Google account.")

    @app.post("/keep/sync")
    def keep_sync(req: Request):
        if not who(req) or not same_origin(req):
            return to_login(req)
        if not keep.connected:
            return back("/keep", "Keep is not connected.", False)
        return back("/", "Synced.") if keep.sync_now() else back("/", f"Sync failed: {keep.error}", False)

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(req: Request):
        if not who(req):
            return to_login(req)
        notes = sorted([n for n in keep.notes if not n.get("trashed")], key=lambda n: (n["kind"] != "list", n.get("archived", False), view.title_of(n).casefold()))
        return page(req, "settings.html", s=settings(), labels=keep.labels, notes=notes, keep=keep.status(), title_of=view.title_of)

    @app.post("/settings")
    async def settings_save(req: Request):
        if not who(req) or not same_origin(req):
            return to_login(req)
        form = await req.form()
        s = view.clean_settings({
            "labels": form.getlist("labels"),
            "notes": form.getlist("notes"),
            "textNotes": form.get("textNotes") == "on",
            "checked": form.get("checked"),
            "order": form.get("order"),
            "templates": str(form.get("templates") or ""),
        })
        store.write("settings.json", s)
        return back("/settings", "Saved. The watch gets it at its next sync.")

    @app.get("/account", response_class=HTMLResponse)
    def account_page(req: Request):
        if not who(req):
            return to_login(req)
        return page(req, "account.html")

    @app.post("/account/password")
    def account_password(req: Request, current: str = Form(""), password: str = Form(""), password2: str = Form("")):
        u = who(req)
        if not u or not same_origin(req):
            return to_login(req)
        o = owner()
        wait = st.password_lock.blocked(client_ip(req))
        if wait:
            return back("/account", f"Too many wrong passwords. Try again in {max(1, wait // 60)} min.", False)
        if not auth.check_password(o, u, current):
            st.password_lock.failed(client_ip(req))
            return back("/account", "The current password is wrong.", False)
        if password != password2:
            return back("/account", "The two new passwords are not the same.", False)
        try:
            o = auth.change_password(o, password)
        except ValueError as e:
            return back("/account", str(e), False)
        store.write("owner.json", o)
        r = back("/account", "Password changed. Every other browser is signed out.")
        r.set_cookie(auth.COOKIE, auth.issue_session(st.secret, o), max_age=auth.SESSION_DAYS * 86400, path="/", httponly=True, samesite="lax", secure=secure)
        return r

    # ── Watches, from the web ──────────────────────────────────────────────

    @app.post("/watches/link")
    def watch_link(req: Request, code: str = Form("")):
        u = who(req)
        if not u or not same_origin(req):
            return to_login(req)
        now = now_ms()
        gate = pairing.link_gate(st.link_entry, now)
        g = pairing.global_fails(st.link_global, now)
        st.link_global = g["times"]
        if gate["locked"]:
            return back("/", f"Too many wrong codes: linking is locked for {max(1, gate['retryAfter'] // 3600)} h.", False)
        if g["paused"]:
            return back("/", "Too many wrong codes from everyone: linking is paused for an hour.", False)
        with st.lock:
            res = pairing.claim(st.pairings, watches_file(), code=code, user=u, now=now)
            if "file" in res:
                store.write("watches.json", res["file"])
        if "error" in res:
            st.link_entry = pairing.link_failed(st.link_entry, now)
            st.link_global.append(now)
            left = st.link_entry.get("left")
            return back("/", res["error"] + (f" ({left} tries left today.)" if left else " Linking is locked for 24 h."), False)
        return back("/", "Watch linked. It shows your lists in a few seconds.")

    @app.post("/watches/{watch_id}/rename")
    def watch_rename(req: Request, watch_id: str, name: str = Form("")):
        if not who(req) or not same_origin(req):
            return to_login(req)
        with st.lock:
            res = pairing.rename(watches_file(), watch_id, name)
            if "file" in res:
                store.write("watches.json", res["file"])
        if "error" in res:
            return back("/", res["error"], False)
        return back("/", "Renamed.")

    @app.post("/watches/{watch_id}/unlink")
    def watch_unlink(req: Request, watch_id: str):
        if not who(req) or not same_origin(req):
            return to_login(req)
        with st.lock:
            store.write("watches.json", pairing.unlink(watches_file(), watch_id))
        return back("/", "Watch unlinked. It asks for a new code the next time it syncs.")

    # ── The watch ──────────────────────────────────────────────────────────

    @app.post("/api/watch/pair")
    def watch_pair(req: Request):
        if not st.pair_limit.hit(client_ip(req)):
            return JSONResponse({"error": "Too many codes."}, status_code=429)
        with st.lock:
            p = pairing.new_pairing(st.pairings, now_ms())
        if p is None:
            return JSONResponse({"error": "Too many codes."}, status_code=429)
        return p

    @app.post("/api/watch/status")
    def watch_status(req: Request, body: dict = Body(default_factory=dict)):
        if not st.status_limit.hit(client_ip(req)):
            return JSONResponse({"error": "Slow down."}, status_code=429)
        with st.lock:
            s = pairing.status(st.pairings, str(body.get("secret") or "")[:200], now_ms())
        if s is None:
            return JSONResponse({"error": "No such pairing."}, status_code=404)
        # The watch needs only its token; the account's name stays on the server.
        return {k: v for k, v in s.items() if k != "username"}

    def the_watch(req: Request) -> dict | None:
        h = req.headers.get("authorization", "")
        w = None
        if h.lower().startswith("bearer "):
            w = pairing.watch_of(watches_file(), h[7:].strip()[:200])
        if w is None:
            st.bad_token_limit.hit(client_ip(req))
            return None
        if now_ms() - w["lastSeenAt"] > 10 * 60_000:
            with st.lock:
                store.write("watches.json", pairing.seen(watches_file(), w["id"], now_ms()))
        return w

    def bad_tokens(req: Request) -> bool:
        """Too many wrong tokens from this address lately: stop reading files for it for a while."""
        return st.bad_token_limit.full(client_ip(req))

    def unauthorized() -> JSONResponse:
        return JSONResponse({"error": "Not linked."}, status_code=401)

    def for_watch(v: dict) -> dict:
        """What the watch is sent: the lists, nothing about the account."""
        return {"rev": v["rev"], "syncedAt": v["syncedAt"], "lists": v["lists"], "keep": keep.state}

    @app.get("/api/watch/lists")
    def watch_lists(req: Request, rev: str = ""):
        if bad_tokens(req):
            return JSONResponse({"error": "Slow down."}, status_code=429)
        w = the_watch(req)
        if not w:
            return unauthorized()
        if not st.watch_limit.hit(w["id"]):
            return JSONResponse({"error": "Slow down."}, status_code=429)
        keep.fresh(30)
        v = current_view()
        if rev and rev == v["rev"]:
            return {"rev": v["rev"], "same": True, "syncedAt": v["syncedAt"], "keep": keep.state}
        return for_watch(v)

    @app.post("/api/watch/changes")
    def watch_changes(req: Request, body: dict = Body(default_factory=dict)):
        # A plain def: applying syncs with Google, which blocks, so it runs in the thread pool.
        if bad_tokens(req):
            return JSONResponse({"error": "Slow down."}, status_code=429)
        w = the_watch(req)
        if not w:
            return unauthorized()
        if not st.watch_limit.hit(w["id"]):
            return JSONResponse({"error": "Slow down."}, status_code=429)
        asked = view.clean_changes(body.get("changes"))
        # Only the lists and items the watch was given: a watch token opens nothing else in Keep.
        changes = view.allowed_changes(asked, current_view())
        result = {"applied": 0, "skipped": len(asked) - len(changes)}
        if changes:
            try:
                done = keep.apply(changes)
                result = {"applied": done["applied"], "skipped": result["skipped"] + done["skipped"]}
            except NotConnected:
                return JSONResponse({"error": "Keep is not connected."}, status_code=503)
            except KeepError as e:
                return JSONResponse({"error": str(e)}, status_code=503)
        return {**for_watch(current_view()), **result}

    return app


def ago(t) -> str:
    if not t:
        return "never"
    t = t / 1000 if t > 1e11 else t
    s = int(time.time() - t)
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return f"{s // 86400} d ago"
