"""Category decision: user override -> document type -> keyword rule -> Other."""
import json
import re
from pathlib import Path

from core.config import CATEGORIES_PATH

DEFAULT_CATEGORY = "Other"
TRANSFER_CATEGORY = "Transfers to People"
TOP_LINES = 10

SOURCE_LABELS = {
    "override": "your past choice",
    "doc_type": "document type",
    "rule": "merchant rule",
    "default": "default",
    "manual": "you",
}


def load_config(path: Path = CATEGORIES_PATH) -> dict:
    return json.loads(path.read_text())


def normalize_merchant(merchant: str) -> str:
    """Uppercase, collapse whitespace, and strip card prefixes and trailing store numbers."""
    key = " ".join(merchant.upper().split())
    key = re.sub(r"^(SQ ?\*|TST ?\*)\s*", "", key)
    return re.sub(r"\s*#\s*\d+$", "", key)


def _matching_category(text: str, rules: list[dict]) -> str | None:
    """Rules run in file order, so specific ones (UBER EATS) must come before general ones (UBER)."""
    for rule in rules:
        for keyword in rule["keywords"]:
            if re.search(rf"\b{re.escape(keyword)}(?:'?S)?\b", text, re.I):
                return rule["category"]
    return None


def categorize(
    merchant: str | None,
    document_type: str | None,
    raw_text: str,
    overrides: dict[str, str],
    rules: list[dict],
) -> tuple[str, str]:
    """Return (category, category_source)."""
    if merchant:
        override = overrides.get(normalize_merchant(merchant))
        if override:
            return override, "override"
    if document_type == "payment_screenshot":
        return TRANSFER_CATEGORY, "doc_type"
    # The merchant is checked first so a stray word in the header can't outrank it.
    top_text = "\n".join(raw_text.splitlines()[:TOP_LINES])
    for text in (merchant or "", top_text):
        category = _matching_category(text, rules)
        if category:
            return category, "rule"
    return DEFAULT_CATEGORY, "default"
