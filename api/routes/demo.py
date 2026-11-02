from datetime import date

from fastapi import APIRouter, Depends

from api.deps import current_user, get_conn
from core import db, demo, expenses

router = APIRouter()


@router.post("/demo-data")
def load_demo_data(client_today: date | None = None, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    return {"added": demo.load(conn, user_id, expenses.resolve_today(client_today))}


@router.delete("/demo-data")
def remove_demo_data(user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    return {"removed": db.delete_synthetic(conn, user_id)}
