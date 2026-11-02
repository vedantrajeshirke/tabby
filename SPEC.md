# SnapSpend — Project Spec

> **Working name:** SnapSpend
> **Type:** Personal expense tracker (case-study prototype)
> **Receipts:** images are read and then discarded. Only the expense details, masked extracted text and a file hash are kept.
> **Stack:** React + FastAPI + Postgres, with Supabase for hosted accounts
> **Time:** the brief asks for 2–4 hours. The owner has chosen to go past that, and the submission must state the real time spent.
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
- **Free, and private by default.** Extraction uses PDF text extraction, OCR and a rule-based parser, with no paid APIs. In local mode receipt data never leaves the device. The hosted app stores it in the user's own account, and says so plainly.
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
- Photo tips on the capture page (flat, bright, close up, receipt filling the frame)
- Validation checks with clear warnings/errors
- Duplicate detection
- Rule-based categorization with user overrides
- Confirm/edit screen, then save to the database
- Manual entry fallback
- Expense list (view, edit, delete)
- Dashboard (budget pace, category split, month-over-month by category, top 5, avg daily spend)
- Insights panel (top 3 computed insights, templated text)
- Settings (name, monthly budget, budget cycle start day)
- User accounts with saved data: sign-in, per-user separation, and deleting your own account and data
- A hosted app, plus a local mode that needs no accounts
- Synthetic seed data for past months, clearly labeled

### Out of scope (do NOT build)
- Bank connections or bank CSV import (listed as a future step)
- Sharing data between users, roles or admin screens
- Paid AI APIs in the MVP (an AI backend is a stretch goal, section 10)
- Email inbox parsing, forecasting, ML training, notifications, native mobile app
- Tax features
- Refunds or any money coming back: this project tracks expenses only (listed as a future step)
- Viewing or editing the items on a bill: each bill is saved as its total (listed as a future step). The parser still reads items, and they stay inside `extraction_json`, but the `line_items` table isn't written

---

## 3. Tech stack

| Concern | Choice | Notes |
|---|---|---|
| Front end | React, TypeScript, Vite, Tailwind | Phone-first. Charts are hand-built with SVG and HTML: Plotly would add megabytes to the app and is hard to fit to the design |
| Back end | Python 3.11+, FastAPI | Thin routes that call `core/` |
| Database | Postgres via `psycopg` | Plain SQL, no ORM. Supabase hosted, Docker locally |
| Accounts | Supabase Auth (Google and email/password) | Issues JWTs; the API verifies them |
| Images | Pillow + `pillow-heif` | HEIC support for iPhone photos |
| PDF text | `pdfplumber` | Text layer, and rendering pages for OCR |
| OCR | Tesseract via `pytesseract` | Installed in the API's Docker image |
| Data | pandas | Aggregations for dashboard and insights |
| Hosting | Vercel (front end), Docker on Render or Fly.io (API) | Choose after checking current free-tier terms |
| Tokens | PyJWT with `cryptography`, `httpx` | Verifying tokens, and removing a sign-in on account deletion |
| Sign-in screens | `@supabase/supabase-js` | Sign-in, resets and token refresh in the browser; PKCE keeps tokens out of URLs |
| Font | `@fontsource-variable/inter` | Bundled with the app, so browsers make no request to a font service |
| Tests | pytest (API and `core/`), Playwright (end to end) | `web/e2e/run.sh` uses a throwaway stack with mock receipts |

**Do not add other dependencies** without a clear reason noted in the README.

### Run modes
- **Local:** `docker compose up` starts the front end, API and Postgres. `AUTH_MODE=local` uses one built-in demo user with no sign-in. No external account of any kind is needed, as the brief requires.
- **Hosted:** `AUTH_MODE=supabase`. Every API request needs a valid JWT.

The API checks at startup that Tesseract is available. If it isn't, `GET /api/status` reports it, and the front end shows install instructions while everything else stays usable.

### Environment variables (`.env.example`)
```
EXTRACTION_BACKEND=local    # local | mock
TESSERACT_CMD=              # optional full path to the tesseract executable
OCR_MIN_CONFIDENCE=50       # mean word confidence below this = unreadable
AUTH_MODE=local             # local = demo user, no sign-in; if unset, sign-in is required
DATABASE_URL=               # Postgres connection string
SUPABASE_URL=               # hosted only
SUPABASE_SECRET_KEY=        # hosted only, API server only, never sent to the browser
SUPABASE_PUBLISHABLE_KEY=   # hosted only, public by design, used by the sign-in screen
AUTH_GOOGLE=                # true shows "Continue with Google", once it's enabled in Supabase
CORS_ORIGINS=               # the front end's address
```
Secrets are never committed. When `EXTRACTION_BACKEND=mock`, show a visible **"MOCK MODE — extraction is simulated"** banner on the capture page.

