import re

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.keep import KeepService
from app.main import Config, create_app
from app.store import Store
from app.vault import Vault


class FakeClient:
    """Stands in for gkeepapi: one list and one note, changes kept in memory."""

    fail_sync = False

    def __init__(self):
        self.lists = {
            "L1": {"title": "Trgovina", "labels": ["garmin"], "items": {"i1": ["Mleko", False], "i2": ["Kruh", True]}},
        }
        self.syncs = 0

    def login(self, email, master_token, device_id, state):
        assert master_token.startswith("aas_et/")
        self.syncs += 1

    def sync(self):
        if FakeClient.fail_sync:
            raise RuntimeError("network down")
        self.syncs += 1

    def dump(self):
        return {"lists": self.lists}

    def notes(self):
        return [{"id": k, "kind": "list", "title": v["title"], "pinned": False, "archived": False, "trashed": False,
                 "labels": v["labels"], "updated": 1, "text": "",
                 "items": [{"id": i, "text": t, "checked": c, "indented": False} for i, (t, c) in v["items"].items()]}
                for k, v in self.lists.items()]

    def labels(self):
        return ["garmin"]

    def set_checked(self, list_id, item_id, done):
        it = self.lists.get(list_id, {}).get("items", {}).get(item_id)
        if not it:
            return False
        it[1] = done
        return True

    def add_item(self, list_id, text):
        if list_id not in self.lists:
            return False
        self.lists[list_id]["items"][f"n{len(self.lists[list_id]['items'])}"] = [text, False]
        return True


@pytest.fixture
def env(tmp_path):
    FakeClient.fail_sync = False
    cfg = Config(data_dir=str(tmp_path), origin="http://testserver", session_secret="s" * 64, data_key=Fernet.generate_key().decode())
    store = Store(tmp_path)
    keep = KeepService(store, Vault(cfg.data_key), client_factory=FakeClient, exchange=lambda e, t, d: "aas_et/exchanged")
    app = create_app(cfg, keep=keep, start_sync=False)
    # A browser posting a form from the site says so in Origin.
    with TestClient(app, headers={"origin": "http://testserver"}) as c:
        yield c, app.state.gkg, keep


