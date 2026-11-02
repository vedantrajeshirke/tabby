"""Dataclasses shared across the app. Extended in later milestones."""
from dataclasses import asdict, dataclass, field


@dataclass
class Settings:
    name: str = ""
    monthly_budget: float | None = None
    cycle_start_day: int = 1


@dataclass
class Expense:
    merchant: str
    date: str  # YYYY-MM-DD
    total: float
    category: str
    category_source: str  # override | doc_type | rule | default | manual
    currency: str = "USD"
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    payment_method: str | None = None
    document_type: str | None = None
    note: str | None = None
    file_path: str | None = None
    file_hash: str | None = None
    extraction_json: str | None = None
    is_synthetic: bool = False


@dataclass
class LineItem:
    name: str
    quantity: float | None = None
    price: float | None = None


@dataclass
class ValidationIssue:
    code: str
    severity: str  # error | warning
    field: str | None
    message: str


@dataclass
class Extraction:
    document_type: str  # receipt | payment_screenshot | not_an_expense | unreadable
    merchant: str | None = None
    date: str | None = None  # YYYY-MM-DD
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    tip: float | None = None
    total: float | None = None
    payment_method: str | None = None  # card | cash | venmo | zelle | paypal | other
    line_items: list[LineItem] = field(default_factory=list)
    field_confidence: dict[str, str] = field(default_factory=dict)  # only for fields that were found
    field_reason: dict[str, str] = field(default_factory=dict)
    text_source: str = "ocr"  # pdf_text | ocr
    text_confidence: float = 0.0
    raw_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Extraction":
        items = [LineItem(**item) for item in data.get("line_items", [])]
        return cls(**{**data, "line_items": items})
