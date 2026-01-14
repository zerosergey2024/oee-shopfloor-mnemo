import os
import streamlit as st

from src.ui import render_mnemo_selectable, render_machine_panel
from src.providers import get_provider
from src.config_loader import load_config

st.set_page_config(page_title="OEE Shopfloor Mnemo v3", layout="wide")

# Конфиг по умолчанию (BASIC), можно переключать через env var
config_path = os.environ.get("OEE_CONFIG", "config/basic.yaml")
cfg = load_config(config_path)

st.title(f"Мнемосхема цеха (v3) — уровень {cfg['level']}")
st.caption("Уровень оснащения задаётся конфигом. UI одинаковый для BASIC/STANDARD/ADVANCED.")

provider = get_provider(cfg["provider"])
machines = provider.get_overview()

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

    df_oee = provider.get_oee_timeseries(selected.machine_id)
    stops = provider.get_stops(selected.machine_id)

    render_machine_panel(selected, df_oee, stops)


