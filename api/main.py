"""FastAPI entry point. Routes stay thin and call core/."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import account, dashboard, demo, expenses, extractions, settings, status
from api.schemas import invalid_fields_message
from core import db

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    with db.connect() as conn:
        db.init_db(conn)
    yield


# Interactive API docs are off, since the hosted API is public.
app = FastAPI(title="SnapSpend API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split("#")[0].split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["Authorization", "Content-Type"]
    )


@app.middleware("http")
async def protect_responses(request: Request, call_next):
    """Keep responses out of caches, and keep exception details out of logs and browsers."""
    try:
        response = await call_next(request)
    except Exception as e:  # database errors can quote row values, so only the type is logged
        log.error("Request failed: %s", type(e).__name__)
        response = JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError):
    """Replaces the default response, which echoes the submitted values."""
    message, fields = invalid_fields_message(exc.errors())
    return JSONResponse({"detail": message, "fields": fields}, status_code=422)


app.include_router(status.router, prefix="/api")
app.include_router(extractions.router, prefix="/api")
app.include_router(expenses.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(demo.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(account.router, prefix="/api")
