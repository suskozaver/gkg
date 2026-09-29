import pytest

from app import auth
from app.limits import LoginLock, Window
from app.vault import Vault, VaultError


def test_owner_and_sessions():
    o = auth.make_owner(" Owner ", "correct horse battery")
    assert o["username"] == "owner"
    assert auth.check_password(o, "owner", "correct horse battery")
    assert not auth.check_password(o, "owner", "wrong password!")
    assert not auth.check_password(o, "other", "correct horse battery")
    assert not auth.check_password(None, "owner", "x")
    s = auth.issue_session("secret", o, now=1000)
    assert auth.read_session("secret", o, s, now=2000) == "owner"
    assert auth.read_session("other", o, s, now=2000) is None
    assert auth.read_session("secret", o, s, now=1000 + auth.SESSION_DAYS * 86400 + 1) is None
    assert auth.read_session("secret", o, s[:-1] + ("0" if s[-1] != "0" else "1"), now=2000) is None
    o2 = auth.change_password(o, "another good one")
    assert auth.read_session("secret", o2, s, now=2000) is None  # the epoch signs everyone out


def test_owner_rules():
    with pytest.raises(ValueError):
        auth.make_owner("a", "long enough pw")
    with pytest.raises(ValueError):
        auth.make_owner("owner", "short")


def test_vault():
    from cryptography.fernet import Fernet

    k = Fernet.generate_key().decode()
    v = Vault(k)
    assert v.open(v.seal("aas_et/x")) == "aas_et/x"
    assert v.open_json(v.seal_json({"a": [1]})) == {"a": [1]}
    with pytest.raises(VaultError):
        Vault(Fernet.generate_key().decode()).open(v.seal("x"))
    with pytest.raises(VaultError):
        Vault(None).seal("x")
    with pytest.raises(VaultError):
        Vault("not a key")


def test_limits():
    w = Window(2, 60)
    assert w.hit("ip", 0) and w.hit("ip", 1) and not w.hit("ip", 2) and w.hit("ip", 61)
    lock = LoginLock(max_fails=3, window=100, lock=50, global_max=100)
    for t in range(3):
        assert lock.blocked("ip", t) == 0
        lock.failed("ip", t)
    assert lock.blocked("ip", 3) > 0 and lock.blocked("other", 3) == 0
    assert lock.blocked("ip", 60) == 0
