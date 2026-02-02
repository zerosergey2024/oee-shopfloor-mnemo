from __future__ import annotations

import streamlit as st
from pathlib import Path
from typing import List, Optional
import pandas as pd

from .models import MachineOverview, StopEvent
from .telemetry.simulator import (
    TelemetryThresholds,
    generate_telemetry_df,
    compute_alarms,
    summarize_telemetry,
)

BASE_DIR = Path(__file__).resolve().parents[1]

COLOR = {
    "RUN":  "#2ecc71",
    "IDLE": "#95a5a6",
    "DOWN": "#e74c3c",
}

STATE_LABEL = {
    "RUN": "РАБОТАЕТ",
    "IDLE": "НЕ В РАБОТЕ",
    "DOWN": "РЕМОНТ / ТО",
}

REASON_LABEL = {
    "MICROSTOP": "Микростоп",
    "SETUP": "Наладка",
    "FAULT": "Авария",
    "MAINT": "ТО",
    "REPAIR": "Ремонт",
}

SVG_MAP = {
    "Фрезерный ЧПУ": "cnc_mill.svg",
    "Токарный ЧПУ": "cnc_lathe.svg",
    "Крой металла": "cnc_cut.svg",
}


def tooltip_text(m: MachineOverview) -> str:
    header = f"[{m.name} {m.machine_id}]"
    if m.state in ("RUN", "IDLE"):
        return "\n".join([
            header,
            f"{'🟢' if m.state=='RUN' else '⚪'} {STATE_LABEL[m.state]}",
            f"Смена: {m.shift.start:%H:%M} - {m.shift.end:%H:%M}",
            f"Остановок: {m.stops_count}",
            f"Время работы: {m.run_time_hours:.1f} ч из {m.planned_time_hours:.1f} ч",
            f"OEE: {m.oee_percent:.1f}%" if m.oee_percent is not None else "OEE: —"
        ])

    down_ts = f"{m.down_start_ts:%Y-%m-%d %H:%M}" if m.down_start_ts else "—"
    reason = "ТО" if m.down_reason == "MAINT" else ("Ремонт" if m.down_reason == "REPAIR" else "—")
    return "\n".join([
        header,
        "🔴 РЕМОНТ / ТО",
        f"Останов: {down_ts}",
        f"Причина: {reason}",
    ])


def load_svg(kind: str, color: str) -> str:
    svg_file = BASE_DIR / "assets" / "silhouettes" / SVG_MAP[kind]
    svg = svg_file.read_text(encoding="utf-8")
    return svg.replace("CURRENT_COLOR", color)


def render_mnemo_selectable(machines: List[MachineOverview], selected_id: Optional[str]) -> str:
    """
    Рендерим мнемосхему через Streamlit компоненты + кнопки выбора.
    Возвращает machine_id выбранного станка (или текущий).
    """
    cols = st.columns(len(machines))
    new_selected = selected_id

    for col, m in zip(cols, machines):
        with col:
            svg = load_svg(m.kind, COLOR[m.state])
            tooltip = tooltip_text(m).replace("\n", "&#10;")

            is_selected = (m.machine_id == selected_id)
            border = "2px solid #4da3ff" if is_selected else "1px solid rgba(255,255,255,0.15)"

            html = f"""
            <div title="{tooltip}" style="text-align:center; padding:8px; border:{border}; border-radius:14px;">
              {svg}
              <div style="font-weight:600; margin-top:6px;">{m.name}</div>
              <div style="font-size:12px; opacity:0.8;">{m.machine_id}</div>
            </div>
            """
            st.components.v1.html(html, height=190)

            if st.button("Выбрать", key=f"select_{m.machine_id}", use_container_width=True):
                new_selected = m.machine_id

    return new_selected


