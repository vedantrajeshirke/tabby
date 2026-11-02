from fastapi import APIRouter

from core.config import TESSERACT_INSTALL_HELP, find_tesseract, load_config

router = APIRouter()


@router.get("/status")
def get_status() -> dict:
    cfg = load_config()
    available = find_tesseract(cfg) is not None
    return {
        "tesseract_available": available,
        "tesseract_help": None if available else TESSERACT_INSTALL_HELP,
        "mock_mode": cfg.extraction_backend == "mock",
        "auth_mode": cfg.auth_mode,
    }