def setup_owner(c, st):
    r = c.post("/setup", data={"token": st.setup_token, "username": "owner", "password": "a good password", "password2": "a good password"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/keep"
    return r


def test_setup_login_and_pages(env):
    c, st, keep = env
    assert c.get("/", follow_redirects=False).headers["location"] == "/login?next=/"
    assert c.get("/setup?token=wrong", follow_redirects=False).status_code == 303
    setup_owner(c, st)
    assert st.setup_token is None
    for path in ("/", "/keep", "/settings", "/account"):
        assert c.get(path).status_code == 200, path
    c.post("/logout")
    c.cookies.clear()
    r = c.post("/login", data={"username": "owner", "password": "nope nope nope"}, follow_redirects=False)
    assert r.headers["location"].startswith("/login")
    r = c.post("/login", data={"username": "owner", "password": "a good password", "next": "/settings"}, follow_redirects=False)
    assert r.headers["location"] == "/settings" and "gkg_session" in r.cookies


def test_cross_site_post_refused(env):
    c, st, keep = env
    setup_owner(c, st)
    r = c.post("/keep/disconnect", headers={"origin": "https://evil.example"}, follow_redirects=False)
    assert r.headers["location"].startswith("/login")


def test_connect_keep_and_token_is_sealed(env, tmp_path):
    c, st, keep = env
    setup_owner(c, st)
    r = c.post("/keep/connect", data={"email": "a@gmail.com", "token": "oauth2_4/abc"}, follow_redirects=False)
    assert r.headers["location"] == "/settings"
    assert keep.state == "ok" and keep.notes
    raw = (tmp_path / "keep.json").read_text()
    assert "aas_et" not in raw and "oauth2_4" not in raw
    assert b"Mleko" not in (tmp_path / "keep-state.bin").read_bytes()
    c.post("/keep/disconnect")
    assert not (tmp_path / "keep.json").exists() and keep.state == "off"


def pair(c):
    p = c.post("/api/watch/pair").json()
    assert c.post("/api/watch/status", json={"secret": p["secret"]}).json()["status"] == "waiting"
    r = c.post("/watches/link", data={"code": p["code"]}, follow_redirects=False)
    assert r.status_code == 303
    s = c.post("/api/watch/status", json={"secret": p["secret"]}).json()
    assert s["status"] == "linked" and "username" not in s
    assert c.post("/api/watch/status", json={"secret": p["secret"]}).status_code == 404
    return {"authorization": f"Bearer {s['token']}"}


def test_watch_flow(env):
    c, st, keep = env
    setup_owner(c, st)
    c.post("/keep/connect", data={"email": "a@gmail.com", "token": "aas_et/direct"})
    h = pair(c)
    assert c.get("/api/watch/lists").status_code == 401
    assert c.get("/api/watch/lists", headers={"authorization": "Bearer nope"}).status_code == 401
    d = c.get("/api/watch/lists", headers=h).json()
    assert d["lists"][0]["title"] == "Trgovina" and d["keep"] == "ok"
    assert "username" not in d and "templates" not in d
    assert c.get(f"/api/watch/lists?rev={d['rev']}", headers=h).json()["same"] is True

    body = {"changes": [{"op": "check", "list": "L1", "item": "i1", "done": True}, {"op": "add", "list": "L1", "text": "Jajca"},
                        {"op": "check", "list": "L1", "item": "gone", "done": True}]}
    d2 = c.post("/api/watch/changes", headers=h, json=body).json()
    assert d2["applied"] == 2 and d2["skipped"] == 1 and d2["rev"] != d["rev"]
    items = {i["text"]: i["done"] for i in d2["lists"][0]["items"]}
    assert items == {"Mleko": True, "Kruh": True, "Jajca": False}

    FakeClient.fail_sync = True
    assert c.post("/api/watch/changes", headers=h, json=body).status_code == 503
    FakeClient.fail_sync = False

    # Unlink on the web: the watch is told at its next call.
    wid = st.store.read("watches.json")["watches"][0]["id"]
    c.post(f"/watches/{wid}/unlink")
    assert c.get("/api/watch/lists", headers=h).status_code == 401


def test_wrong_codes_lock_linking(env):
    c, st, keep = env
    setup_owner(c, st)
    for _ in range(5):
        c.post("/watches/link", data={"code": "000000"})
    p = c.post("/api/watch/pair").json()
    r = c.post("/watches/link", data={"code": p["code"]}, follow_redirects=False)
    assert "locked" in r.cookies.get("gkg_flash", "").replace("%20", " ")


def test_settings_saved(env):
    c, st, keep = env
    setup_owner(c, st)
    c.post("/keep/connect", data={"email": "a@gmail.com", "token": "aas_et/direct"})
    c.post("/settings", data={"labels": ["garmin"], "checked": "hide", "order": "title", "templates": "Milk\nBread"})
    s = st.store.read("settings.json")
    assert s["labels"] == ["garmin"] and s["checked"] == "hide" and s["templates"] == ["Milk", "Bread"]
    html = c.get("/").text
    assert "Mleko" in html and "Kruh" not in re.sub(r"<[^>]+>", "", html.split("What the watch shows")[1])


def test_health_says_nothing(env):
    c, st, keep = env
    assert c.get("/api/health").json().keys() == {"ok", "app", "version"}


def test_security_headers_and_body_limit(env):
    c, st, keep = env
    r = c.get("/login")
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    big = c.post("/api/watch/status", content=b"{" + b" " * (70 * 1024) + b"}", headers={"content-type": "application/json"})
    assert big.status_code == 413


def test_origin_required_for_forms(env):
    c, st, keep = env
    setup_owner(c, st)
    for h in ({"origin": "null"}, {"origin": "https://evil.example"}, {"origin": ""}):
        r = c.post("/keep/disconnect", headers=h, follow_redirects=False)
        assert r.headers["location"].startswith("/login"), h
    # Referer is enough when Origin is left out.
    r = c.post("/keep/sync", headers={"origin": "", "referer": "http://testserver/"}, follow_redirects=False)
    assert r.headers["location"] == "/keep"


def test_next_stays_on_site(env):
    c, st, keep = env
    setup_owner(c, st)
    c.cookies.clear()
    for bad in ("//evil.com", "/\\evil.com", "/\tevil", "https://evil.com", "/ok\n"):
        r = c.post("/login", data={"username": "owner", "password": "a good password", "next": bad}, follow_redirects=False)
        assert r.headers["location"] == "/", bad
        c.cookies.clear()


def test_watch_changes_only_in_its_lists(env):
    c, st, keep = env
    setup_owner(c, st)
    c.post("/keep/connect", data={"email": "a@gmail.com", "token": "aas_et/direct"})
    keep._client.lists["L2"] = {"title": "Secret", "labels": [], "items": {"s1": ["Hidden", False]}}
    keep.sync_now()
    c.post("/settings", data={"labels": ["garmin"]})
    h = pair(c)
    d = c.post("/api/watch/changes", headers=h, json={"changes": [
        {"op": "check", "list": "L2", "item": "s1", "done": True},
        {"op": "add", "list": "L2", "text": "injected"},
        {"op": "check", "list": "L1", "item": "i1", "done": True}]}).json()
    assert d["applied"] == 1 and d["skipped"] == 2
    assert keep._client.lists["L2"]["items"] == {"s1": ["Hidden", False]}
    assert [l["id"] for l in d["lists"]] == ["L1"]


def test_real_ip_only_from_a_trusted_proxy(tmp_path):
    from app.limits import LoginLock
    cfg = Config(data_dir=str(tmp_path), origin="http://testserver", session_secret="s" * 64,
                 data_key=Fernet.generate_key().decode(), trusted_proxies="10.0.0.0/8")
    app = create_app(cfg, keep=KeepService(Store(tmp_path), Vault(cfg.data_key), client_factory=FakeClient), start_sync=False)
    st = app.state.gkg
    with TestClient(app, headers={"origin": "http://testserver"}) as c:
        # testclient is not a trusted proxy: the header is ignored, the lock falls on the peer.
        for i in range(5):
            c.post("/login", data={"username": "x", "password": "wrong password"}, headers={"x-real-ip": f"1.2.3.{i}"})
        assert st.login_lock.blocked("testclient") > 0


def test_weak_session_secret_refused(tmp_path):
    with pytest.raises(SystemExit):
        create_app(Config(data_dir=str(tmp_path), session_secret="replace-me"), start_sync=False)
    with pytest.raises(SystemExit):
        create_app(Config(data_dir=str(tmp_path), session_secret="s" * 64, data_key="replace-me"), start_sync=False)


def test_setup_token_odd_characters(env):
    c, st, keep = env
    assert c.get("/setup?token=%C3%A9", follow_redirects=False).status_code == 303
