import streamlit as st

from core import db

st.set_page_config(page_title="Dashboard · SnapSpend", page_icon="🧾", layout="wide")
db.init_db()
st.header("Dashboard")
st.info("Charts and insights arrive in M6.")
