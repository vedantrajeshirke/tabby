from datetime import date

import streamlit as st

import ui
from core import categorize, confirm, db, files
from core.config import load_config
from core.duplicates import find_duplicates
from core.extraction import get_backend
from core.validation import blocks_save, validate

PAYMENT_METHODS = ["", "card", "cash", "venmo", "zelle", "paypal", "other"]
MIN_DATE, MAX_DATE = date(1990, 1, 1), date(2100, 1, 1)
UPLOAD_TYPES = sorted(files.ALLOWED_EXTENSIONS)


def reset_capture():
    st.session_state.capture_nonce = st.session_state.get("capture_nonce", 0) + 1
    st.session_state.manual = False


def cached_extraction(file_bytes, filename, file_hash):
    """Streamlit reruns the page on every interaction, so OCR must not repeat for the same file."""
    cache = st.session_state.setdefault("extractions", {})
    if file_hash not in cache:
        with st.spinner("Reading your file…"):
            cache[file_hash] = get_backend().extract(file_bytes, filename)
    return cache[file_hash]


def label(name, field, extraction):
    return f"⚠️ {name} (please check)" if extraction.field_confidence.get(field) == "low" else name


def show_issues(issues):
    for issue in issues:
        (st.error if issue.severity == "error" else st.warning)(f"{issue.message}")


def show_unusable(extraction, nonce):
    show_issues(validate(extraction))
    st.caption(f"Why: {extraction.field_reason.get('document_type', 'unknown')}")
    if st.button("Enter manually", type="primary", key=f"manual_after_error_{nonce}"):
        st.session_state.manual = True
        st.rerun()


def show_preview(file_bytes, filename, file_hash):
    previews = st.session_state.setdefault("previews", {})
    if file_hash not in previews:
        previews[file_hash] = files.preview_image(file_bytes, filename)
    if previews[file_hash] is None:
        st.caption("No preview is available for this file.")
    else:
        st.image(previews[file_hash], width="stretch")


def category_input(key, merchant, extraction, conn):
    """Follows the merchant as it's typed, until the user picks a category themselves."""
    config = categorize.load_config()
    suggested, source = categorize.categorize(
        merchant.strip() or None, extraction.document_type, extraction.raw_text, db.get_overrides(conn), config["rules"]
    )
    touched_key = f"{key}_touched"
    if not st.session_state.get(touched_key):
        st.session_state[key] = suggested
    category = st.selectbox(
        "Category", config["categories"], key=key, on_change=lambda: st.session_state.update({touched_key: True})
    )
    if category != suggested:
        source = "manual"
    st.caption(f"Category from: {categorize.SOURCE_LABELS[source]}")
    return category, source


