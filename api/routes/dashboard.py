from datetime import date

from fastapi import APIRouter, Depends

from api.deps import current_user, get_conn
from core import dashboard, db, expenses

router = APIRouter()
NO_LIMIT = 100_000  # totals must count every row in range


@router.get("/dashboard")
def get_dashboard(
    client_today: date | None = None,
    hide_synthetic: bool = False,
    user_id: str = Depends(current_user),
    conn=Depends(get_conn),
) -> dict:
    today = expenses.resolve_today(client_today)
    settings = db.load_settings(conn, user_id)
    start, end = dashboard.fetch_range(today, settings.cycle_start_day)
    rows = db.list_expenses(conn, user_id, start.isoformat(), end.isoformat(), limit=NO_LIMIT)
    return dashboard.build(rows, settings, today, hide_synthetic)
