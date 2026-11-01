import streamlit as st

from core import db
from core.models import Settings

st.set_page_config(page_title="Settings · SnapSpend", page_icon="🧾", layout="wide")
db.init_db()
st.header("Settings")

conn = db.connect()
current = db.load_settings(conn)

with st.form("settings"):
    name = st.text_input("Display name", value=current.name)
    budget = st.number_input(
        "Monthly budget (USD, 0 = no budget)",
        min_value=0.0, step=50.0, value=float(current.monthly_budget or 0.0),
    )
    start_day = st.number_input(
        "Budget cycle start day (1–28)", min_value=1, max_value=28, step=1,
        value=current.cycle_start_day,
        help="Day your allowance or stipend cycle starts. 1 = calendar months.",
    )
    if st.form_submit_button("Save settings"):
        db.save_settings(conn, Settings(name, budget or None, int(start_day)))
        st.success("Settings saved.")

st.subheader("Demo data")
st.info("Synthetic demo data arrives in M7.")
conn.close()
