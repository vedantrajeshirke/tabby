"""File storage behind one interface. Keys look like <user_id>/<hash>.<ext>."""
import re
from pathlib import Path
from typing import Protocol

from core.config import DATA_DIR

KEY_RE = re.compile(r"^[0-9a-f-]{36}/[0-9a-f]{64}\.[a-z0-9]{1,5}$")


class Storage(Protocol):
    def save(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> None: ...


def file_key(user_id: str, file_hash: str, extension: str) -> str:
    key = f"{user_id}/{file_hash}.{extension}"
    _check_key(key)
    return key


def _check_key(key: str) -> None:
    if not KEY_RE.fullmatch(key):
        raise ValueError("Invalid file key")


class LocalStorage:
    def __init__(self, root: Path = DATA_DIR / "files"):
        self.root = root

    def _path(self, key: str) -> Path:
        _check_key(key)
        return self.root / key

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
