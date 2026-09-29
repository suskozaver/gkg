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
    with TestClient(app) as c:
        yield c, app.state.gkg, keep


def setup_owner(c, st):
    r = c.post("/setup", data={"token": st.setup_token, "username": "susko", "password": "a good password", "password2": "a good password"}, follow_redirects=False)
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
    r = c.post("/login", data={"username": "susko", "password": "nope nope nope"}, follow_redirects=False)
    assert r.headers["location"].startswith("/login")
    r = c.post("/login", data={"username": "susko", "password": "a good password", "next": "/settings"}, follow_redirects=False)
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
    assert s["status"] == "linked" and s["username"] == "susko"
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
    assert d["lists"][0]["title"] == "Trgovina" and d["username"] == "susko" and d["keep"] == "ok"
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
