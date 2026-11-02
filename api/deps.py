"""Request dependencies: the current user and a database connection."""
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException

from api import auth
from core import db
from core.config import LOCAL_USER_ID, load_config

SIGN_IN_REQUIRED = "Please sign in to continue."


def _refuse() -> HTTPException:
    return HTTPException(status_code=401, detail=SIGN_IN_REQUIRED, headers={"WWW-Authenticate": "Bearer"})


def current_user(authorization: str | None = Header(default=None)) -> str:
    """The user always comes from here, never from a request body or URL."""
    cfg = load_config()
    if cfg.auth_mode == "local":
        return LOCAL_USER_ID
    if cfg.auth_mode != "supabase" or not cfg.supabase_url:
        raise _refuse()  # a misconfigured server refuses everyone rather than letting them in
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _refuse()
    try:
        return auth.verify_token(token.strip(), cfg.supabase_url)
    except auth.InvalidToken:
        raise _refuse()


def get_conn(user_id: str = Depends(current_user)) -> Iterator:
    """A connection limited by row-level security to this user's rows."""
    with db.connect() as conn:
        db.act_as(conn, user_id)
        yield conn
