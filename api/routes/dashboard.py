from datetime import date

from fastapi import APIRouter, Depends

from api.deps import current_user, get_conn
from core import dashboard, db, expenses

router = APIRouter()
NO_LIMIT = 1_000_000  # totals must count every row, and history goes back to the first one


@router.get("/dashboard")
def get_dashboard(
    client_today: date | None = None,
    hide_synthetic: bool = False,
    period: date | None = None,
    user_id: str = Depends(current_user),
    conn=Depends(get_conn),
) -> dict:
    """`period` is any day in the period to show; without it, the current one."""
    today = expenses.resolve_today(client_today)
    settings = db.load_settings(conn, user_id)
    rows = db.list_expenses(conn, user_id, limit=NO_LIMIT)
    return dashboard.build(rows, settings, today, hide_synthetic, period)
