from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import current_user, get_conn
from api.schemas import ExpenseEdit, ExpenseForm
from core import categorize, confirm, db, expenses
from core.redact import redact_value

router = APIRouter()
NOT_FOUND = "This expense doesn't exist. It may have been deleted; refresh the list."


def public_expense(row: dict) -> dict:
    """What the browser sees: no owner ID or file hash."""
    hidden = {"user_id", "file_hash", "extraction_json"}
    return {
        **{k: v for k, v in row.items() if k not in hidden},
        "category_label": categorize.SOURCE_LABELS.get(row["category_source"], ""),
    }


def blocked_response(checked: expenses.Review) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"message": "Fix the highlighted fields, then save again.", **expenses.report_review(checked)},
    )


@router.post("/expenses", status_code=201)
def create_expense(body: ExpenseForm, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    original = body.extraction.to_extraction() if body.extraction else None
    form = confirm.FormValues(
        body.merchant, body.date, body.total, body.subtotal, body.tax, body.tip, body.payment_method, body.note
    )
    today = expenses.resolve_today(body.client_today)
    try:
        checked = expenses.review(conn, user_id, original, form, today, body.category, body.file_hash)
    except expenses.InvalidCategory as e:
        raise HTTPException(status_code=422, detail=str(e))
    if checked.blocked:  # the browser disables Save too, but the server decides
        raise blocked_response(checked)
    expense_id = expenses.save(conn, user_id, checked, body.file_hash, body.always_use_category)
    return {"expense": public_expense(db.get_expense(conn, user_id, expense_id)), **expenses.report_review(checked)}


@router.get("/expenses")
def list_expenses(
    start: date | None = None,
    end: date | None = None,
    category: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=500, ge=1, le=1000),
    user_id: str = Depends(current_user),
    conn=Depends(get_conn),
) -> list[dict]:
    rows = db.list_expenses(conn, user_id, start and start.isoformat(), end and end.isoformat(), category, limit)
    return [public_expense(row) for row in rows]


def _owned(conn, user_id: str, expense_id: int) -> dict:
    """Another user's expense looks exactly like a missing one."""
    row = db.get_expense(conn, user_id, expense_id)
    if row is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return row


@router.get("/expenses/{expense_id}")
def get_expense(expense_id: int, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    row = _owned(conn, user_id, expense_id)
    extraction = row["extraction_json"]
    return {**public_expense(row), "extraction": redact_value(extraction) if extraction else None}


def _check_edit(conn, user_id: str, row: dict, body: ExpenseEdit) -> tuple[expenses.Review, confirm.FormValues]:
    changes = body.model_dump(exclude_unset=True)
    merged = {key: changes.get(key, row[key]) for key in ("merchant", "total", "subtotal", "tax", "tip", "payment_method", "note")}
    day = changes["date"] if changes.get("date") else date.fromisoformat(row["date"])
    form = confirm.FormValues(
        merged["merchant"] or "", day, merged["total"], merged["subtotal"], merged["tax"], merged["tip"],
        merged["payment_method"], merged["note"] or "",
    )
    today = expenses.resolve_today(body.client_today)
    try:
        return expenses.edit(conn, user_id, row, form, today, changes.get("category")), form
    except expenses.InvalidCategory as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/expenses/{expense_id}/validate")
def validate_edit(expense_id: int, body: ExpenseEdit, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    """Re-check edits to a saved expense, which isn't its own duplicate. Saves nothing."""
    checked, _ = _check_edit(conn, user_id, _owned(conn, user_id, expense_id), body)
    return expenses.report_review(checked)


@router.patch("/expenses/{expense_id}")
def edit_expense(expense_id: int, body: ExpenseEdit, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    checked, form = _check_edit(conn, user_id, _owned(conn, user_id, expense_id), body)
    if checked.blocked:
        raise blocked_response(checked)
    db.update_expense(conn, user_id, expense_id, {
        "merchant": checked.edited.merchant or confirm.UNKNOWN_MERCHANT,
        "date": checked.edited.date,
        "total": round(checked.edited.total, 2),
        "subtotal": checked.edited.subtotal,
        "tax": checked.edited.tax,
        "tip": checked.edited.tip,
        "payment_method": checked.edited.payment_method,
        "note": form.note.strip() or None,
        "category": checked.category,
        "category_source": checked.category_source,
    })
    if body.always_use_category and checked.edited.merchant and checked.category_source == expenses.SOURCE_MANUAL:
        db.set_override(conn, user_id, checked.edited.merchant, checked.category)
    return {"expense": public_expense(db.get_expense(conn, user_id, expense_id)), **expenses.report_review(checked)}


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> None:
    if not db.delete_expense(conn, user_id, expense_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
