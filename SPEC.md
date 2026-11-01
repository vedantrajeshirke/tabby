# SnapSpend — Project Spec

> **Working name:** SnapSpend
> **Type:** Personal expense tracker (case-study prototype)
> **Time budget:** ~4 hours of build time
> **Audience for this doc:** Claude Code (the implementer) and the project owner

---

## 1. Context

### The problem
Tracking expenses manually (e.g. in a spreadsheet) takes effort for every single purchase, so people stop doing it. The project owner is an international student in the US who wants to track spending but consistently skips logging expenses because it's tedious. Research on self-tracking abandonment lists "it's a hassle" and "felt lazy" as the top reasons people stop.

### The idea
Reduce logging an expense to **one upload (a receipt photo, a digital receipt PDF, or a payment screenshot) + one confirmation tap**. The app reads the document locally, validates what it found, and the human confirms. Then it shows a simple dashboard and a few plain-language insights that answer "am I on track?"

### What this prototype must prove (case-study requirements)
The prototype is part of a hiring case study. It **must**:
1. Complete one core workflow end to end: **receipt image or PDF → extracted expense → human confirms → saved → reflected in dashboard and insights.**
2. Handle a **representative input** (a typical receipt) and a **difficult/invalid input** (unreadable image, non-receipt, mismatched totals, duplicate) gracefully.
3. Run real logic (no static screens or pseudocode).
4. **Clearly label** anything synthetic or mocked in the UI.

### Design principles
- **Local and free.** Extraction runs on the user's machine using PDF text extraction, OCR, and a rule-based parser. No paid APIs, and receipt data never leaves the device.
- **Explainable.** Every extracted field has a confidence level and a reason, and every number in the dashboard and insights is computed in code.
- **The human confirms.** Nothing is saved without the user reviewing it.
- **Fail loudly and helpfully.** Invalid input produces a clear message and a path forward (retry or manual entry), never a crash or silent bad data.
- **Swappable extraction.** Extraction sits behind one interface so an AI vision backend can be added later without touching the rest of the app.
- **Simple over clever.** This is a 4-hour prototype. Prefer the simplest thing that works.

---

## 2. Scope

### In scope (MVP)
- Upload a receipt photo, a digital receipt PDF, or a payment/order screenshot
- Local extraction: PDF text layer → OCR fallback → rule-based parser with per-field confidence
- Mock extraction mode for development and tests
- Validation checks with clear warnings/errors
- Duplicate detection
- Rule-based categorization with user overrides
- Confirm/edit screen, then save to local SQLite
- Manual entry fallback
- Expense list (view, edit, delete)
- Dashboard (budget pace, category split, month-over-month by category, top 5, avg daily spend)
- Insights panel (top 3 computed insights, templated text)
- Settings (name, monthly budget, budget cycle start day)
- Synthetic seed data for past months, clearly labeled

### Out of scope (do NOT build)
- User accounts / authentication / multi-user
- Bank connections or bank CSV import (listed as a future step)
- Cloud database or deployment infrastructure
- Paid AI APIs in the MVP (an AI backend is a stretch goal, section 10)
- Email inbox parsing, forecasting, ML training, notifications, native mobile app
- Tax features

---

## 3. Tech stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| UI | Streamlit (multipage) | Works in a phone browser too |
| Storage | SQLite (`data/app.db`) | Via `sqlite3` stdlib; no ORM |
| Images | Pillow + `pillow-heif` | HEIC support for iPhone photos |
| PDF text | `pdfplumber` | Text layer extraction; `page.to_image()` to render pages for OCR when there's no text layer |
| OCR | Tesseract via `pytesseract` | Requires the Tesseract binary installed on the system |
| Data | pandas | Aggregations for dashboard/insights |
| Charts | Plotly | |
| Config | python-dotenv | `.env` for settings |
| Tests | pytest | |

**Do not add other dependencies** without a clear reason noted in the README.

### System requirement
Tesseract must be installed:
- Mac: `brew install tesseract`
- Windows: install from the Tesseract installer (UB Mannheim build) and set `TESSERACT_CMD` in `.env` if it isn't on PATH
- Linux: `sudo apt install tesseract-ocr`

On startup, check that Tesseract is available. If not, show a clear banner with install instructions and keep the rest of the app usable (manual entry, PDFs with text layers, dashboard).

