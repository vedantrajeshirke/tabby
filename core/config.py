"""Environment-driven configuration and the Tesseract availability check."""
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "app.db"
CATEGORIES_PATH = ROOT / "config" / "categories.json"

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    extraction_backend: str
    tesseract_cmd: str
    ocr_min_confidence: float
    hosted_demo: bool = False


def load_config() -> Config:
    backend = os.getenv("EXTRACTION_BACKEND", "local").split("#")[0].strip().lower() or "local"
    cmd = os.getenv("TESSERACT_CMD", "").split("#")[0].strip()
    try:
        min_conf = float(os.getenv("OCR_MIN_CONFIDENCE", "50").split("#")[0].strip())
    except ValueError:
        min_conf = 50.0
    hosted = os.getenv("HOSTED_DEMO", "false").split("#")[0].strip().lower() == "true"
    return Config(backend, cmd, min_conf, hosted)


def find_tesseract(cfg: Config | None = None) -> str | None:
    """Return the path to the tesseract executable, or None if it isn't available."""
    cfg = cfg or load_config()
    if cfg.tesseract_cmd:
        return cfg.tesseract_cmd if Path(cfg.tesseract_cmd).exists() else None
    return shutil.which("tesseract")


TESSERACT_INSTALL_HELP = (
    "Mac: `brew install tesseract` · Linux: `sudo apt install tesseract-ocr` · "
    "Windows: install the UB Mannheim build and set `TESSERACT_CMD` in `.env`."
)
