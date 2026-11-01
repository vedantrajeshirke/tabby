import streamlit as st

from core import db
from core.config import load_config

st.set_page_config(page_title="Add Expense · SnapSpend", page_icon="🧾", layout="wide")
db.init_db()
st.header("Add Expense")
if load_config().extraction_backend == "mock":
    st.warning("**MOCK MODE — extraction is simulated**")
st.info("Receipt capture and confirmation arrive in M4.")
