"""A simple per-user limit on uploads, because reading a file is slow. One server, in memory."""
import threading
import time
from collections import defaultdict, deque

MAX_UPLOADS = 30
WINDOW_SECONDS = 60

_lock = threading.Lock()
_uploads: dict[str, deque] = defaultdict(deque)


def allow_upload(user_id: str, now: float | None = None) -> bool:
    now = time.monotonic() if now is None else now
    with _lock:
        recent = _uploads[user_id]
        while recent and now - recent[0] >= WINDOW_SECONDS:
            recent.popleft()
        if len(recent) >= MAX_UPLOADS:
            return False
        recent.append(now)
        return True


def reset() -> None:
    with _lock:
        _uploads.clear()