### Environment variables (`.env.example`)
```
EXTRACTION_BACKEND=local    # local | mock
TESSERACT_CMD=              # optional full path to the tesseract executable
OCR_MIN_CONFIDENCE=50       # mean word confidence below this = unreadable
```
When `EXTRACTION_BACKEND=mock`, show a visible **"MOCK MODE — extraction is simulated"** banner on the capture page.

---

## 4. Project structure

```
snapspend/
├── app.py                     # Entry point, navigation, global banners
├── pages/
│   ├── 1_Add_Expense.py       # Capture → extract → confirm → save
│   ├── 2_Expenses.py          # List, filter, edit, delete
│   ├── 3_Dashboard.py         # Charts + insights
│   └── 4_Settings.py          # Name, budget, cycle start day, demo data
├── core/
│   ├── db.py                  # Schema creation, CRUD
│   ├── models.py              # Dataclasses: Expense, LineItem, Extraction, ValidationIssue
│   ├── files.py               # Load image/PDF, EXIF-rotate, hash, render PDF pages
│   ├── ocr.py                 # Image preprocessing + Tesseract (text, lines, confidence)
│   ├── parser.py              # Raw text → Extraction (rule-based, with confidences)
│   ├── extraction.py          # Backend interface: local | mock
│   ├── validation.py          # Validation rules → list of issues
│   ├── duplicates.py          # Duplicate detection
│   ├── categorize.py          # Override → rule → default
│   ├── periods.py             # Budget-cycle period helpers
│   └── insights.py            # Insight generators, ranking, templates
├── config/
│   └── categories.json        # Category list + merchant keyword rules
├── fixtures/
│   ├── ocr_text/              # Raw receipt text samples for parser tests
│   ├── mock_extractions/      # JSON results used in mock mode
│   └── demo_files/            # Sample images/PDFs for the demo (owner adds real ones)
├── scripts/
│   └── seed_synthetic.py      # Seeds past months with synthetic data
├── data/                      # gitignored: app.db, saved files
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

---

## 5. Core user flow

```
[Add Expense page]
   Upload image / PDF (or "Enter manually")
        │
        ▼
   Load file, compute hash ──► exact-duplicate warning if seen before
        │
        ▼
   Get text:
     PDF with text layer → pdfplumber text (confidence: high)
     PDF without text    → render page → OCR
     Image               → preprocess → OCR (text + mean word confidence)
        │
        ▼
   Parser: text → structured fields + per-field confidence
        │
        ▼
   Validation rules → errors / warnings
        │
        ▼
   Categorization (override → rule → "Other")
        │
        ▼
   Confirm screen: preview | editable prefilled form | warnings | "show extracted text"
        │
   [Save]  or  [Discard]
        │
        ▼
   Saved to SQLite → visible in Expenses list, Dashboard, Insights
