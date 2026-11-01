import streamlit as st

from core import db

st.set_page_config(page_title="Add Expense · SnapSpend", page_icon="🧾", layout="wide")
db.init_db()
st.header("Add Expense")
st.info("Receipt capture and confirmation arrive in M4.")
