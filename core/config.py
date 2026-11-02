"""Environment-driven configuration and the Tesseract availability check."""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES_PATH = ROOT / "config" / "categories.json"
LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"  # the built-in demo user in local mode

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    extraction_backend: str
    tesseract_cmd: str
    ocr_min_confidence: float
    auth_mode: str = "local"
    database_url: str = ""  # empty = use the standard PG* environment variables


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).split("#")[0].strip()


def load_config() -> Config:
    try:
        min_conf = float(_env("OCR_MIN_CONFIDENCE", "50"))
    except ValueError:
        min_conf = 50.0
    return Config(
        extraction_backend=_env("EXTRACTION_BACKEND", "local").lower() or "local",
        tesseract_cmd=_env("TESSERACT_CMD"),
        ocr_min_confidence=min_conf,
        auth_mode=_env("AUTH_MODE", "local").lower() or "local",
        database_url=os.getenv("DATABASE_URL", "").strip(),
    )


def find_tesseract(cfg: Config | None = None) -> str | None:
    """Return the path to the tesseract executable, or None if it isn't available."""
    cfg = cfg or load_config()
    if cfg.tesseract_cmd:
        return cfg.tesseract_cmd if Path(cfg.tesseract_cmd).exists() else None
    return shutil.which("tesseract")


TESSERACT_INSTALL_HELP = (
    "Mac: brew install tesseract. Linux: sudo apt install tesseract-ocr. "
    "Windows: install the UB Mannheim build and set TESSERACT_CMD in .env."
)
