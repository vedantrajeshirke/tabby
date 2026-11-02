"""Rule-based parser: raw text -> Extraction. Pure functions only, no I/O."""
import re
from dataclasses import dataclass
from datetime import date

from core.models import Extraction, LineItem

MIN_ALNUM_CHARS = 20
FOOTER_LINES = 5
DEFAULT_MIN_CONFIDENCE = 50.0

# Spec amount pattern, plus guards so phone numbers, dotted dates and percentages don't count as money.
# A decimal comma ("$3,49") is accepted only next to a currency symbol, where it can't be a plain number.
AMOUNT_RE = re.compile(
    r"(?<![\d.])(?:[$€£₹]?\s?((?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})|[$€£₹]\s?(\d+,\d{2}))(?!\d)(?!\.\d)(?!\s?%)"
)

TOTAL_KEYWORDS = ["GRAND TOTAL", "AMOUNT DUE", "BALANCE DUE", "BALANCE TO PAY", "TOTAL", "AMOUNT PAID", "CHARGED", "BALANCE"]
TOTAL_EXCLUDE_RE = re.compile(r"SUB[\s-]?TOTAL|TOTAL (SAVINGS|SAVED|DISCOUNT|ITEMS|NUMBER|TAX)")
CARD_CHARGE_RE = re.compile(r"\b(CREDIT|DEBIT)\b")
CARD_CHARGE_EXCLUDE_RE = re.compile(r"REFUND|RETURN")
SUBTOTAL_RE = re.compile(r"\bSUB[\s-]?TOTAL\b")
TAX_RE = re.compile(r"\bTAX(?:ES|\d*)\b")
TAX_EXCLUDE_RE = re.compile(r"TOTAL|PRE-TAX|TAXABLE")
TIP_RE = re.compile(r"\b(TIP|GRATUITY)\b")
TIP_EXCLUDE_RE = re.compile(r"SUGGEST|GUIDE")

PAYMENT_APP_RE = re.compile(r"\b(VENMO|ZELLE|PAYPAL)\b", re.I)
PAYMENT_PHRASE_RE = re.compile(r"\b(?:paid to|sent to|you paid|you sent)\b[:\s]*(.*)", re.I)
CARD_RE = re.compile(r"\b(VISA|MASTERCARD|AMEX|DISCOVER|DEBIT|CREDIT)\b")
CASH_RE = re.compile(r"\bCASH\b(?! BACK)")

NON_ITEM_RE = re.compile(
    r"(?<![A-Z])(SUB[\s-]?TOTAL|TOTAL|TAX(?:ES|\d*)|TIP|GRATUITY|AMOUNT DUE|BALANCE|AMOUNT PAID|CHARGED|"
    r"VISA|MASTERCARD|AMEX|DISCOVER|DEBIT|CREDIT|CASH|CHANGE|VENMO|ZELLE|PAYPAL)\b"
)
BARCODE_PREFIX_RE = re.compile(r"^\W*\d{6,}\s+")
QTY_LINE_RE = re.compile(r"^\W*(\d+(?:\.\d+)?)\s*@\s*\$?\s?(\d+\.\d{2})")
QTY_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:@|[xX]\b)\s*(?:\$?\s?(\d+\.\d{2}))?")

MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
MONTH = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
SLASH_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b")
DASH_DATE_RE = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b")  # 4-digit year only; shorter runs are usually IDs
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
MONTH_FIRST_RE = re.compile(rf"\b{MONTH}\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
DAY_FIRST_RE = re.compile(rf"\b(\d{{1,2}})\s+{MONTH}\.?,?\s+(\d{{4}})\b", re.I)

PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}")
URL_RE = re.compile(r"https?:|www\.|\.(com|org|net)\b", re.I)
STREET_RE = re.compile(
    r"^\d+\s+.*\b(ST|STREET|AVE|AVENUE|RD|ROAD|BLVD|BOULEVARD|DR|DRIVE|LN|LANE|WAY|HWY|HIGHWAY|CT|COURT|PL|PLACE|PKWY|SUITE)\b\.?",
    re.I,
)
CITY_STATE_ZIP_RE = re.compile(r"\b[A-Z]{2}\s+\d{5}\b", re.I)
LEADING_NUMBER_RE = re.compile(r"\d{3,}\s")  # usually an address even without a street word
GENERIC_MERCHANT_RE = re.compile(r"\b(RECEIPT|WELCOME|THANK YOU|INVOICE|ORDER)\b", re.I)