---

## 4. Project structure

```
snapspend/
├── api/
│   ├── main.py                # App setup, CORS, routers
│   ├── auth.py                # JWT verification → current user
│   └── routes/                # expenses, extractions, settings, dashboard, account
├── core/                      # Framework-free logic, kept from the Streamlit build
│   ├── db.py                  # Schema, CRUD; every query takes user_id
│   ├── models.py, files.py, ocr.py, parser.py, extraction.py
│   ├── validation.py, duplicates.py, categorize.py, confirm.py
│   ├── periods.py, insights.py
├── web/                       # React app: pages for sign-in, add expense, expenses, dashboard, settings
├── config/categories.json
├── fixtures/                  # ocr_text, mock_extractions, sample_receipts (generated), demo_files (gitignored)
├── scripts/seed_synthetic.py
├── tests/                     # pytest; web/e2e holds Playwright tests
├── docker-compose.yml, Dockerfile, .env.example, requirements.txt, README.md
```

### API
All routes need a signed-in user, apart from the status check. The user always comes from the token, never from the request body.

| Route | Purpose |
|---|---|
| `GET /api/status` | Tesseract available, mock mode, run mode |
| `POST /api/extractions` | Upload a file; returns the extraction, issues, suggested category and duplicate warnings. Keeps nothing, and the file is discarded |
| `POST /api/validate` | Re-check edited form values |
| `POST /api/expenses` | Save a confirmed expense. No file is sent |
| `GET /api/expenses`, `GET` / `PATCH` / `DELETE /api/expenses/{id}` | List with period and category filters, view, edit, delete |
| `POST /api/expenses/{id}/validate` | Re-check edits to a saved expense |
| `GET /api/periods` | The user's recent budget cycles |
| `GET /api/dashboard` | All dashboard numbers and insights, computed on the server |
| `GET` / `PUT /api/settings` | Name, budget, cycle start day |
| `POST` / `DELETE /api/demo-data` | Load or remove synthetic data |
| `DELETE /api/account` | Permanently delete the user's account and data |

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
   Saved to the database → visible in Expenses list, Dashboard, Insights