def confirm_form(extraction, conn, form_key, upload=None):
    """Returns nothing; saves or discards through its own buttons."""
    today = date.today()
    extracted_date = date.fromisoformat(extraction.date) if extraction.date else today
    reasons = extraction.field_reason
    issues_slot = st.container()

    merchant = st.text_input(
        label("Merchant", "merchant", extraction), value=extraction.merchant or "",
        key=f"{form_key}_merchant", help=reasons.get("merchant"),
    )
    day = st.date_input(
        label("Date", "date", extraction), value=min(max(extracted_date, MIN_DATE), MAX_DATE),
        min_value=MIN_DATE, max_value=MAX_DATE, key=f"{form_key}_date", help=reasons.get("date"),
    )
    total = st.number_input(
        label("Total", "total", extraction), value=extraction.total, step=0.01, format="%.2f",
        key=f"{form_key}_total", help=reasons.get("total"),
    )
    category, source = category_input(f"{form_key}_category", merchant, extraction, conn)
    method_index = PAYMENT_METHODS.index(extraction.payment_method) if extraction.payment_method in PAYMENT_METHODS else 0
    method = st.selectbox(
        "Payment method", PAYMENT_METHODS, index=method_index, key=f"{form_key}_method",
        format_func=lambda m: m.capitalize() or "Not specified", help=reasons.get("payment_method"),
    )
    note = st.text_input("Note", key=f"{form_key}_note")
    with st.expander("Subtotal, tax and tip"):
        subtotal = st.number_input("Subtotal", value=extraction.subtotal, step=0.01, format="%.2f",
                                   key=f"{form_key}_subtotal", help=reasons.get("subtotal"))
        tax = st.number_input("Tax", value=extraction.tax, step=0.01, format="%.2f",
                              key=f"{form_key}_tax", help=reasons.get("tax"))
        tip = st.number_input("Tip", value=extraction.tip, step=0.01, format="%.2f",
                              key=f"{form_key}_tip", help=reasons.get("tip"))

    remember = False
    if source == "manual" and merchant.strip():
        remember = st.checkbox(f"Always use this category for {merchant.strip()}", key=f"{form_key}_remember")

    form = confirm.FormValues(merchant, day, total, subtotal, tax, tip, method or None, note)
    edited = confirm.apply_edits(extraction, form)
    issues = confirm.form_issues(extraction, edited, today)
    file_hash = upload[2] if upload else None
    duplicates = find_duplicates(conn, file_hash, edited.merchant, edited.date, edited.total)
    with issues_slot:
        show_issues(issues)
        for duplicate in duplicates:
            st.warning(f"{duplicate.message} Saved expense: {duplicate.summary}.")

    save_col, discard_col = st.columns(2)
    if save_col.button("Save expense", type="primary", disabled=blocks_save(issues), width="stretch", key=f"{form_key}_save"):
        file_path = None
        if upload:
            path = files.save_original(upload[0], upload[1], ui.data_dir() / "files")
            file_path = str(path.relative_to(ui.data_dir()))
        expense = confirm.build_expense(extraction, edited, form, category, source, file_path, file_hash)
        db.insert_expense(conn, expense)
        if remember:
            db.set_override(conn, merchant, category)
        st.session_state.saved_summary = f"{expense.merchant}, {expense.date}, ${expense.total:.2f}, {expense.category}"
        reset_capture()
        st.rerun()
    if discard_col.button("Discard", width="stretch", key=f"{form_key}_discard"):
        reset_capture()
        st.rerun()


def show_saved():
    st.success(f"Saved: {st.session_state.saved_summary}")
    if st.button("Add another", type="primary"):
        del st.session_state.saved_summary
        st.rerun()


ui.setup_page("Add Expense")
st.header("Add Expense")
if load_config().extraction_backend == "mock":
    st.warning("**MOCK MODE — extraction is simulated**")
if not load_config().hosted_demo:
    st.caption(ui.LOCAL_NOTICE)

conn = ui.open_db()
st.session_state.setdefault("capture_nonce", 0)
st.session_state.setdefault("manual", False)
nonce = st.session_state.capture_nonce

if "saved_summary" in st.session_state:
    show_saved()
else:
    uploaded = st.file_uploader(
        "Upload a receipt photo, a PDF, or a payment screenshot", type=UPLOAD_TYPES, key=f"upload_{nonce}"
    )
    if st.button("Enter manually instead", key=f"manual_{nonce}"):
        st.session_state.manual = True
        st.rerun()

    upload = None
    extraction = None
    rejection = None
    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        try:
            files.validate_upload(file_bytes, uploaded.name)
            upload = (file_bytes, uploaded.name, files.file_hash(file_bytes))
            extraction = cached_extraction(file_bytes, uploaded.name, upload[2])
        except files.FileRejected as e:
            rejection = str(e)

    if rejection:
        st.error(rejection)
    elif st.session_state.manual or extraction is not None:
        unusable = extraction is not None and extraction.document_type in confirm.UNUSABLE_DOCUMENT_TYPES
        if unusable and not st.session_state.manual:
            if upload:
                for duplicate in find_duplicates(conn, upload[2]):
                    st.warning(f"{duplicate.message} Saved expense: {duplicate.summary}.")
            show_unusable(extraction, nonce)
        else:
            if st.session_state.manual:
                extraction = confirm.start_manual(extraction)
            form_key = f"form_{nonce}_{'manual' if st.session_state.manual else upload[2][:16]}"
            if upload:
                left, right = st.columns(2)
                with left:
                    show_preview(upload[0], upload[1], upload[2])
            else:
                right = st.container()
            with right:
                confirm_form(extraction, conn, form_key, upload)
                if extraction.raw_text:
                    with st.expander("Show extracted text"):
                        st.text(extraction.raw_text)
conn.close()
