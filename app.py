import streamlit as st
from src.data_mock import get_mock_overview
from src.ui import render_mnemo

st.set_page_config(page_title="OEE Shopfloor Mnemo", layout="wide")

st.title("Мнемосхема цеха (v2) — 3 станка ЧПУ")
st.caption("SVG-силуэты оборудования с цветовой индикацией состояния и всплывающей карточкой при наведении курсора.")

machines = get_mock_overview()
render_mnemo(machines)

st.markdown("---")
st.info("Легенда: 🟢 Работает | ⚪ Не в работе | 🔴 Ремонт/ТО. Наведите курсор на станок, чтобы увидеть детали.")
