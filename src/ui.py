from __future__ import annotations
import streamlit as st
from pathlib import Path
from typing import List, Optional
import pandas as pd

from .models import MachineOverview, StopEvent

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

            # Визуальная рамка выбранного
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

def render_machine_panel(machine: MachineOverview, df_oee: pd.DataFrame, stops: List[StopEvent]):
    st.subheader("Карточка оборудования")
    st.code(tooltip_text(machine), language="text")

    st.subheader("OEE за смену")
    # Streamlit сам построит график по индексу времени
    st.line_chart(df_oee["oee_percent"])

    st.subheader("Остановки")
    if stops:
        rows = []
        for s in stops:
            rows.append({
                "Начало": s.start.strftime("%H:%M"),
                "Конец": s.end.strftime("%H:%M"),
                "Длительность, мин": s.duration_min,
                "Причина": REASON_LABEL.get(s.reason, s.reason),
                "Комментарий": s.note or "",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Остановок за смену не зарегистрировано.")

