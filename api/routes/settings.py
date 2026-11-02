from dataclasses import asdict

from fastapi import APIRouter, Depends

from api.deps import current_user, get_conn
from api.schemas import SettingsIn
from core import categorize, db

router = APIRouter()


@router.get("/settings")
def get_settings(user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    return asdict(db.load_settings(conn, user_id))


@router.put("/settings")
def put_settings(body: SettingsIn, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    db.save_settings(conn, user_id, body.to_settings())
    return asdict(db.load_settings(conn, user_id))


@router.get("/categories")
def get_categories(_: str = Depends(current_user)) -> list[str]:
    return categorize.load_config()["categories"]
