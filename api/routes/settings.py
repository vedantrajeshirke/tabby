from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends

from api.deps import current_user, get_conn
from api.schemas import SettingsIn
from core import categorize, db, expenses, periods

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


@router.get("/periods")
def get_periods(client_today: date | None = None, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> list[dict]:
    """Recent budget cycles for this user, newest first."""
    cycle_start_day = db.load_settings(conn, user_id).cycle_start_day
    return periods.recent_periods(expenses.resolve_today(client_today), cycle_start_day)