def render_machine_panel(machine: MachineOverview, df_oee, stops: List[StopEvent]):
    st.subheader("Карточка оборудования")
    st.code(tooltip_text(machine), language="text")

    st.subheader("OEE за смену")

    # --- Нормализация df_oee: провайдер может вернуть dict/list ---
    if isinstance(df_oee, dict):
        df_oee = pd.DataFrame(df_oee)
    elif isinstance(df_oee, list):
        df_oee = pd.DataFrame(df_oee)

    if not isinstance(df_oee, pd.DataFrame):
        st.error(f"df_oee должен быть pandas.DataFrame, но пришёл: {type(df_oee)}")
        return

    # timestamp -> index (если присутствует)
    if "timestamp" in df_oee.columns:
        df_oee = df_oee.copy()
        df_oee["timestamp"] = pd.to_datetime(df_oee["timestamp"])
        df_oee = df_oee.set_index("timestamp")

    # Нормализация имени колонки OEE
    col_candidates = ["oee_percent", "OEE_percent", "oee", "OEE"]
    oee_col = next((c for c in col_candidates if c in df_oee.columns), None)

    if oee_col is None:
        st.error(f"Не найдена колонка OEE в df_oee. Доступно: {list(df_oee.columns)}")
    else:
        st.line_chart(df_oee[[oee_col]])

    st.subheader("Остановки")
    if stops:
        rows = []
        for s in stops:
            end_str = s.end.strftime("%H:%M") if s.end else "—"
            rows.append({
                "Начало": s.start.strftime("%H:%M"),
                "Конец": end_str,
                "Длительность, мин": getattr(s, "duration_min", None),
                "Причина": REASON_LABEL.get(s.reason, s.reason),
                "Комментарий": s.note or "",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Остановок за смену не зарегистрировано.")


def _badge(status: str) -> str:
    if status == "alarm":
        return "🔴 ALARM"
    if status == "warn":
        return "🟠 WARN"
    return "🟢 OK"


def render_telemetry_panel(machine: MachineOverview, cfg: dict):
    """
    Показ “датчиков/PLC” в демо-режиме (симуляция).
    """
    st.subheader("Датчики / PLC (DEMO)")

    level = cfg.get("level", "BASIC")
    state = getattr(machine, "state", "RUN")
    if state == "DOWN":
        st.warning("Оборудование в ремонте/ТО. Датчики отключены — телеметрия недоступна.")


    # Кэшируем, чтобы при каждом rerun не “скакали” графики
    cache_key = f"telemetry::{level}::{machine.machine_id}::{state}"
    if cache_key not in st.session_state:
        df = generate_telemetry_df(machine.machine_id, level=level, state=state, minutes=240, step_sec=30)
        st.session_state[cache_key] = df
    else:
        df = st.session_state[cache_key]

    thr = TelemetryThresholds()
    alarms = compute_alarms(df, thr)
    summary = summarize_telemetry(df)

    def fmt(x, fmt_str):
        return "—" if pd.isna(x) else fmt_str.format(x)

    c1, c2, c3 = st.columns(3)
    c1.metric("Вибрация, мм/с", fmt(summary["vibration_last"], "{:.2f}"), _badge(alarms["vibration"]))
    c2.metric("Температура, °C", fmt(summary["temp_last"], "{:.1f}"), _badge(alarms["temperature"]))
    c3.metric("Ток, pu", fmt(summary["current_last"], "{:.2f}"), _badge(alarms["current"]))

    st.caption("Сигналы симулируются. В ADVANCED больше аномалий для демонстрации диагностики.")
    if df[["vibration_mm_s", "bearing_temp_c", "motor_current_pu"]].dropna(how="all").empty:
        st.info("Нет телеметрии за период (нет связи/данных).")
        return

    st.line_chart(df[["vibration_mm_s"]], height=160)
    st.line_chart(df[["bearing_temp_c"]], height=160)
    st.line_chart(df[["motor_current_pu"]], height=160)

    with st.expander("Пороги (для демонстрации)"):
        st.write(
            {
                "vibration_warn": thr.vibration_warn,
                "vibration_alarm": thr.vibration_alarm,
                "temp_warn": thr.temp_warn,
                "temp_alarm": thr.temp_alarm,
                "current_warn": thr.current_warn,
                "current_alarm": thr.current_alarm,
            }
        )


