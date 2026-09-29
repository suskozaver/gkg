"""In-memory limits: requests per key per window, and wrong passwords. A restart forgets them."""
from __future__ import annotations

import threading
import time


class Window:
    """At most `limit` hits per `seconds` for each key (sliding log)."""

    def __init__(self, limit: int, seconds: int):
        self.limit = limit
        self.seconds = seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            if len(self._hits) > 10_000:
                self._hits.clear()
            hits = [t for t in self._hits.get(key, []) if now - t < self.seconds]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


class LoginLock:
    """Wrong passwords: `max_fails` in `window` locks sign-in from that address for `lock` seconds,
    and more than `global_max` wrong ones from everyone in an hour pauses sign-in for all."""

    def __init__(self, max_fails=5, window=900, lock=900, global_max=50):
        self.max_fails, self.window, self.lock, self.global_max = max_fails, window, lock, global_max
        self._fails: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}
        self._all: list[float] = []
        self._mutex = threading.Lock()

    def blocked(self, key: str, now: float | None = None) -> int:
        """Seconds until sign-in is allowed again, 0 when it is."""
        now = time.time() if now is None else now
        with self._mutex:
            self._all = [t for t in self._all if now - t < 3600]
            if len(self._all) >= self.global_max:
                return int(3600 - (now - self._all[0])) + 1
            until = self._locked.get(key, 0)
            return int(until - now) + 1 if until > now else 0

    def failed(self, key: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._mutex:
            self._all.append(now)
            fails = [t for t in self._fails.get(key, []) if now - t < self.window] + [now]
            if len(fails) >= self.max_fails:
                self._locked[key] = now + self.lock
                fails = []
            self._fails[key] = fails

    def succeeded(self, key: str) -> None:
        with self._mutex:
            self._fails.pop(key, None)
            self._locked.pop(key, None)