```

On mobile, use a standard file input that accepts images (phones offer "Take Photo" in the native picker). Do **not** rely on direct browser camera access.

---

## 6. Feature requirements

Priorities: **P0** = must have for the demo, **P1** = should have if time allows, **P2** = stretch / write up as next step.

### 6.1 Capture (P0)
- Accept `jpg`, `jpeg`, `png`, `webp`, `heic`, `pdf`. Max 10 MB. Reject other types with a clear message.
- Compute a SHA-256 hash of the **original bytes** for exact-duplicate detection.
- For PDFs, process up to the first 3 pages; concatenate their text.
- **The file is never stored.** The API reads it in memory and discards it. The browser shows its own local copy as the preview.
- An "Enter manually instead" button is always available and opens the same confirm form, empty.

### 6.2 Getting text (P0)

**PDFs (`files.py`)**
- Extract text with `pdfplumber`, preserving line breaks.
- If the extracted text has fewer than 20 alphanumeric characters, treat the PDF as having no text layer: render each page at 300 DPI (`page.to_image(resolution=300).original`) and send it through OCR.
- Text-layer extraction gets `source = "pdf_text"` and a text confidence of 100.

**Images (`ocr.py`)**
- If the words read confidently cover well under the whole image, run OCR again cropped to them, and keep whichever pass has the higher mean confidence. This removes the table or background around a photographed receipt.
- Preprocess: apply EXIF orientation → convert to grayscale → if the width is under 1200 px, upscale to ~1600 px wide (LANCZOS) → autocontrast. If the mean brightness is below 100 (a dark-mode screenshot), invert the image.
- Run `pytesseract.image_to_data(..., config="--psm 6", output_type=Output.DICT)`.
- Rebuild lines by grouping words on `(block_num, par_num, line_num)`.
- Compute the **mean word confidence** over words with `conf >= 0`.
- Return `OcrResult(text: str, lines: list[str], mean_confidence: float, source="ocr")`.
- Typical runtime should be a few seconds. The front end keeps the result while the user edits, so OCR doesn't re-run.

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
| `document_type` | `unreadable` if `text_confidence < OCR_MIN_CONFIDENCE` or < 20 alphanumeric chars. Nothing is filled in from low-confidence text: a wrong value that looks right is worse than asking again, so the user is offered a clearer photo or manual entry. `payment_screenshot` if it contains Venmo/Zelle/PayPal keywords plus a phrase like "You paid", "Paid to", "Sent to", "You sent". `not_an_expense` if readable but no amounts were found. Otherwise `receipt`. | — |
| `total` | Search lines **bottom-up** for, in priority order: `GRAND TOTAL`, `AMOUNT DUE`, `BALANCE DUE`, `BALANCE TO PAY`, `TOTAL`, `AMOUNT PAID`, `CHARGED`, `BALANCE`. Exclude lines containing `SUBTOTAL`, `SUB TOTAL`, `TOTAL SAVINGS`, `TOTAL ITEMS`, `TOTAL TAX`. Take the last amount on the matching line. | high if keyword-matched; otherwise a `CREDIT` / `DEBIT` line without `REFUND` / `RETURN` → **medium**; otherwise the largest amount in the document → **low** |
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
| V01 | `document_type` is `not_an_expense` | error | "Couldn't find any amounts, so this may not be a receipt. Upload a clearer photo or enter it manually." |
| V02 | `document_type` is `unreadable` | error | "Couldn't read this clearly enough to fill it in. Upload a clearer photo or enter it manually." |
| V03 | `total` missing | error (blocks save) | "Total amount is required." |
| V04 | `total` ≤ 0 | error (blocks save) | "Total must be greater than zero." |
| V05 | `date` missing | warning | "No date found; defaulting to today." (prefill today) |
| V06 | `date` in the future | error (blocks save) | "Date is in the future." |
| V07 | `date` > 365 days old | warning | "This expense is over a year old. Is the date right?" |
| V08 | `subtotal + tax + tip` ≠ `total` (tolerance $0.05) when subtotal and total are present | warning | "Subtotal + tax + tip = $X but total is $Y. Please check the amounts." |
| V10 | `currency` is not USD | warning | "Currency is EUR. Amounts are stored as-is; conversion isn't supported yet." |
| V11 | any `field_confidence` is `low` | warning | Highlight the field: "Please double-check the total." |
| V12 | `merchant` missing | warning | "Merchant not found; please add one." |

**Errors** marked "blocks save" disable the Save button until fixed. V01/V02 show the manual entry option prominently. **Warnings** are shown in yellow but don't block saving.

### 6.6 Duplicate detection (P0)
- Duplicates are only ever checked against the same user's expenses.
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
- **Left:** preview of the file, from the browser's own copy.
- **Right:** editable form with merchant, date, total, category (dropdown), payment method, note, plus subtotal/tax/tip.
- Validation issues are listed above the form; low-confidence fields are visually marked, and each field shows its `field_reason` as help text.
- A collapsible **"Show extracted text"** section displays `raw_text` for transparency.
- Buttons: **Save expense** (disabled while blocking errors exist) and **Discard**.
- After saving, show a success message plus an "Add another" button that resets the page state.

### 6.9 Expenses list (P0)
- Table of expenses for the selected period: date, merchant, category, total, payment method, and a "synthetic" tag where applicable.
- Filters: period (budget cycle), category.
- Edit (reuses the confirm form) and delete (with a confirmation step).
- Open a row to see its details and extracted text.

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
`scripts/seed_synthetic.py` (also callable from Settings) generates ~3 previous periods, plus enough of the current one for the dashboard to show, of realistic student spending (groceries, cafes, delivery, transport, a rent transfer, subscriptions) with `is_synthetic = 1`. It must never touch real rows, and "Remove synthetic demo data" deletes only `is_synthetic = 1` rows. The UI labels synthetic rows and charts as described above. It only ever touches the current user's rows.

---

### 6.15 Accounts and data separation (P0)
- **Sign-in:** Supabase Auth, with Google and email/password. Supabase handles password storage, resets and token refresh. The React app sends the access token as a `Bearer` header, and the API verifies its signature against the project's public keys (ES256 or RS256; the legacy shared secret isn't supported), plus expiry, issuer, audience and role, on every request. If `AUTH_MODE` is unset or sign-in is misconfigured, the API refuses all data requests.
- **Separation, checked twice:** every query in `core/db.py` is scoped by a required `user_id` that comes from the verified token, and Postgres row-level security enforces the same rule: each request runs as a restricted role limited to that user's rows. The browser never queries the database directly. Requesting another user's expense returns 404.
- **Deleting an account** removes the user's rows and sign-in.
- **Reviewers:** sample receipts in `fixtures/sample_receipts/` are generated and contain no personal data. New accounts start empty and can load labeled synthetic data from Settings.
- **Availability:** free Supabase projects pause after a week of inactivity, and free API hosts may sleep. Wake and re-test the hosted app before any review.

---

## 7. Data model (Postgres)

```sql
CREATE TABLE IF NOT EXISTS expenses (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  merchant TEXT NOT NULL,
  date DATE NOT NULL,
  total NUMERIC(12,2) NOT NULL,       -- positive number, in `currency`
  currency TEXT NOT NULL DEFAULT 'USD',
  subtotal NUMERIC(12,2), tax NUMERIC(12,2), tip NUMERIC(12,2),
  category TEXT NOT NULL,
  category_source TEXT NOT NULL,      -- override | doc_type | rule | default | manual
  payment_method TEXT,
  document_type TEXT,                 -- from extraction, or 'manual'
  note TEXT,
  file_hash TEXT,                     -- SHA-256 of the upload, for duplicate warnings only
  extraction_json JSONB,              -- full extraction incl. raw_text and items, for traceability
  is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS merchant_overrides (
  user_id UUID NOT NULL,
  merchant_key TEXT NOT NULL,         -- normalized uppercase merchant
  category TEXT NOT NULL,
  PRIMARY KEY (user_id, merchant_key)
);

CREATE TABLE IF NOT EXISTS settings (
  user_id UUID PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  monthly_budget NUMERIC(12,2),
  cycle_start_day INTEGER NOT NULL DEFAULT 1 CHECK (cycle_start_day BETWEEN 1 AND 28)
);
CREATE INDEX IF NOT EXISTS idx_expenses_user_date ON expenses(user_id, date);
CREATE INDEX IF NOT EXISTS idx_expenses_user_hash ON expenses(user_id, file_hash);
```
Row-level security is enabled on all three tables, limiting each row to its owner. The `line_items` table is dropped, because items are future scope and stay inside `extraction_json`. Merchant normalization for matching: uppercase, trim, collapse whitespace, strip trailing store numbers (`#1234`) and common prefixes (`SQ *`, `TST*`).

---

## 8. Privacy and safety
- **Local mode:** everything stays on the device, and nothing is sent to external services. The capture page says: "Your receipts are processed and stored only on this device."
- **Hosted mode:** uploads are processed on the API server and discarded. Expense details and masked text are stored with Supabase. The capture page says: "Your receipt is read and then discarded. The details you save stay in your private account, and you can delete them at any time."
- Never log raw text, file contents or tokens; log errors only.
- **Keep less:** images and PDFs are never stored, which also keeps their metadata (real iPhone photos contain GPS) and any printed card digits off the server. Before text is stored, mask card numbers, long digit runs, and login or password lines.
- **Never in logs or error reports:** receipt fields, merchants, amounts, emails, file names, tokens, signed links, or request bodies. Errors returned to the browser never include stack traces or internal details.
- **Browser:** API responses carry `Cache-Control: no-store`, tokens never appear in URLs, and a Content Security Policy limits what scripts can run. No third-party analytics, ads or error trackers. Signing out clears cached receipt data.
- **Never in the repo or images:** `.env` files, keys, real receipts and databases. `.gitignore` and `.dockerignore` both exclude them, and a test fails if a tracked file breaks this rule.
- **Before the first push:** remove the personal email from commit history (use GitHub's private noreply address), and scan the full history for secrets.
- **Demos:** the video and hosted demos use only generated sample receipts and synthetic data, with no real account details or keys on screen.
- HTTPS everywhere in hosted mode. The API accepts requests from the front end's address only, and limits upload rate per user.
- Secrets live in the host's settings and never in git or the browser, apart from Supabase's public anon key.

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
- `validation.py`: each rule V01–V12 (V09 removed) has at least one test, including tolerance edges for V08.
- `categorize.py`: override beats doc type beats rule beats default; `UBER EATS` → Food Delivery, not Transport.
- `duplicates.py`: exact hash match; likely match on the same total, date and merchant; no false positive for the same merchant on a different date.
- `periods.py`: cycle start day 1 and 15; month boundaries; February.
- `insights.py`: each P0 generator fires and doesn't fire at its thresholds; ranking pins `budget_pace` and caps at 3; empty state.

- **Accounts and separation (must pass, run against real Postgres):** requests without a token, with an expired token, or with a bad signature get 401. User B can't read, edit or delete User A's expense. Duplicates, overrides, settings, dashboard totals and demo-data removal never cross users. Row-level security blocks access even when a query omits its filter. Deleting an account removes that user's rows and nobody else's.
- **API:** each route's success path and its helpful error paths; nothing is saved by `POST /api/extractions`.
- **End to end (Playwright):** upload → confirm → saved → visible in the list and dashboard, on desktop and phone sizes.

### Demo scenarios (document in the README)
1. **Representative (photo):** a grocery receipt photo → OCR → parsed fields with reasons → category from a rule → confirm → dashboard and insights update.
2. **Representative (PDF):** a digital receipt PDF → text extracted directly → confirm → saved.
3. **Payment screenshot:** a Venmo screenshot → recipient as merchant, "Transfers to People" as category.
4. **Difficult/invalid inputs:**
   - Blurry photo → low OCR confidence → V02 error, manual entry offered
   - Photo that isn't a receipt → V01 error
   - Receipt where the amounts don't add up → V08 warning, saving still allowed
   - The same file uploaded twice → duplicate warning

---

## 10. Build order (milestones)

**Done on the earlier Streamlit build:** M1 skeleton, M2 extraction, M3 validation/categorization/duplicates, M4 confirm-and-save logic. `core/` carries over; the Streamlit pages and `ui.py` are removed in M5 and remain in git history.

Work through these in order. Finish each milestone's acceptance criteria and run the tests before moving on. **Keep the app runnable after every milestone.**

| # | Milestone | Acceptance criteria |
|---|---|---|
| M5 | New foundation | Repo restructured, `docker compose up` runs React, FastAPI and Postgres, `core/db.py` on Postgres with `user_id`, existing tests passing |
| M6 | API | Extract, validate, save, list, edit, delete and settings routes, using the local demo user, with tests |
| M7 | Accounts and separation | Supabase JWT verification, row-level security, account deletion, the separation tests in section 9 passing |
| M8 | Add expense | Sign-in, phone-first upload and confirm screens, issues and field reasons, extracted text, manual entry, category override |
| M9 | Expenses list | Filter by period and category, edit, delete, view details and extracted text |
| M10 | Dashboard + insights | `periods.py`, all P0 dashboard sections, 4 P0 insight generators with tests, empty states |
| M11 | Settings + demo data | Settings page, seed script and buttons, synthetic labels and toggle, generated sample receipts |
| M12 | Deploy + finish | Hosted on Vercel and the chosen API host, Playwright flow passing, README complete |

**Never cut:** the confirm step, validation, field confidence/reasons, mock labeling, invalid-input handling, or the separation tests.

### Stretch (P2, only after M12)
- **Viewing and searching the items on a bill**, which the owner wants next: see what was bought on a given day, and search across bills. Stored text and items in `extraction_json` make this possible for past receipts too.
- **AI vision backend for more accuracy**, which is future scope and not paid for now. Testing on real receipts showed OCR results on borderline phone photos vary with the Tesseract version. (`EXTRACTION_BACKEND=claude` or `ollama`) implementing the same `ExtractionBackend` interface and returning the same `Extraction` model. Then a small script that runs every file in `fixtures/demo_files/` through both backends and reports field accuracy and seconds per file, for the case-study write-up.
- Item name normalization and the `repeat_item` insight.
- Home-currency display.

---

## 11. README must include
- What the app does, in 2–3 sentences, and a link to the hosted app
- Local setup with `docker compose up`, needing no accounts, and optional setup without Docker (including installing Tesseract per OS)
- Hosted setup: Supabase project, Google sign-in, environment variables, deployment
- How to use it from a phone
- How extraction works (PDF text → OCR → parser) and mock mode
- How accounts and data separation work
- Dependencies, sample data, example inputs and their expected outputs, and the demo scenarios from section 9
- What's implemented, what's synthetic or mocked and how to remove it, and what's deferred
- Time spent, how AI was used and how its output was checked, and any prior work reused
- Known limitations and next steps: AI vision backend, bank CSV import, viewing and searching the items on a bill, refunds, receipt line item insights, home-currency view, roommate splits

---

## 12. Instructions for Claude Code
- The case-study brief also requires: a working prototype, its source code, an explanation of up to four pages, and a 5–10 minute video walkthrough. The owner writes the explanation and records the video.
- Read this whole spec before writing code. Follow the milestone order in section 10.
- Ask before changing scope, adding dependencies, or deviating from the data model.
- Keep functions small and pure in `core/` (especially `parser.py`); keep API routes and React pages thin. No framework imports in `core/`.
- Every user-facing error message should say what happened **and** what to do next.

- Every number shown to the user must be computed in code from stored data.
- After each milestone, run the tests and give a 2–3 line summary of what's done and what's next.
