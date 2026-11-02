"""SnapSpend entry point: home page and global banners."""
import streamlit as st

import ui
from core import db

ui.setup_page()

conn = ui.open_db()
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
