# SnapSpend

SnapSpend is a personal expense tracker for students. Upload a receipt, PDF or payment screenshot, check the details it read, and save it. The dashboard then shows your budget pace, where the money went, and plain-language insights. Nothing is saved until you confirm it, and the file itself is never stored.

**Hosted app:** _link added after deployment_

## Run it locally

You need [Docker](https://www.docker.com/) and no accounts of any kind.

```
docker compose up --build
```

Open http://localhost:5173. Local mode uses one built-in demo user with no sign-in, and all data stays on your computer. For a quick tour, go to **Settings → Load synthetic demo data**, then open **Dashboard**.

To simulate extraction instead of running OCR, use `EXTRACTION_BACKEND=mock docker compose up --build`. A "MOCK MODE" banner stays visible, and the result is chosen by file name (see `fixtures/mock_extractions/`).

### Without Docker

Requires Python 3.11+, Node 20+, Postgres and Tesseract.

| System | Install Tesseract |
|---|---|
| macOS | `brew install tesseract` |
| Ubuntu/Debian | `sudo apt install tesseract-ocr` |
| Windows | [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki), then set `TESSERACT_CMD` to its full path |

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
AUTH_MODE=local DATABASE_URL=<your local Postgres connection string> uvicorn api.main:app --port 8000
cd web && npm install && npm run dev
```

If Tesseract is missing, the app says so and everything except reading photos and scanned PDFs still works.

### From a phone

On the hosted app, sign in and tap **Take a photo or choose a file**. Your phone's normal file picker offers the camera. The layout is designed for phones first, with a bottom menu.

## How extraction works

1. **Get the text.** A PDF with a text layer is read directly. Scanned PDFs and photos go through Tesseract OCR, including iPhone HEIC photos.
2. **Parse it.** Rules find the merchant, date, amounts and payment method. Each field gets a confidence level and a reason, shown on the review screen.
3. **Validate.** Rules flag missing totals, future dates, amounts that don't add up, and so on. Only a missing or non-positive total, or a future date, blocks saving.
4. **Categorize.** Your past choice comes first, then the document type, then merchant keywords in `config/categories.json`.
5. **Confirm.** Nothing is saved until you review it and press Save.

If the text can't be read confidently, **no fields are filled in**. The app suggests a clearer photo or manual entry, because a wrong guess is worse than an empty form.

## Accounts and data separation

Hosted mode uses Supabase Auth with email and password, and optionally Google. The React app sends a token with each request, and the API verifies its signature, expiry, issuer, audience and role. The user always comes from the verified token, never from the request.

Users are kept apart twice. Every query filters by user, and Postgres row-level security enforces the same rule, because each request runs under a restricted role limited to that user's rows. Another user's expense returns 404. If sign-in is missing or misconfigured, the API refuses all data requests.

**Privacy:** uploads are read in memory and discarded. Only the confirmed details, the extracted text with card numbers and long digit runs masked, and a file hash for spotting duplicates are kept. Logs never contain receipt data or tokens. Settings can permanently delete your account and data.

## Hosted setup

1. Create a Supabase project with the **Data API off**, since the browser never queries the database directly. Set the Site URL to your front end's address under **Authentication → URL Configuration**.
2. Deploy the API from the `Dockerfile` with these settings: `AUTH_MODE=supabase`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `DATABASE_URL`. Use a direct or session-mode connection, not transaction mode, because each request sets a role on its connection.
3. Deploy `web/` as a static site with these settings: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`, and `VITE_AUTH_GOOGLE=true` if Google is enabled. Point the `/api` rewrite in `web/vercel.json` at your API.
4. For Google sign-in, create an OAuth client in Google Cloud and enable the provider in Supabase.

Secrets stay in your host's settings. See `.env.example` for every option.

## Sample files and expected results

Everything in `fixtures/sample_receipts/` is generated and made up. Rebuild it with `python -m scripts.generate_sample_receipts`.

| File | Demo scenario | Expected result |
|---|---|---|
| `grocery_photo.png` | Photo | Sample Grocer, total $11.88, subtotal $11.00, tax $0.88 |
| `restaurant_digital.pdf` | Digital PDF | Text read directly, total $19.20 including a $3.00 tip |
| `venmo_screenshot.png` | Payment screenshot | Sam Example as merchant, $45.00, "Transfers to People" |
| `amounts_dont_add_up.png` | Inconsistent amounts | Total $40.00 with a warning; saving is still allowed |
| `blurry_photo.png` | Unreadable photo | Nothing filled in; clearer photo or manual entry offered |
| `not_a_receipt.png` | Not a receipt | Nothing filled in; clearer photo or manual entry offered |

To see the duplicate warning, save any of these and upload the same file again.

## Tests

```
docker compose up -d db
pytest                 # API and core logic, against real Postgres
cd web && npx playwright install chromium && ./e2e/run.sh
```

The browser tests use a throwaway stack with its own database and mock receipts, on desktop and phone sizes. Your data isn't touched.

## What's real, synthetic and deferred

- **Implemented:** upload, OCR and PDF reading, review and confirm, validation, duplicates, categories, expense list, dashboard with four insight types, budget cycles, accounts, data separation and account deletion.
- **Synthetic:** demo data is labeled wherever it appears and can be hidden on the dashboard. **Settings → Remove synthetic demo data** deletes only those rows.
- **Mocked:** only when `EXTRACTION_BACKEND=mock` is set, always with a visible banner.
- **Deferred:** viewing and searching items on a bill, AI vision for harder photos, refunds, bank CSV import, other currencies, and roommate splits.

## Dependencies

Beyond the core stack (React, TypeScript, Vite, Tailwind, FastAPI, Postgres):

| Dependency | Why |
|---|---|
| `psycopg` | Plain SQL with no ORM |
| Pillow, `pillow-heif`, `pdfplumber`, `pytesseract` | Reading images, iPhone photos and PDFs, and running OCR |
| pandas | Dashboard and insight calculations |
| PyJWT, `cryptography`, `httpx` | Verifying sign-in tokens, and removing a sign-in when an account is deleted |
| `@supabase/supabase-js` | Sign-in screens in the browser |
| `@fontsource-variable/inter` | The font, bundled so browsers don't contact a font service |
| pytest, Playwright | Tests |

Charts are hand-built with SVG and HTML, because Plotly would add megabytes to the app and is hard to fit to the design.

## Known limitations

- **OCR accuracy varies.** Borderline phone photos can read differently between Tesseract versions, and may fall back to manual entry. Line items are read but not shown yet.
- **USD only.** Every amount is treated as US dollars, including on receipts showing another currency symbol.
- **Expenses only.** Refunds and credits aren't tracked.
- **Upload limits are per server.** The rate limit is kept in memory, so it resets on restart.
- **Free hosting sleeps.** Free Supabase projects pause after a week of inactivity, and free API hosts can take a while to wake.
- **HEIC previews** only show in browsers that support them. The file is still read.

## Next steps

An AI vision backend for hard photos, bank CSV import, viewing and searching the items on a bill, refunds, line-item insights, other currencies, and roommate splits.

## Time, AI use and prior work

- **Time spent:** _to be filled in by the author_
- **How AI was used:** _to be confirmed by the author._ Built with Claude Code, working milestone by milestone from `SPEC.md`. Its output was checked with the automated tests, by running the app, and by the author testing it with real receipts on their own computer.
- **Prior work reused:** none outside the open-source dependencies listed above.