@dataclass
class Amount:
    value: float
    negative: bool
    start: int
    end: int


def find_amounts(line: str) -> list[Amount]:
    amounts = []
    for m in AMOUNT_RE.finditer(line):
        before = line[: m.start()].rstrip()
        after = line[m.end() :].lstrip()
        signed = before.endswith(("-", "−", "(")) and not (len(before) > 1 and before[-2].isalnum())
        negative = signed or after.startswith(("-", ")"))
        value = m.group(1).replace(",", "") if m.group(1) else m.group(2).replace(",", ".")
        amounts.append(Amount(float(value), negative, m.start(), m.end()))
    return amounts


def _last_amount(line: str) -> Amount | None:
    amounts = find_amounts(line)
    return amounts[-1] if amounts else None


def _found(line: str) -> str:
    return f"found on line '{line}'"


def _title_case(text: str) -> str:
    return re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", lambda m: m.group(0).capitalize(), text).strip(" ;:,.-|~")


def split_lines(text: str) -> list[str]:
    return [line.strip().replace("’", "'") for line in text.splitlines() if line.strip()]


def _can_rescue(lines: list[str]) -> bool:
    """Low-confidence text is still worth confirming if it has a total line and a date."""
    return parse_total(lines)[1] in ("high", "medium") and bool(find_dates("\n".join(lines)))


def classify_document(lines: list[str], text_confidence: float, min_confidence: float) -> tuple[str, str]:
    text = "\n".join(lines)
    if text_confidence < min_confidence and not _can_rescue(lines):
        return "unreadable", f"text confidence {text_confidence:.0f} is below the minimum of {min_confidence:.0f}"
    if sum(ch.isalnum() for ch in text) < MIN_ALNUM_CHARS:
        return "unreadable", "too little text was found"
    if PAYMENT_APP_RE.search(text) and PAYMENT_PHRASE_RE.search(text):
        return "payment_screenshot", "payment app name and a payment phrase were found"
    if not any(find_amounts(line) for line in lines):
        return "not_an_expense", "readable text, but no amounts were found"
    return "receipt", "readable text with amounts"


def parse_total(lines: list[str]) -> tuple[float | None, str | None, str, int | None]:
    """Return (total, confidence, reason, line index)."""
    for keyword in TOTAL_KEYWORDS:
        pattern = re.compile(rf"(?<![A-Z]){keyword}\b")  # OCR can glue digits on: "6BALANCE"
        for i in range(len(lines) - 1, -1, -1):
            upper = lines[i].upper()
            if not pattern.search(upper) or TOTAL_EXCLUDE_RE.search(upper):
                continue
            amount = _last_amount(lines[i])
            # A zero "BALANCE DUE 0.00" after payment is not the amount of the purchase.
            if amount and not amount.negative and amount.value > 0:
                return amount.value, "high", _found(lines[i]), i
    for i in range(len(lines) - 1, -1, -1):  # "Credit $36.94" is the amount charged to the card
        upper = lines[i].upper()
        if not CARD_CHARGE_RE.search(upper) or CARD_CHARGE_EXCLUDE_RE.search(upper):
            continue
        amount = _last_amount(lines[i])
        if amount and not amount.negative and amount.value > 0:
            return amount.value, "medium", f"no total line found; used the card charge, {_found(lines[i])}", i
    positive = [a.value for line in lines for a in find_amounts(line) if not a.negative]
    if positive:
        return max(positive), "low", "no total line found; used the largest amount in the document", None
    return None, None, "no total found", None


