"""SnapSpend entry point: home page and global banners."""
import streamlit as st

from core import db
from core.config import TESSERACT_INSTALL_HELP, find_tesseract, load_config

st.set_page_config(page_title="SnapSpend", page_icon="🧾", layout="wide")
db.init_db()

cfg = load_config()
if find_tesseract(cfg) is None:
    st.warning(
        "**Tesseract OCR not found.** Photo and scanned-PDF reading is disabled; manual entry, "
        "PDFs with a text layer, and the dashboard still work. " + TESSERACT_INSTALL_HELP
    )

conn = db.connect()
settings = db.load_settings(conn)
conn.close()

st.title("🧾 SnapSpend")
st.write(
    f"Welcome{', ' + settings.name if settings.name else ''}! "
    "Upload a receipt, confirm it in one tap, and see if you're on track."
)
st.page_link("pages/1_Add_Expense.py", label="Add an expense", icon="➕")
st.page_link("pages/2_Expenses.py", label="Expenses", icon="📋")
st.page_link("pages/3_Dashboard.py", label="Dashboard", icon="📊")
st.page_link("pages/4_Settings.py", label="Settings", icon="⚙️")
st.caption("Your receipts are processed and stored only on this device.")
