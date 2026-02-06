from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import streamlit as st

from .models import MachineOverview, StopEvent
from .telemetry.simulator import (
    TelemetryThresholds,
    compute_alarms,
    generate_telemetry_df,
    summarize_telemetry,
)

BASE_DIR = Path(__file__).resolve().parents[1]

COLOR = {
    "RUN": "#2ecc71",
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


# ============================
# Mnemo helpers
# ============================
def tooltip_text(m: MachineOverview) -> str:
    header = f"[{m.name} {m.machine_id}]"

    if m.state in ("RUN", "IDLE"):
        # аккуратная защита от не-datetime
        try:
            shift_start = getattr(m.shift, "start", None)
            shift_end = getattr(m.shift, "end", None)
            shift_str = f"{shift_start:%H:%M} - {shift_end:%H:%M}"
        except Exception:
            shift_str = "—"

        return "\n".join(
            [
                header,
                f"{'🟢' if m.state == 'RUN' else '⚪'} {STATE_LABEL.get(m.state, m.state)}",
                f"Смена: {shift_str}",
                f"Остановок: {getattr(m, 'stops_count', 0)}",
                f"Время работы: {getattr(m, 'run_time_hours', 0.0):.1f} ч из {getattr(m, 'planned_time_hours', 0.0):.1f} ч",
                f"OEE: {m.oee_percent:.1f}%" if m.oee_percent is not None else "OEE: —",
            ]
        )

    try:
        down_ts = f"{m.down_start_ts:%Y-%m-%d %H:%M}" if m.down_start_ts else "—"
    except Exception:
        down_ts = "—"

    reason = "ТО" if getattr(m, "down_reason", None) == "MAINT" else ("Ремонт" if getattr(m, "down_reason", None) == "REPAIR" else "—")
    return "\n".join([header, "🔴 РЕМОНТ / ТО", f"Останов: {down_ts}", f"Причина: {reason}"])


def load_svg(kind: str, color: str) -> str:
    # безопасный fallback, чтобы UI не падал из-за нового типа станка
    fname = SVG_MAP.get(kind, "cnc_mill.svg")
    svg_file = BASE_DIR / "assets" / "silhouettes" / fname
    svg = svg_file.read_text(encoding="utf-8")
    return svg.replace("CURRENT_COLOR", color)


def render_mnemo_selectable(machines: List[MachineOverview], selected_id: Optional[str]) -> str:
    cols = st.columns(len(machines))
    new_selected = selected_id

    for col, m in zip(cols, machines):
        with col:
            svg = load_svg(getattr(m, "kind", "Фрезерный ЧПУ"), COLOR.get(m.state, "#95a5a6"))
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


# ============================
# Machine panel
# ============================
def render_machine_panel(
    machine: MachineOverview,
    df_oee: Union[pd.DataFrame, Dict[str, Any], List[Dict[str, Any]]],
    stops: List[StopEvent],
) -> None:
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

    if "timestamp" in df_oee.columns:
        df_oee = df_oee.copy()
        df_oee["timestamp"] = pd.to_datetime(df_oee["timestamp"], errors="coerce")
        df_oee = df_oee.dropna(subset=["timestamp"]).set_index("timestamp")

    col_candidates = ["oee_percent", "OEE_percent", "oee", "OEE"]
    oee_col = next((c for c in col_candidates if c in df_oee.columns), None)

    if oee_col is None:
        st.error(f"Не найдена колонка OEE в df_oee. Доступно: {list(df_oee.columns)}")
    else:
        st.line_chart(df_oee[[oee_col]])

    st.subheader("Остановки")
    if stops:
        stops_sorted = sorted(stops, key=lambda s: s.start, reverse=True)
        rows = []
        for s in stops_sorted:
            end_ts = getattr(s, "end", None)
            end_str = end_ts.strftime("%H:%M") if end_ts else "—"

            if getattr(s, "duration_min", None) is not None:
                dur = s.duration_min
            else:
                end_for_calc = end_ts or datetime.now()
                dur = int((end_for_calc - s.start).total_seconds() // 60)

            rows.append(
                {
                    "Начало": s.start.strftime("%H:%M"),
                    "Конец": end_str,
                    "Длительность, мин": dur,
                    "Причина": REASON_LABEL.get(s.reason, s.reason),
                    "Комментарий": getattr(s, "note", "") or "",
                }
            )

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Остановок за смену не зарегистрировано.")


# ============================
# Telemetry panel (CLEAN)
# ============================
def _badge(status: str) -> str:
    if status == "alarm":
        return "🔴 ALARM"
    if status == "warn":
        return "🟠 WARN"
    return "🟢 OK"


def _inject_alarm_styles() -> None:
    st.markdown(
        """
        <style>
        .alarm-row { display:flex; align-items:center; gap:12px; margin: 6px 0 12px 0; }
        .estop {
            width: 92px; height: 92px; border-radius: 999px;
            display:flex; align-items:center; justify-content:center;
            font-weight: 900; font-size: 12px; letter-spacing: 1px;
            user-select:none;
        }
        .estop-red {
            background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.35), rgba(231,76,60,0.85));
            border: 2px solid rgba(231,76,60,0.95);
            box-shadow: 0 0 0 0 rgba(231,76,60,0.65);
            animation: pulse 1.1s infinite;
            color: #fff;
        }
        .estop-orange {
            background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.35), rgba(243,156,18,0.85));
            border: 2px solid rgba(243,156,18,0.95);
            color: #1a1a1a;
        }
        .estop-ok {
            background: rgba(46, 204, 113, 0.18);
            border: 1px solid rgba(46, 204, 113, 0.35);
            color: rgba(230, 255, 240, 0.95);
        }
        .alarm-banner {
            flex: 1;
            padding: 12px 14px;
            border-radius: 12px;
            font-weight: 800;
            letter-spacing: 0.3px;
            text-align: left;
        }
        .banner-red {
            background: rgba(231,76,60,0.20);
            border: 1px solid rgba(231,76,60,0.55);
            color: #ffdad6;
        }
        .banner-orange {
            background: rgba(243,156,18,0.18);
            border: 1px solid rgba(243,156,18,0.55);
            color: #ffe8bd;
        }
        .banner-ok {
            background: rgba(46, 204, 113, 0.12);
            border: 1px solid rgba(46, 204, 113, 0.28);
            color: rgba(230, 255, 240, 0.95);
        }
        @keyframes pulse {
            0%   { box-shadow: 0 0 0 0 rgba(231,76,60,0.65); }
            70%  { box-shadow: 0 0 0 14px rgba(231,76,60,0.0); }
            100% { box-shadow: 0 0 0 0 rgba(231,76,60,0.0); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_estop(has_alarm: bool, has_warn: bool, hint: str) -> None:
    _inject_alarm_styles()

    if has_alarm:
        estop_class = "estop estop-red"
        banner_class = "alarm-banner banner-red"
        title = "АВАРИЯ: превышение порогов"
    elif has_warn:
        estop_class = "estop estop-orange"
        banner_class = "alarm-banner banner-orange"
        title = "ПРЕДУПРЕЖДЕНИЕ: близко к порогам"
    else:
        estop_class = "estop estop-ok"
        banner_class = "alarm-banner banner-ok"
        title = "OK: критических превышений нет"

    st.markdown(
        f"""
        <div class="alarm-row">
            <div class="{estop_class}" title="Демо-индикатор, без управления">E-STOP</div>
            <div class="{banner_class}">
                <div style="font-size:14px; font-weight:900; margin-bottom:2px;">{title}</div>
                <div style="font-size:12px; opacity:0.95;">{hint}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _apply_cutoff(df: pd.DataFrame, cutoff_ts: Optional[pd.Timestamp]) -> pd.DataFrame:
    if cutoff_ts is None:
        return df
    df2 = df.copy()
    df2.loc[df2.index >= cutoff_ts, ["vibration_mm_s", "bearing_temp_c", "motor_current_pu"]] = pd.NA
    return df2


def _last_valid_row(df: pd.DataFrame) -> Optional[pd.Series]:
    cols = ["vibration_mm_s", "bearing_temp_c", "motor_current_pu"]
    last_valid = df[cols].dropna(how="any").tail(1)
    if last_valid.empty:
        return None
    return last_valid.iloc[0]


def render_telemetry_panel(
    machine: MachineOverview,
    cfg: dict,
    stops: Optional[List[StopEvent]] = None,
) -> None:
    """
    Чистая версия панели:
    - стабильный кэш по (level, machine_id, state)
    - корректная отсечка телеметрии при IDLE/DOWN
    - устойчивость к NA в последних строках после cutoff
    - статус (OK/WARN/ALARM) показываем НЕ через delta у metric, а отдельной строкой
    """
    st.subheader("Датчики / PLC (DEMO)")

    level = cfg.get("level", "BASIC")
    state = getattr(machine, "state", "RUN")

    # кэш, чтобы не "скакало"
    cache_key = f"telemetry::{level}::{machine.machine_id}::{state}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = generate_telemetry_df(
            machine.machine_id,
            level=level,
            state=state,
            minutes=240,
            step_sec=30,
        )

    df = st.session_state[cache_key]

    # --- cutoff: обрыв телеметрии при IDLE/DOWN ---
    cutoff_ts = None
    if state == "DOWN" and getattr(machine, "down_start_ts", None):
        cutoff_ts = pd.to_datetime(machine.down_start_ts)

    if state == "IDLE" and stops:
        open_stop = next((s for s in stops if getattr(s, "end", None) is None), None)
        if open_stop:
            cutoff_ts = pd.to_datetime(open_stop.start)
        else:
            last_stop = max(stops, key=lambda s: s.start, default=None)
            if last_stop:
                cutoff_ts = pd.to_datetime(last_stop.start)

    df = _apply_cutoff(df, cutoff_ts)

    cols = ["vibration_mm_s", "bearing_temp_c", "motor_current_pu"]
    if df[cols].dropna(how="all").empty:
        if state == "DOWN":
            st.warning("Оборудование в ремонте/ТО. Датчики отключены — телеметрия недоступна.")
        else:
            st.info("Нет телеметрии за период (нет связи/данных).")
        return

    last_valid = _last_valid_row(df)
    if last_valid is None:
        # есть какие-то данные в целом, но после cutoff последние строки пустые — это ок
        st.info("Телеметрия есть, но последние точки после отсечки пустые. Прокрутите период или смените станок.")
        return

    # --- считаем alarms/summary устойчиво, через “валидные” данные ---
    # ВНИМАНИЕ: compute_alarms/summarize_telemetry в текущем simulator.py берут df.iloc[-1].
    # Здесь мы передадим df без последних NA: обрежем по последнему валидному индексу.
    last_ts = df[cols].dropna(how="any").index.max()
    df_valid_tail = df.loc[:last_ts]

    thr = TelemetryThresholds()
    alarms = compute_alarms(df_valid_tail, thr)
    summary = summarize_telemetry(df_valid_tail)

    # --- E-STOP индикатор ---
    has_alarm = any(v == "alarm" for v in alarms.values())
    has_warn = any(v == "warn" for v in alarms.values())

    hint = f"Станок: {machine.machine_id} • Состояние: {STATE_LABEL.get(state, state)}"
    if cutoff_ts is not None:
        hint += f" • Отсечка телеметрии: {cutoff_ts:%H:%M}"

    _render_estop(has_alarm, has_warn, hint)

    def fmt_num(x: Any, fmt_str: str) -> str:
        return "—" if pd.isna(x) else fmt_str.format(x)

    c1, c2, c3 = st.columns(3)

    c1.metric("Вибрация, мм/с", fmt_num(summary.get("vibration_last"), "{:.2f}"))
    c1.caption(_badge(alarms.get("vibration", "ok")))

    c2.metric("Температура, °C", fmt_num(summary.get("temp_last"), "{:.1f}"))
    c2.caption(_badge(alarms.get("temperature", "ok")))

    c3.metric("Ток, pu", fmt_num(summary.get("current_last"), "{:.2f}"))
    c3.caption(_badge(alarms.get("current", "ok")))

    st.caption("Сигналы симулируются. В ADVANCED больше аномалий для демонстрации диагностики.")

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


