import asyncio
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from api import rate_limit
from api.deps import current_user, get_conn
from api.schemas import ExpenseForm
from core import confirm, expenses, files
from core.extraction import get_backend

router = APIRouter()
reading = asyncio.Semaphore(1)  # OCR is heavy, so a small server reads one receipt at a time


async def read_upload(file: UploadFile) -> tuple[bytes, str]:
    """Read and check an upload, without reading far past the size limit."""
    data = await file.read(files.MAX_BYTES + 1)
    filename = file.filename or ""
    try:
        files.validate_upload(data, filename)
    except files.FileRejected as e:
        raise HTTPException(status_code=400, detail=str(e))
    return data, filename


@router.post("/extractions")
async def create_extraction(
    file: UploadFile = File(),
    client_today: date | None = Form(default=None),
    user_id: str = Depends(current_user),
    conn=Depends(get_conn),
) -> dict:
    """Read a file and report on it. The file is discarded; only its hash (and a HEIC preview) go back to the browser."""
    if not rate_limit.allow_upload(user_id):
        raise HTTPException(status_code=429, detail="That's a lot of uploads at once. Wait a minute, then try again.")
    data, filename = await read_upload(file)
    async with reading:  # off the event loop, so the server keeps answering while it reads
        extraction = await run_in_threadpool(get_backend().extract, data, filename)
        preview = await run_in_threadpool(files.browser_preview, data, filename)
    file_hash = files.file_hash(data)
    today = expenses.resolve_today(client_today)
    return {
        "extraction": extraction.to_dict(),
        "file_hash": file_hash,
        "preview": preview,
        "suggested_date": extraction.date or today.isoformat(),
        **expenses.review_upload(conn, user_id, extraction, file_hash, today),
    }


@router.post("/validate")
def validate_form(body: ExpenseForm, user_id: str = Depends(current_user), conn=Depends(get_conn)) -> dict:
    """Re-check edited form values. Saves nothing."""
    original = body.extraction.to_extraction() if body.extraction else None
    form = confirm.FormValues(
        body.merchant, body.date, body.total, body.subtotal, body.tax, body.tip, body.payment_method, body.note
    )
    try:
        checked = expenses.review(
            conn, user_id, original, form, expenses.resolve_today(body.client_today), body.category, body.file_hash
        )
    except expenses.InvalidCategory as e:
        raise HTTPException(status_code=422, detail=str(e))
    return expenses.report_review(checked)
