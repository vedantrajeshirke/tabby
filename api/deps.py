"""Request dependencies: the current user and a database connection."""
from collections.abc import Iterator

from fastapi import HTTPException

from core import db
from core.config import LOCAL_USER_ID, load_config


def current_user() -> str:
    """The user always comes from here, never from a request body or URL."""
    if load_config().auth_mode == "local":
        return LOCAL_USER_ID
    # Token verification arrives in M7. Until then, any other mode refuses every request.
    raise HTTPException(status_code=401, detail="Please sign in to continue.")


def get_conn() -> Iterator:
    with db.connect() as conn:
        yield conn
