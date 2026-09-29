from app import pairing as p

T0 = 1_700_000_000_000


def test_code_claim_status_once():
    pairings = {}
    n = p.new_pairing(pairings, T0)
    assert len(n["code"]) == 6 and n["expiresIn"] == 180
    assert p.status(pairings, n["secret"], T0 + 1000)["status"] == "waiting"
    res = p.claim(pairings, None, code=n["code"][:3] + " " + n["code"][3:], user="susko", now=T0 + 2000)
    w = res["file"]["watches"][0]
    assert w["id"] == res["watchId"] and "token" not in w
    s = p.status(pairings, n["secret"], T0 + 3000)
    assert s["status"] == "linked" and s["username"] == "susko"
    assert p.watch_of(res["file"], s["token"])["id"] == w["id"]
    # The token is handed out once.
    assert p.status(pairings, n["secret"], T0 + 4000) is None


def test_wrong_secret_and_expiry():
    pairings = {}
    n = p.new_pairing(pairings, T0)
    assert p.status(pairings, "nope", T0) is None
    assert "error" in p.claim(pairings, None, code=n["code"], user="u", now=T0 + p.CODE_MS)
    assert p.status(pairings, n["secret"], T0 + p.CODE_MS) is None


def test_code_cannot_be_claimed_twice():
    pairings = {}
    n = p.new_pairing(pairings, T0)
    assert "file" in p.claim(pairings, None, code=n["code"], user="u", now=T0)
    assert "error" in p.claim(pairings, None, code=n["code"], user="u", now=T0)


def test_too_many_pairings():
    pairings = {}
    for _ in range(p.MAX_PAIRINGS):
        assert p.new_pairing(pairings, T0)
    assert p.new_pairing(pairings, T0) is None
    assert p.new_pairing(pairings, T0 + p.CODE_MS) is not None


def test_wrong_codes_lock():
    e = {}
    for i in range(p.FAIL_MAX - 1):
        e = p.link_failed(e, T0 + i)
        assert not p.link_gate(e, T0 + i)["locked"]
    e = p.link_failed(e, T0 + 10)
    assert p.link_gate(e, T0 + 11)["locked"]
    assert not p.link_gate(e, T0 + 10 + p.LOCK_MS)["locked"]
    assert p.global_fails([T0] * p.GLOBAL_FAIL_MAX, T0 + 1)["paused"]
    assert not p.global_fails([T0] * p.GLOBAL_FAIL_MAX, T0 + p.GLOBAL_WINDOW_MS)["paused"]


def test_max_watches_rename_unlink_expire():
    file = None
    pairings = {}
    for i in range(p.MAX_WATCHES + 1):
        n = p.new_pairing(pairings, T0 + i)
        file = p.claim(pairings, file, code=n["code"], user="u", now=T0 + i)["file"]
    assert len(file["watches"]) == p.MAX_WATCHES
    wid = file["watches"][0]["id"]
    file = p.rename(file, wid, "  Fenix   8 ")["file"]
    assert file["watches"][0]["name"] == "Fenix 8"
    file = p.rename(file, wid, "")["file"]
    assert "name" not in file["watches"][0]
    assert "error" in p.rename(file, "nope", "x")
    file = p.seen(file, wid, T0 + p.IDLE_MS)
    left = p.expire(file, T0 + p.IDLE_MS + 10)
    assert [w["id"] for w in left["watches"]] == [wid]
    assert p.unlink(left, wid) == {"watches": []}
