"""Shared page setup: banners and where this session's data lives."""
import shutil
import time
import uuid
from pathlib import Path

import streamlit as st

from core import db
from core.config import TESSERACT_INSTALL_HELP, find_tesseract, load_config

SESSION_MAX_AGE_SECONDS = 24 * 60 * 60
HOSTED_NOTICE = (
    "**Public demo.** Uploads are processed on this server and kept only for your session, which ends when "
    "you refresh or close the page. Please use the sample receipts, not real ones."
)
LOCAL_NOTICE = "Your receipts are processed and stored only on this device."


def _prune_old_sessions(root: Path) -> None:
    if not root.exists():
        return
    cutoff = time.time() - SESSION_MAX_AGE_SECONDS
    for session in root.iterdir():
        if session.is_dir() and session.stat().st_mtime < cutoff:
            shutil.rmtree(session, ignore_errors=True)


def data_dir() -> Path:
    """The shared data folder locally. Hosted, a private folder per browser session."""
    base = Path(db.DB_PATH).parent
    if not load_config().hosted_demo:
        return base
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid.uuid4().hex
        _prune_old_sessions(base / "sessions")
    return base / "sessions" / st.session_state.session_id


def db_path() -> Path:
    return data_dir() / Path(db.DB_PATH).name


def open_db():
    return db.connect(db_path())


def setup_page(title: str | None = None) -> None:
    st.set_page_config(page_title=f"{title} · SnapSpend" if title else "SnapSpend", page_icon="🧾", layout="wide")
    db.init_db(db_path())
    cfg = load_config()
    if cfg.hosted_demo:
        st.info(HOSTED_NOTICE)
    if find_tesseract(cfg) is None:
        st.warning(
            "**Tesseract OCR not found.** Photo and scanned-PDF reading is disabled; manual entry, "
            "PDFs with a text layer, and the dashboard still work. " + TESSERACT_INSTALL_HELP
        )
