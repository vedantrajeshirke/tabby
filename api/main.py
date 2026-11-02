"""FastAPI entry point. Routes stay thin and call core/."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.routes import status
from core import db


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
async def no_store(request: Request, call_next):
    """API responses can hold personal data, so browsers and proxies must not keep them."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(status.router, prefix="/api")
