"""Masks sensitive details in extracted text before it's stored."""
import re

HIDDEN_LINE = "[line hidden]"
HIDDEN_NUMBER = "[number hidden]"

SENSITIVE_LINE_RE = re.compile(r"\b(user ?id|password|passcode|pin|auth(orization)?( code)?|aid|mid|tid)\b\s*[:;#]", re.I)
MASKED_CARD_RE = re.compile(r"[*xX#•]{1,}[ -]?\d{4}\b")
# 8+ digits in a row, or 12+ with separators. Dates (8 with dashes) and phone numbers (10) stay readable.
LONG_NUMBER_RE = re.compile(r"\d{8,}|\d(?:[ -]?\d){11,}")


def _redact_line(line: str) -> str:
    if SENSITIVE_LINE_RE.search(line):
        return HIDDEN_LINE
    return LONG_NUMBER_RE.sub(HIDDEN_NUMBER, MASKED_CARD_RE.sub("[card hidden]", line))


def redact_text(text: str) -> str:
    return "\n".join(_redact_line(line) for line in text.split("\n"))


def redact_value(value):
    """Redact every string in nested extraction data, such as raw text and field reasons."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value
