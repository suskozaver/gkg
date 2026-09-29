"""Small JSON files in the data folder, written whole and atomically."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

_lock = threading.RLock()


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.root / name

    def read(self, name: str, default=None):
        with _lock:
            try:
                return json.loads(self.path(name).read_text("utf-8"))
            except FileNotFoundError:
                return default
            except (OSError, ValueError):
                return default

    def write(self, name: str, value) -> None:
        self.write_bytes(name, json.dumps(value, ensure_ascii=False, indent=1).encode("utf-8"))

    def read_bytes(self, name: str) -> bytes | None:
        with _lock:
            try:
                return self.path(name).read_bytes()
            except OSError:
                return None

    def write_bytes(self, name: str, data: bytes) -> None:
        with _lock:
            target = self.path(name)
            fd, tmp = tempfile.mkstemp(dir=self.root, prefix=f".{name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, target)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    def delete(self, name: str) -> None:
        with _lock:
            try:
                self.path(name).unlink()
            except FileNotFoundError:
                pass
