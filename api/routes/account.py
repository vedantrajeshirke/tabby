from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException

from api.deps import current_user, get_conn
from api.schemas import Strict
from core import db
from core.config import load_config

router = APIRouter()
ADMIN_TIMEOUT_SECONDS = 10


class DeleteAccount(Strict):
    confirm: Literal["DELETE"]


def _delete_sign_in(user_id: str) -> None:
    cfg = load_config()
    response = httpx.delete(
        f"{cfg.supabase_url}/auth/v1/admin/users/{user_id}",
        headers={"apikey": cfg.supabase_secret_key},
        timeout=ADMIN_TIMEOUT_SECONDS,
    )
    if response.status_code not in (200, 204, 404):  # 404: already gone, from an earlier retry
        raise RuntimeError(f"Sign-in removal returned {response.status_code}")


@router.delete("/account", status_code=204)
def delete_account(body: DeleteAccount, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> None:
    """Data goes first. If removing the sign-in then fails, the user can retry, with nothing left behind."""
    db.delete_user_data(conn, user_id)
    if load_config().auth_mode == "local":
        return
    try:
        _delete_sign_in(user_id)
    except (httpx.HTTPError, RuntimeError):
        raise HTTPException(
            status_code=502,
            detail="Your data was deleted, but your sign-in couldn't be removed. Please try again.",
        )