def parse_subtotal(lines: list[str]) -> tuple[float | None, str, int | None]:
    for i, line in enumerate(lines):
        if SUBTOTAL_RE.search(line.upper()):
            amount = _last_amount(line)
            if amount:
                return amount.value, _found(line), i
    return None, "no subtotal found", None


def parse_tax(lines: list[str]) -> tuple[float | None, str]:
    matched = []
    for line in lines:
        upper = line.upper()
        if TAX_RE.search(upper) and not TAX_EXCLUDE_RE.search(upper) and not SUBTOTAL_RE.search(upper):
            amount = _last_amount(line)
            if amount and not amount.negative:
                matched.append((line, amount.value))
    if not matched:
        return None, "no tax found"
    reason = "; ".join(_found(line) for line, _ in matched)
    return round(sum(value for _, value in matched), 2), reason


def parse_tip(lines: list[str]) -> tuple[float | None, str]:
    for line in lines:
        upper = line.upper()
        if TIP_RE.search(upper) and not TIP_EXCLUDE_RE.search(upper):
            amount = _last_amount(line)
            if amount and not amount.negative:
                return amount.value, _found(line)
    return None, "no tip found"


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_dates(text: str) -> list[date]:
    """All valid dates in document order. Slashed dates are read month-first (US)."""
    found: list[tuple[int, date | None]] = []
    for m in SLASH_DATE_RE.finditer(text):
        year = int(m.group(3))
        found.append((m.start(), _safe_date(year if year >= 100 else 2000 + year, int(m.group(1)), int(m.group(2)))))
    for m in DASH_DATE_RE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))))
    for m in ISO_DATE_RE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
    for m in MONTH_FIRST_RE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))))
    for m in DAY_FIRST_RE.finditer(text):
        found.append((m.start(), _safe_date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))))
    return [d for _, d in sorted(found, key=lambda pair: pair[0]) if d]


def parse_date(text: str) -> tuple[str | None, str | None, str]:
    dates = find_dates(text)
    if not dates:
        return None, None, "no date found"
    if len(set(dates)) == 1:
        return dates[0].isoformat(), "high", f"found one date: {dates[0].isoformat()}"
    return dates[0].isoformat(), "medium", f"found {len(set(dates))} different dates; used the first"


