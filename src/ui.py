from __future__ import annotations
import streamlit as st
from pathlib import Path
from typing import List
from .models import MachineOverview

BASE_DIR = Path(__file__).resolve().parents[1]

COLOR = {
    "RUN":  "#2ecc71",  # зелёный
    "IDLE": "#95a5a6",  # серый
    "DOWN": "#e74c3c",  # красный
}

STATE_LABEL = {
    "RUN": "РАБОТАЕТ",
    "IDLE": "НЕ В РАБОТЕ",
    "DOWN": "РЕМОНТ / ТО",
}

REASON_LABEL = {
    "MAINT": "ТО",
    "REPAIR": "Ремонт",
    None: "—",
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

    return "\n".join([
        header,
        "🔴 РЕМОНТ / ТО",
        f"Останов: {m.down_start_ts:%Y-%m-%d %H:%M}" if m.down_start_ts else "Останов: —",
        f"Причина: {REASON_LABEL.get(m.down_reason)}",
    ])

def load_svg(kind: str, color: str) -> str:
    svg_file = BASE_DIR / "assets" / "silhouettes" / SVG_MAP[kind]
    svg = svg_file.read_text(encoding="utf-8")
    return svg.replace("CURRENT_COLOR", color)

def render_mnemo(machines: List[MachineOverview]):
    cols = st.columns(len(machines))
    for col, m in zip(cols, machines):
        with col:
            svg = load_svg(m.kind, COLOR[m.state])
            tooltip = tooltip_text(m).replace("\n", "&#10;")  # переносы для title
            html = f"""
            <div title="{tooltip}" style="text-align:center;">
              {svg}
              <div style="font-weight:600; margin-top:6px;">
                {m.name}
              </div>
              <div style="font-size:12px; opacity:0.8;">
                {m.machine_id}
              </div>
            </div>
            """
            st.components.v1.html(html, height=170)