```

On mobile, use `st.file_uploader` (phones offer "Take Photo" in the native picker). Do **not** rely on `st.camera_input`, because browser camera access requires HTTPS when not on localhost.

---

## 6. Feature requirements

Priorities: **P0** = must have for the demo, **P1** = should have if time allows, **P2** = stretch / write up as next step.

### 6.1 Capture (P0)
- Accept `jpg`, `jpeg`, `png`, `webp`, `heic`, `pdf`. Max 10 MB. Reject other types with a clear message.
- Compute a SHA-256 hash of the **original bytes** for exact-duplicate detection.
- For PDFs, process up to the first 3 pages; concatenate their text.
- Save the original file to `data/files/<hash>.<ext>` only after the user confirms.
- An "Enter manually instead" button is always available and opens the same confirm form, empty.

### 6.2 Getting text (P0)

**PDFs (`files.py`)**
- Extract text with `pdfplumber`, preserving line breaks.
- If the extracted text has fewer than 20 alphanumeric characters, treat the PDF as having no text layer: render each page at 300 DPI (`page.to_image(resolution=300).original`) and send it through OCR.
- Text-layer extraction gets `source = "pdf_text"` and a text confidence of 100.

**Images (`ocr.py`)**
- Preprocess: apply EXIF orientation → convert to grayscale → if the width is under 1200 px, upscale to ~1600 px wide (LANCZOS) → autocontrast. If the mean brightness is below 100 (a dark-mode screenshot), invert the image.
- Run `pytesseract.image_to_data(..., config="--psm 6", output_type=Output.DICT)`.
- Rebuild lines by grouping words on `(block_num, par_num, line_num)`.
- Compute the **mean word confidence** over words with `conf >= 0`.
- Return `OcrResult(text: str, lines: list[str], mean_confidence: float, source="ocr")`.
- Typical runtime should be a few seconds. Cache results by file hash in `st.session_state` so Streamlit reruns don't re-run OCR.

### 6.3 Parser (P0)
`parser.py` turns raw text into an `Extraction`. It must be a set of **pure functions** with no I/O, so they're easy to unit test against `fixtures/ocr_text/*.txt`.

**Extraction model:**
```json
{
  "document_type": "receipt | payment_screenshot | not_an_expense | unreadable",
  "merchant": "string | null",
  "date": "YYYY-MM-DD | null",
  "currency": "USD | EUR | GBP | INR | CAD | ... | null",
  "subtotal": "number | null",
  "tax": "number | null",
  "tip": "number | null",
  "total": "number | null",
  "payment_method": "card | cash | venmo | zelle | paypal | other | null",
  "line_items": [{ "name": "string", "quantity": "number | null", "price": "number | null" }],
  "field_confidence": { "merchant": "high|medium|low", "date": "...", "total": "...", "subtotal": "...", "tax": "..." },
  "field_reason": { "total": "found on line 'TOTAL 23.47'", "...": "..." },
  "text_source": "pdf_text | ocr",
  "text_confidence": "number 0-100",
  "raw_text": "string"
}
```

**Amount pattern:** `\$?\s?(\d{1,3}(?:,\d{3})*|\d+)\.\d{2}` (strip `$` and commas; use the last amount on a line). Treat a trailing `-` or parentheses as negative (discount/refund lines) and exclude those from the total search.

**Field rules:**

| Field | Rule | Confidence |
|---|---|---|
| `document_type` | `unreadable` if `text_confidence < OCR_MIN_CONFIDENCE` or < 20 alphanumeric chars. `payment_screenshot` if it contains Venmo/Zelle/PayPal keywords plus a phrase like "You paid", "Paid to", "Sent to", "You sent". `not_an_expense` if readable but no amounts were found. Otherwise `receipt`. | — |
| `total` | Search lines **bottom-up** for, in priority order: `GRAND TOTAL`, `AMOUNT DUE`, `BALANCE DUE`, `TOTAL`, `AMOUNT PAID`, `CHARGED`. Exclude lines containing `SUBTOTAL`, `SUB TOTAL`, `TOTAL SAVINGS`, `TOTAL ITEMS`, `TOTAL TAX`. Take the last amount on the matching line. | high if keyword-matched; if nothing matches, fall back to the largest amount in the document → **low** |
| `subtotal` | Line containing `SUBTOTAL` / `SUB TOTAL` / `SUB-TOTAL` | high if found |
| `tax` | Sum of amounts on lines containing `TAX` (not `TOTAL`, not `PRE-TAX`, not `TAXABLE`) | high if found |
| `tip` | Line containing `TIP` or `GRATUITY` | high if found |
| `date` | Regex for `MM/DD/YYYY`, `MM/DD/YY`, `YYYY-MM-DD`, `Mon D, YYYY`, `Month D, YYYY`, `D Mon YYYY`. Assume US month-first for slashed dates. | high if exactly one distinct date; medium if several (use the first); null if none |
| `merchant` | 1) If any keyword from `categories.json` rules appears in the top 10 lines, use that merchant name → high. 2) Otherwise the first line in the top 6 that has ≥ 3 letters and isn't a phone number, URL, street address (starts with digits + street word), date, or a generic word (`RECEIPT`, `WELCOME`, `THANK YOU`, `INVOICE`, `ORDER`) → medium. Title-case the result. | as noted |
| `payment_method` | `VISA`/`MASTERCARD`/`AMEX`/`DISCOVER`/`DEBIT`/`CREDIT` → card; `CASH` → cash; `VENMO`/`ZELLE`/`PAYPAL` → that value | — |
| `currency` | `€`/`EUR`, `£`/`GBP`, `₹`/`INR`, `CA$`/`CAD`; `$` alone → USD; nothing → USD with medium confidence | — |
| `line_items` | Lines between the merchant header block and the subtotal line (or the total line if there's no subtotal) that contain ≥ 2 letters, end with an amount, and don't match any keyword above. Parse quantity from `2 @ 3.99`, `2 x`, or `2X` patterns. | medium |

**Payment screenshots:** `merchant` = the recipient name following "Paid to" / "Sent to" / "You paid" (up to the end of the line or the amount); `total` = the first amount; `line_items` = empty.

Every field records a short `field_reason` so the confirm screen can explain itself (e.g. "Total: found on line 'TOTAL 23.47'").

### 6.4 Extraction backend interface (P0)
```python
class ExtractionBackend(Protocol):
    def extract(self, file_bytes: bytes, filename: str) -> Extraction: ...
```
- `LocalBackend`: files.py → ocr.py (if needed) → parser.py
- `MockBackend`: returns a fixture from `fixtures/mock_extractions/`, chosen by matching the uploaded filename stem (e.g. `blurry.jpg` → `blurry.json`), otherwise `default.json`. Provide at least `default.json`, `blurry.json`, `not_receipt.json`, `mismatch.json` and `venmo.json`.
- The backend is selected by `EXTRACTION_BACKEND`. Any exception inside a backend is caught and turned into an `unreadable` extraction with a reason, so the page never crashes.

### 6.5 Validation (P0)
`validation.py` takes an extraction (or the edited form values) and returns a list of `ValidationIssue(code, severity, field, message)`. Re-run validation on the edited form values before saving.

| Code | Check | Severity | Message (example) |
|---|---|---|---|
| V01 | `document_type` is `not_an_expense` | error | "This doesn't look like a receipt or payment. Try another file or enter it manually." |
| V02 | `document_type` is `unreadable` | error | "Couldn't read this image clearly. Retake the photo or enter it manually." |
| V03 | `total` missing | error (blocks save) | "Total amount is required." |
| V04 | `total` ≤ 0 | error (blocks save) | "Total must be greater than zero." |
| V05 | `date` missing | warning | "No date found; defaulting to today." (prefill today) |
| V06 | `date` in the future | error (blocks save) | "Date is in the future." |
| V07 | `date` > 365 days old | warning | "This expense is over a year old. Is the date right?" |
| V08 | `subtotal + tax + tip` ≠ `total` (tolerance $0.05) when subtotal and total are present | warning | "Subtotal + tax + tip = $X but total is $Y. Please check the amounts." |
| V09 | sum of line item prices ≠ `subtotal` (tolerance $0.05) when both are present | warning | "Line items add up to $X, but subtotal is $Y." |
| V10 | `currency` is not USD | warning | "Currency is EUR. Amounts are stored as-is; conversion isn't supported yet." |
| V11 | any `field_confidence` is `low` | warning | Highlight the field: "Please double-check the total." |
| V12 | `merchant` missing | warning | "Merchant not found; please add one." |

**Errors** marked "blocks save" disable the Save button until fixed. V01/V02 show the manual entry option prominently. **Warnings** are shown in yellow but don't block saving.

### 6.6 Duplicate detection (P0)
- **Exact:** the file hash already exists in `expenses.file_hash` → warning: "You already added this file on <date>." with the option to continue anyway.
- **Likely:** an existing expense with the same total (±$0.01), the same date, and a merchant that matches case-insensitively → warning: "Looks similar to an expense you already saved." Show that expense's summary.

### 6.7 Categorization (P0)
`config/categories.json` holds the categories and merchant keyword rules:
```json
{
  "categories": ["Groceries", "Restaurants & Cafes", "Food Delivery", "Transport", "Rent & Utilities",
                 "Phone & Internet", "Subscriptions", "Shopping", "Education", "Health",
                 "Personal Care", "Entertainment", "Travel", "Transfers to People", "Other"],
  "rules": [
    { "keywords": ["TRADER JOE", "WHOLE FOODS", "SAFEWAY", "H MART", "ALDI"], "category": "Groceries" },
    { "keywords": ["STARBUCKS", "CHIPOTLE", "CAFE", "COFFEE"], "category": "Restaurants & Cafes" },
    { "keywords": ["DOORDASH", "UBER EATS", "GRUBHUB"], "category": "Food Delivery" },
    { "keywords": ["UBER", "LYFT", "METRO", "TRANSIT"], "category": "Transport" },
    { "keywords": ["NETFLIX", "SPOTIFY", "ICLOUD"], "category": "Subscriptions" }
  ]
}
```
(Expand the rules sensibly; the owner will tune them.)

Order of decision:
1. **User override:** the `merchant_overrides` table (the user previously chose a category for this merchant).
2. **Document type:** `payment_screenshot` → `Transfers to People`.
3. **Keyword rule:** case-insensitive substring match on the merchant (and on the top lines of the raw text). More specific rules come first (e.g. `UBER EATS` before `UBER`).
4. **Default:** `Other`.

Store `category_source` (`override | doc_type | rule | default | manual`) and show it as a small label on the confirm screen (e.g. "Category from: your past choice"). When the user changes the category on save, offer a checkbox: **"Always use this category for <merchant>"** → write to `merchant_overrides`.

### 6.8 Confirm screen (P0)
Two-column layout (stacks on mobile):
- **Left:** file preview (image, or the rendered first page of a PDF).
- **Right:** editable form with merchant, date, total, category (dropdown), payment method, note, plus a collapsible line items table (editable) and subtotal/tax/tip.
- Validation issues are listed above the form; low-confidence fields are visually marked, and each field shows its `field_reason` as help text.
- A collapsible **"Show extracted text"** section displays `raw_text` for transparency.
- Buttons: **Save expense** (disabled while blocking errors exist) and **Discard**.
- After saving, show a success message plus an "Add another" button that resets the page state.

### 6.9 Expenses list (P0)
- Table of expenses for the selected period: date, merchant, category, total, payment method, and a "synthetic" tag where applicable.
- Filters: period (budget cycle), category.
- Edit (reuses the confirm form) and delete (with a confirmation step).
- Click a row to view its stored file.

### 6.10 Settings (P0)
- Display name (used in the insights greeting)
- Monthly budget (USD)
- Budget cycle start day (1–28, default 1). This supports allowance or stipend cycles that don't start on the 1st of the month.
- Demo data section: **"Load synthetic demo data"** and **"Remove synthetic demo data"** buttons.
- P1: home currency code + manual exchange rate (USD → home), used only for display.

### 6.11 Periods (P0)
`periods.py` provides:
- `current_period(today, cycle_start_day) -> (start_date, end_date)`
- `previous_period(...)`
- `days_elapsed`, `days_left`, `period_length`

All dashboard numbers and insights use budget-cycle periods, not hardcoded calendar months (with a start day of 1 these are identical to calendar months).

### 6.12 Dashboard (P0)
Shown top to bottom, for the current period:
1. **Budget pace card:** spent / budget, a progress bar, days left, **safe to spend per day** = `(budget − spent) / days_left`. If over budget, show the amount over in red. If no budget is set, prompt the user to set one in Settings.
2. **Insights panel** (see 6.13).
3. **Category split:** horizontal bar chart of spend by category, sorted descending, with amounts and percentages.
4. **Month-over-month by category:** grouped bar chart (current vs previous period) plus a small table showing the $ change and % change per category. Use a fair comparison (see below).
5. **Monthly total trend:** line chart of total spend over the last 6 periods.
6. **Top 5 expenses** this period: merchant, date, category, amount.
7. **Average daily spend** this period = spent / days_elapsed.

**Fair comparison rule:** when the current period is still in progress, compare it with the **same number of elapsed days** in the previous period (e.g. Nov 1–14 vs Oct 1–14), and label it that way.

Show a visible label **"Includes synthetic demo data"** on any chart whose data includes synthetic rows, plus a toggle "Hide synthetic data" (default: show).

**Empty state:** if there are fewer than 3 expenses in the current period, show a friendly message and a button to add an expense instead of empty charts.

### 6.13 Insights (P0: four generators; P1: the rest)
Each generator is a pure function that takes the expenses DataFrame and settings, and returns `Insight | None`:
```python
@dataclass
class Insight:
    type: str
    text: str          # rendered from a template
    score: float       # $ impact, used for ranking
    tone: str          # "neutral" | "warning" | "positive"
    data: dict         # the computed numbers used in the text
```

| Priority | Generator | Fires when | Template example |
|---|---|---|---|
| P0 | `budget_pace` | budget set and ≥ 3 days elapsed | "Hi {name}, you've spent ${spent} of your ${budget} budget with {days_left} days left — about ${safe_per_day}/day to stay on track." If the projected spend exceeds the budget: "At this pace you'll be about ${over} over budget." |
| P0 | `category_change` | a category changed by ≥ $20 and ≥ 20% vs the fair previous window | "Restaurants & Cafes: ${current} so far, ${diff} more than this point last month." |
| P0 | `frequent_merchant` | a merchant has ≥ 3 visits this period | "You've been to {merchant} {count} times this period (${total})." |
| P0 | `small_purchases` | ≥ 5 expenses under $10 totaling ≥ $25 | "Purchases under $10 added up to ${total} across {count} items." |
| P1 | `positive_change` | a category is down ≥ 20% and ≥ $20 | "Groceries are down ${diff} from this point last month. Nice." (tone: positive) |
| P1 | `top_category_share` | the top category is ≥ 30% of spend | "{category} is {pct}% of your spending this period." |
| P2 | `repeat_item` | an item name appears on ≥ 3 receipts | "{item} showed up on {count} receipts (${total})." (needs item name normalization) |

Ranking: `budget_pace` is always pinned first if it fires; the rest are sorted by `score` descending; show at most **3**. If fewer than 5 expenses exist in the period, show "Add a few more expenses to see insights." Never compare against a previous period that has no data. All numbers come from the generators.

### 6.14 Synthetic demo data (P0)
`scripts/seed_synthetic.py` (also callable from Settings) generates ~3 previous periods of realistic student spending (groceries, cafes, delivery, transport, a rent transfer, subscriptions) with `is_synthetic = 1`. It must never touch real rows, and "Remove synthetic demo data" deletes only `is_synthetic = 1` rows. The UI labels synthetic rows and charts as described above.

---

## 7. Data model (SQLite)

```sql
CREATE TABLE IF NOT EXISTS expenses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  merchant TEXT NOT NULL,
  date TEXT NOT NULL,                 -- YYYY-MM-DD
  total REAL NOT NULL,                -- positive number, in `currency`
  currency TEXT NOT NULL DEFAULT 'USD',
  subtotal REAL, tax REAL, tip REAL,
  category TEXT NOT NULL,
  category_source TEXT NOT NULL,      -- override | doc_type | rule | default | manual
  payment_method TEXT,
  document_type TEXT,                 -- from extraction, or 'manual'
  note TEXT,
  file_path TEXT,
  file_hash TEXT,
  extraction_json TEXT,               -- full extraction incl. raw_text, for traceability
  is_synthetic INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS line_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  quantity REAL,
  price REAL
);

CREATE TABLE IF NOT EXISTS merchant_overrides (
  merchant_key TEXT PRIMARY KEY,      -- normalized uppercase merchant
  category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_hash ON expenses(file_hash);
```
Enable `PRAGMA foreign_keys = ON`. Merchant normalization for matching: uppercase, trim, collapse whitespace, strip trailing store numbers (`#1234`) and common prefixes (`SQ *`, `TST*`).

---

## 8. Privacy and safety
- Everything runs locally. Files and data stay in `data/` (gitignored); nothing is sent to external services.
- Never log raw text or file contents; log errors only.
- Show a one-line note on the capture page: "Your receipts are processed and stored only on this device."

---

## 9. Testing

### Unit tests (pytest), which must pass
- `parser.py` (most important), using text fixtures in `fixtures/ocr_text/`:
  - a grocery receipt with SUBTOTAL, TAX and TOTAL lines → correct total, not the subtotal
  - a receipt with `TOTAL SAVINGS` and discount lines → those are ignored
  - a restaurant receipt with a tip line
  - multiple tax lines → summed
  - each supported date format; no date → null
  - merchant from a keyword rule vs. from the first-line heuristic; address and phone lines skipped
  - quantity patterns in line items
  - Venmo and Zelle screenshot text → recipient as merchant, document type `payment_screenshot`
  - text with no amounts → `not_an_expense`; too little text → `unreadable`
  - no total keyword → largest-amount fallback with `low` confidence
- `ocr.py`: preprocessing returns grayscale; inversion triggers for a dark image (no real OCR needed in this test).
- `files.py`: a PDF with a text layer returns text; the empty-text case triggers the render path (can mock pdfplumber).
- `validation.py`: each rule V01–V12 has at least one test, including tolerance edges for V08/V09.
- `categorize.py`: override beats doc type beats rule beats default; `UBER EATS` → Food Delivery, not Transport.
- `duplicates.py`: exact hash match; likely match on the same total, date and merchant; no false positive for the same merchant on a different date.
- `periods.py`: cycle start day 1 and 15; month boundaries; February.
- `insights.py`: each P0 generator fires and doesn't fire at its thresholds; ranking pins `budget_pace` and caps at 3; empty state.

### Demo scenarios (document in the README)
1. **Representative (photo):** a grocery receipt photo → OCR → parsed fields with reasons → category from a rule → confirm → dashboard and insights update.
2. **Representative (PDF):** a digital receipt PDF → text extracted directly → confirm → saved.
3. **Payment screenshot:** a Venmo screenshot → recipient as merchant, "Transfers to People" as category.
4. **Difficult/invalid inputs:**
   - Blurry photo → low OCR confidence → V02 error, manual entry offered
   - Photo that isn't a receipt → V01 error
   - Receipt where the amounts don't add up → V08/V09 warning, saving still allowed
   - The same file uploaded twice → duplicate warning

---

## 10. Build order (milestones)

Work through these in order. Finish each milestone's acceptance criteria and run the tests before moving on. **Keep the app runnable after every milestone.**

| # | Milestone | Acceptance criteria | ~Time |
|---|---|---|---|
| M1 | Skeleton | Project structure, requirements, `.env.example`, DB schema created on startup, multipage app runs with empty pages, settings save and load, Tesseract availability check with a banner | 20 min |
| M2 | Extraction | `files.py` (image + PDF loading, hashing, PDF text and render), `ocr.py`, `parser.py` with fixture-based tests passing, backend interface with local and mock backends | 75 min |
| M3 | Validate + categorize + duplicates | `validation.py`, `categorize.py`, `duplicates.py` with unit tests passing | 30 min |
| M4 | Confirm and save | Confirm screen with an editable form, issues and field reasons shown, extracted-text panel, Save disabled on blocking errors, manual entry, "always use this category" override, saved file | 30 min |
| M5 | Expenses list | Filter by period and category, edit, delete, view file | 15 min |
| M6 | Dashboard + insights | `periods.py`, all P0 dashboard sections, 4 P0 insight generators with tests, empty states | 45 min |
| M7 | Synthetic data + polish | Seed script and Settings buttons, synthetic labels/toggle, README with setup and demo scenarios | 15 min |

If time is running out, cut in this order: monthly trend line → expense list editing → line item editing → line item parsing (leave `line_items` empty). **Never cut:** the confirm step, validation, field confidence/reasons, mock labeling, or invalid-input handling.

### Stretch (P2, only after M7)
- **AI vision backend** (`EXTRACTION_BACKEND=claude` or `ollama`) implementing the same `ExtractionBackend` interface and returning the same `Extraction` model. Then a small script that runs every file in `fixtures/demo_files/` through both backends and reports field accuracy and seconds per file, for the case-study write-up.
- Item name normalization and the `repeat_item` insight.
- Home-currency display.

---

## 11. README must include
- What the app does, in 2–3 sentences
- Setup: install Tesseract (per OS), `python -m venv .venv`, `pip install -r requirements.txt`, copy `.env.example` to `.env`, `streamlit run app.py`
- How to use it from a phone on the same Wi-Fi (`streamlit run app.py --server.address 0.0.0.0`, then open the laptop's IP on port 8501 and use the upload button's "Take Photo" option)
- How extraction works (PDF text → OCR → parser) and mock mode
- The demo scenarios from section 9
- What's synthetic or mocked, and how to remove it
- Known limitations and next steps: AI vision backend, bank CSV import, receipt line item insights, home-currency view, roommate splits

---

## 12. Instructions for Claude Code
- Read this whole spec before writing code. Follow the milestone order in section 10.
- Ask before changing scope, adding dependencies, or deviating from the data model.
- Keep functions small and pure in `core/` (especially `parser.py`); keep Streamlit pages thin (UI only, calling `core/`).
- Cache extraction results by file hash in `st.session_state` so a Streamlit rerun doesn't redo OCR for the same file.
- Every user-facing error message should say what happened **and** what to do next.
- Every number shown to the user must be computed in code from stored data.
- After each milestone, run `pytest` and give a 2–3 line summary of what's done and what's next.