def _keyword_merchant(lines: list[str], keywords) -> tuple[str, str] | None:
    """Return (keyword, line) for the longest keyword found, so UBER EATS wins over UBER."""
    for keyword in sorted(keywords, key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(keyword)}(?:'?S)?\b", re.I)
        for line in lines:
            if pattern.search(line):
                return keyword, line
    return None


def _is_merchant_candidate(line: str) -> bool:
    if sum(ch.isalpha() for ch in line) < 3 or LEADING_NUMBER_RE.match(line):
        return False
    if find_amounts(line) or find_dates(line):
        return False
    bad_patterns = (PHONE_RE, URL_RE, STREET_RE, CITY_STATE_ZIP_RE, GENERIC_MERCHANT_RE)
    return not any(p.search(line) for p in bad_patterns)


def parse_merchant(lines: list[str], keywords) -> tuple[str | None, str | None, str]:
    """Return (merchant, confidence, reason)."""
    match = _keyword_merchant(lines[:10], keywords)
    if match:
        return _title_case(match[0]), "high", f"known merchant keyword on line '{match[1]}'"
    match = _keyword_merchant(lines[-FOOTER_LINES:], keywords)  # the header is often misread
    if match:
        return _title_case(match[0]), "medium", f"known merchant keyword near the end, on line '{match[1]}'"
    for line in lines[:6]:
        if _is_merchant_candidate(line):
            return _title_case(line), "medium", f"first line that looks like a business name: '{line}'"
    return None, None, "no merchant found"


def parse_payment_method(text: str) -> tuple[str | None, str]:
    upper = text.upper()
    app = PAYMENT_APP_RE.search(upper)
    if app:
        return app.group(1).lower(), f"found '{app.group(1)}'"
    card = CARD_RE.search(upper)
    if card:
        return "card", f"found '{card.group(1)}'"
    if CASH_RE.search(upper):
        return "cash", "found 'CASH'"
    return None, "no payment method found"


def parse_currency(text: str) -> tuple[str, str, str]:
    """Return (currency, confidence, reason)."""
    upper = text.upper()
    for currency, pattern in (
        # Symbols must touch a number, because OCR noise often produces a stray one.
        ("EUR", r"€\s?\d|\bEUR\b"),
        ("GBP", r"£\s?\d|\bGBP\b"),
        ("INR", r"₹\s?\d|\bINR\b"),
        ("CAD", r"CA\$|\bCAD\b"),
    ):
        if re.search(pattern, upper):
            return currency, "high", f"found a {currency} symbol or code"
    if "$" in upper or re.search(r"\bUSD\b", upper):
        return "USD", "high", "found '$' or 'USD'"
    return "USD", "medium", "no currency marker found; assumed USD"


def _item_from_line(line: str, fallback_name: str = "") -> LineItem | None:
    amount = _last_amount(line)
    if not amount or not re.fullmatch(r"\s*[-)]?\s*[A-Za-z]?[\s|.,'’]*", line[amount.end :]):
        return None
    price = -amount.value if amount.negative else amount.value
    qty = QTY_RE.search(line)
    quantity = float(qty.group(1)) if qty else None
    if qty and qty.group(2) and amount.start < qty.end():
        # "MILK 2 @ 3.99" has no line total, so the only amount is the unit price.
        price = round(quantity * amount.value, 2)
        name_part = line[: qty.start()]
    else:
        name_part = QTY_RE.sub("", line[: amount.start])
    name = BARCODE_PREFIX_RE.sub("", name_part).strip(" -:.\t") or fallback_name
    return LineItem(name=name, quantity=quantity, price=price) if name else None


def _set_previous_quantity(items: list[LineItem], line: str) -> bool:
    """Handle "ONION 1.98" followed by "2 @ 0.99 ea": the quantity belongs to the item above."""
    m = QTY_LINE_RE.match(line)
    if not (m and items and items[-1].price is not None):
        return False
    quantity, unit = float(m.group(1)), float(m.group(2))
    if abs(quantity * unit - items[-1].price) > 0.01:
        return False
    items[-1].quantity = quantity
    return True


def parse_line_items(lines: list[str], end: int) -> list[LineItem]:
    """Parse item lines above `end`, the subtotal or total line."""
    items: list[LineItem] = []
    pending_name = ""  # name-only line, for receipts that put "3 @ 0.29 0.87" on the next line
    for line in lines[:end]:
        upper = line.upper()
        if NON_ITEM_RE.search(upper):
            pending_name = ""
            continue
        if not pending_name and _set_previous_quantity(items, line):
            continue
        letters = sum(ch.isalpha() for ch in line)
        if not find_amounts(line):
            pending_name = line if letters >= 2 else ""
            continue
        if letters >= 2:
            item = _item_from_line(line)
        elif QTY_RE.search(line) and pending_name:
            item = _item_from_line(line, fallback_name=pending_name)
        else:
            item = None
        if item and item.price != 0:
            items.append(item)
        pending_name = ""
    return items


def _clean_recipient(text: str) -> str:
    text = re.sub(r"^to\s+", "", text.strip(), flags=re.I)
    return text.strip(" -−:,.!(")


def _format_recipient(name: str) -> str:
    return name if name.startswith("@") else _title_case(name)


def parse_recipient(lines: list[str]) -> tuple[str | None, str]:
    for i, line in enumerate(lines):
        m = PAYMENT_PHRASE_RE.search(line)
        if not m:
            continue
        rest = m.group(1)
        amounts = find_amounts(rest)
        before = _clean_recipient(rest[: amounts[0].start] if amounts else rest)
        if any(ch.isalpha() for ch in before):
            return _format_recipient(before), _found(line)
        if amounts:  # "You sent $50.00 to Jane Doe"
            after = re.match(r"\s*to\s+(.+)", rest[amounts[0].end :], re.I)
            if after and any(ch.isalpha() for ch in after.group(1)):
                return _format_recipient(_clean_recipient(after.group(1))), _found(line)
        if i + 1 < len(lines) and not find_amounts(lines[i + 1]):  # recipient on its own line
            return _format_recipient(_clean_recipient(lines[i + 1])), _found(lines[i + 1])
    return None, "no recipient found"


def _set_field(extraction: Extraction, name: str, value, confidence: str | None, reason: str) -> None:
    setattr(extraction, name, value)
    extraction.field_reason[name] = reason
    if value is not None and confidence:
        extraction.field_confidence[name] = confidence


def _parse_shared_fields(extraction: Extraction, text: str) -> None:
    extraction_date, date_confidence, date_reason = parse_date(text)
    _set_field(extraction, "date", extraction_date, date_confidence, date_reason)
    currency, currency_confidence, currency_reason = parse_currency(text)
    _set_field(extraction, "currency", currency, currency_confidence, currency_reason)
    method, method_reason = parse_payment_method(text)
    _set_field(extraction, "payment_method", method, None, method_reason)


def _parse_payment(extraction: Extraction, lines: list[str]) -> None:
    recipient, recipient_reason = parse_recipient(lines)
    _set_field(extraction, "merchant", recipient, "high", recipient_reason)
    for line in lines:
        amounts = find_amounts(line)
        if amounts:  # Venmo shows a payment as "-$25.00", so the sign is dropped here.
            _set_field(extraction, "total", amounts[0].value, "high", f"first amount, {_found(line)}")
            return
    _set_field(extraction, "total", None, None, "no amount found")


def _parse_receipt(extraction: Extraction, lines: list[str], keywords) -> None:
    merchant, merchant_confidence, merchant_reason = parse_merchant(lines, keywords)
    _set_field(extraction, "merchant", merchant, merchant_confidence, merchant_reason)
    total, total_confidence, total_reason, total_line = parse_total(lines)
    _set_field(extraction, "total", total, total_confidence, total_reason)
    subtotal, subtotal_reason, subtotal_line = parse_subtotal(lines)
    _set_field(extraction, "subtotal", subtotal, "high", subtotal_reason)
    tax, tax_reason = parse_tax(lines)
    _set_field(extraction, "tax", tax, "high", tax_reason)
    tip, tip_reason = parse_tip(lines)
    _set_field(extraction, "tip", tip, "high", tip_reason)

    # Scan from the top: a merchant keyword can sit on an item line ("TARGET BAG"), so it can't mark the header.
    end = next((i for i in (subtotal_line, total_line) if i is not None), len(lines))
    extraction.line_items = parse_line_items(lines, end)
    extraction.field_reason["line_items"] = f"{len(extraction.line_items)} item lines found above the totals"


def _mark_rescued(extraction: Extraction, min_confidence: float) -> None:
    """OCR can misread digits at this quality, so everything found needs a human check."""
    extraction.field_reason["document_type"] = (
        f"text confidence {extraction.text_confidence:.0f} is below {min_confidence:.0f}, "
        "but a total line and a date were found"
    )
    for name in extraction.field_confidence:
        if name == "currency":  # read from a symbol, and the form has no currency field to correct
            continue
        extraction.field_confidence[name] = "low"
        extraction.field_reason[name] = f"{extraction.field_reason[name]} (low-quality scan, please check)"


def parse(
    text: str,
    text_source: str = "ocr",
    text_confidence: float = 100.0,
    merchant_keywords=(),
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> Extraction:
    lines = split_lines(text)
    document_type, reason = classify_document(lines, text_confidence, min_confidence)
    extraction = Extraction(
        document_type=document_type,
        text_source=text_source,
        text_confidence=text_confidence,
        raw_text=text,
        field_reason={"document_type": reason},
    )
    if document_type == "payment_screenshot":
        _parse_shared_fields(extraction, text)
        _parse_payment(extraction, lines)
    elif document_type == "receipt":
        _parse_shared_fields(extraction, text)
        _parse_receipt(extraction, lines, merchant_keywords)
    if document_type in ("receipt", "payment_screenshot") and text_confidence < min_confidence:
        _mark_rescued(extraction, min_confidence)
    return extraction
