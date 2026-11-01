import streamlit as st

from core import db

st.set_page_config(page_title="Expenses · SnapSpend", page_icon="🧾", layout="wide")
db.init_db()
st.header("Expenses")
st.info("The expense list arrives in M5.")
