import streamlit as st

from src.data_mock import get_mock_overview, get_mock_machine_timeseries, get_mock_stops
from src.ui import render_mnemo_selectable, render_machine_panel

st.set_page_config(page_title="OEE Shopfloor Mnemo v3", layout="wide")

st.title("Мнемосхема цеха (v3) — выбор станка + панель OEE")
st.caption("Клик «Выбрать» под силуэтом открывает панель анализа: карточка, тренд OEE и список остановок.")

machines = get_mock_overview()

# Выбранный станок (сохраняем между перерендерами)
if "selected_machine_id" not in st.session_state:
    st.session_state.selected_machine_id = machines[0].machine_id

left, right = st.columns([2, 1], gap="large")

with left:
    st.subheader("Мнемосхема")
    st.session_state.selected_machine_id = render_mnemo_selectable(
        machines,
        st.session_state.selected_machine_id
    )
    st.info("Легенда: 🟢 Работает | ⚪ Не в работе | 🔴 Ремонт/ТО. Наведите курсор на станок для подсказки.")

with right:
    st.subheader("Панель анализа")
    selected = next(m for m in machines if m.machine_id == st.session_state.selected_machine_id)

    df_oee = get_mock_machine_timeseries(selected.machine_id)
    stops = get_mock_stops(selected.machine_id)

    render_machine_panel(selected, df_oee, stops)

