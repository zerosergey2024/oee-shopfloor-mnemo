import os
import requests

import pandas as pd
import streamlit as st
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from uuid import uuid4

from src.ai.service import generate_recommendation
from src.ui import render_mnemo_selectable, render_machine_panel, render_telemetry_panel
from src.providers import get_provider
from src.config_loader import load_config

from src.telemetry.simulator import (
    TelemetryThresholds,
    generate_telemetry_df,
    compute_alarms,
    summarize_telemetry,
)


st.set_page_config(page_title="OEE Shopfloor Mnemo", layout="wide")

config_path = os.environ.get("OEE_CONFIG", "config/basic.yaml")
cfg = load_config(config_path)

st.title(f"Мнемосхема цеха — уровень {cfg['level']}")
st.caption("Уровень оснащения задаётся конфигом. UI одинаковый для BASIC/STANDARD/ADVANCED.")

provider = get_provider(cfg["provider"])
machines = provider.get_overview()

if not machines:
    st.error("Провайдер не вернул ни одного станка (machines пуст).")
    st.stop()

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

selected_id = st.session_state.selected_machine_id
selected = next((m for m in machines if m.machine_id == selected_id), None)

if selected is None:
    st.error(f"Не найден станок с id={selected_id}")
    st.stop()

df_oee = provider.get_oee_timeseries(selected_id)
stops = provider.get_stops(selected_id)

def actions_to_list(actions):
    out = []
    for a in actions or []:
        if hasattr(a, "model_dump"):          # pydantic v2
            out.append(a.model_dump())
        elif isinstance(a, dict):
            out.append(a)
        else:
            out.append({"title": str(a), "details": None})
    return out


def build_telemetry_hint(machine_obj, cfg: dict, stops_list, economics: dict | None):
    """
    Собираем реальные цифры телеметрии (last/max) + статусы alarm/warn/ok.
    Берём df из session_state тем же ключом, что использует render_telemetry_panel,
    чтобы AI видел те же данные, что на графике.
    economics — what-if цифры (можно None).
    """
    if not cfg.get("features", {}).get("telemetry", False):
        return {"status": "DISABLED", "reason": "telemetry feature flag is off", "economics": economics}

    level = cfg.get("level", "BASIC")
    state = getattr(machine_obj, "state", "RUN")

    cache_key = f"telemetry::{level}::{machine_obj.machine_id}::{state}"

    if cache_key in st.session_state:
        df = st.session_state[cache_key]
    else:
        df = generate_telemetry_df(
            machine_obj.machine_id,
            level=level,
            state=state,
            minutes=240,
            step_sec=30
        )
        st.session_state[cache_key] = df

    # --- тот же cutoff, что и в UI: после него телеметрия "обрывается" ---
    cutoff_ts = None

    if state == "DOWN" and getattr(machine_obj, "down_start_ts", None):
        cutoff_ts = pd.to_datetime(machine_obj.down_start_ts)

    if state == "IDLE" and stops_list:
        open_stop = next((s for s in stops_list if getattr(s, "end", None) is None), None)
        if open_stop:
            cutoff_ts = pd.to_datetime(open_stop.start)
        else:
            last_stop = max(stops_list, key=lambda s: s.start, default=None)
            if last_stop:
                cutoff_ts = pd.to_datetime(last_stop.start)

    if cutoff_ts is not None:
        df = df.copy()
        df.loc[df.index >= cutoff_ts, ["vibration_mm_s", "bearing_temp_c", "motor_current_pu"]] = pd.NA

    # если данных нет — честно
    cols = ["vibration_mm_s", "bearing_temp_c", "motor_current_pu"]
    if df[cols].dropna(how="all").empty:
        return {
            "status": "NO_DATA",
            "reason": "нет связи/данных или отсечка по состоянию",
            "cutoff_ts": str(cutoff_ts) if cutoff_ts is not None else None,
            "state": state,
            "economics": economics,
        }

    thr = TelemetryThresholds()
    alarms = compute_alarms(df, thr)
    summary = summarize_telemetry(df)

    vib_max = pd.to_numeric(df["vibration_mm_s"], errors="coerce").max()
    tmp_max = pd.to_numeric(df["bearing_temp_c"], errors="coerce").max()
    cur_max = pd.to_numeric(df["motor_current_pu"], errors="coerce").max()

    vib_last = summary.get("vibration_last")
    tmp_last = summary.get("temp_last")
    cur_last = summary.get("current_last")

    def _to_float(x):
        return None if pd.isna(x) else float(x)

    return {
        "status": "OK",
        "state": state,
        "cutoff_ts": str(cutoff_ts) if cutoff_ts is not None else None,
        "last": {
            "vibration_mm_s": _to_float(vib_last),
            "bearing_temp_c": _to_float(tmp_last),
            "motor_current_pu": _to_float(cur_last),
        },
        "max": {
            "vibration_mm_s": _to_float(vib_max),
            "bearing_temp_c": _to_float(tmp_max),
            "motor_current_pu": _to_float(cur_max),
        },
        "alarms": alarms,
        "thresholds": {
            "vibration_warn": thr.vibration_warn,
            "vibration_alarm": thr.vibration_alarm,
            "temp_warn": thr.temp_warn,
            "temp_alarm": thr.temp_alarm,
            "current_warn": thr.current_warn,
            "current_alarm": thr.current_alarm,
        },
        "window_minutes": 240,
        "sample_step_sec": 30,
        "economics": economics,
    }
@dataclass
class MaintenanceRequest:
    request_id: str
    created_at: str
    machine_id: str
    machine_name: str
    priority: str
    recommended_action: str
    reason: str
    oee_percent: float | None
    stops_count: int | None
    telemetry_status: str
    telemetry_last: dict
    telemetry_max: dict
    alarms: dict
    estimated_loss: float | None
    currency: str | None
    ai: dict
    payload_for_erp: dict


def _infer_priority(telemetry_hint: dict | None, rec) -> str:
    # CRITICAL если есть alarm, иначе HIGH если warn, иначе MEDIUM
    if not telemetry_hint or telemetry_hint.get("status") != "OK":
        return "MEDIUM"
    alarms = telemetry_hint.get("alarms", {})
    if any(v == "alarm" for v in alarms.values()):
        return "CRITICAL"
    if any(v == "warn" for v in alarms.values()):
        return "HIGH"
    return "MEDIUM"


with right:
    st.subheader("Панель анализа")
    render_machine_panel(selected, df_oee, stops)

    # телеметрия (если включена)
    if cfg.get("features", {}).get("telemetry", False):
        st.divider()
        render_telemetry_panel(selected, cfg, stops)

    # --- AI ---
    st.divider()
    st.subheader("AI-рекомендации (DEMO)")

    if "ai_result" not in st.session_state:
        st.session_state.ai_result = None
    if "ai_error" not in st.session_state:
        st.session_state.ai_error = None

    st.subheader("What-if: простой / потери")

    eco = cfg.get("economics", {})
    planned_units = float(eco.get("planned_units_per_shift", 0) or 0)
    shift_hours = float(eco.get("shift_hours", 8) or 8)
    margin = float(eco.get("margin_per_unit", 0) or 0)
    currency = eco.get("currency", "USD")

    hours_stop = st.number_input("Если остановить на (часов)", min_value=0.0, value=2.0, step=0.5)
    units_per_hour = (planned_units / shift_hours) if shift_hours > 0 else 0.0
    estimated_loss = units_per_hour * margin * hours_stop

    c1, c2, c3 = st.columns(3)
    c1.metric("План/смена", f"{planned_units:,.0f} шт")
    c2.metric("Производительность", f"{units_per_hour:,.0f} шт/ч")
    c3.metric("Потери (what-if)", f"{estimated_loss:,.2f} {currency}")

    economics = {
        "planned_units_per_shift": planned_units,
        "shift_hours": shift_hours,
        "margin_per_unit": margin,
        "currency": currency,
        "what_if_stop_hours": hours_stop,
        "units_per_hour": units_per_hour,
        "estimated_loss": estimated_loss,
    }

    if st.button("Сгенерировать рекомендации", use_container_width=True):
        st.session_state.ai_error = None
        try:
            telemetry_hint = build_telemetry_hint(selected, cfg, stops, economics)

            st.session_state.ai_result = generate_recommendation(
                machine=selected,
                df_oee=df_oee,
                stops=stops,
                cfg=cfg,
                telemetry_hint=telemetry_hint,  # ✅ реальные цифры + экономика
            )
        except Exception as e:
            st.session_state.ai_result = None
            st.session_state.ai_error = str(e)

    if st.session_state.ai_error:
        st.error(st.session_state.ai_error)

    if st.session_state.ai_result:
        rec = st.session_state.ai_result
        st.markdown(
            f"""**Решение:** `{rec.decision}`
**Риск:** `{rec.risk}`

**Диагностика:** {rec.diagnosis}

**Обоснование:** {rec.rationale}
"""
        )

        if rec.cost_impact:
            st.info(rec.cost_impact)

        if rec.actions:
            st.write("**Действия:**")
            for a in rec.actions:
                st.write(f"- **{a.title}**" + (f": {a.details}" if a.details else ""))

        if rec.next_check:
            st.caption(f"Если продолжаем: {rec.next_check}")

st.divider()
st.subheader("Заявка на ТО (DEMO)")

if "maintenance_requests" not in st.session_state:
    st.session_state.maintenance_requests = []

can_create = st.session_state.get("ai_result") is not None

if not can_create:
    st.info("Сначала сгенерируйте AI-рекомендации — они попадут в заявку.")
else:
    rec = st.session_state.ai_result

    # telemetry_hint уже считали при генерации рекомендаций, но на всякий случай пересчитаем так же
    telemetry_hint = build_telemetry_hint(selected, cfg, stops, economics)

    default_priority = _infer_priority(telemetry_hint, rec)

    with st.form("maintenance_request_form"):
        priority = st.selectbox("Приоритет", ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                                index=["LOW","MEDIUM","HIGH","CRITICAL"].index(default_priority))
        work_type = st.selectbox("Тип работ", ["Диагностика", "Плановое ТО", "Ремонт", "Замена подшипника", "Проверка вибрации"])
        comment = st.text_area("Комментарий мастера (опционально)", placeholder="Например: проверить крепёж/подшипник, снять тренд вибрации...")

        submit = st.form_submit_button("Создать заявку ТО", use_container_width=True)

    if submit:
        req = MaintenanceRequest(
            request_id=f"MR-{uuid4().hex[:8].upper()}",
            created_at=datetime.now().isoformat(timespec="seconds"),
            machine_id=selected.machine_id,
            machine_name=getattr(selected, "name", selected.machine_id),
            priority=priority,
            recommended_action=getattr(rec, "decision", "SCHEDULE_MAINTENANCE"),
            reason=f"{work_type}. {comment}".strip(),
            oee_percent=getattr(selected, "oee_percent", None),
            stops_count=getattr(selected, "stops_count", None),
            telemetry_status=telemetry_hint.get("status") if telemetry_hint else "UNKNOWN",
            telemetry_last=(telemetry_hint.get("last") if telemetry_hint else {}),
            telemetry_max=(telemetry_hint.get("max") if telemetry_hint else {}),
            alarms=(telemetry_hint.get("alarms") if telemetry_hint else {}),
            estimated_loss=(economics.get("estimated_loss") if economics else None),
            currency=(economics.get("currency") if economics else None),
            ai={
                "decision": getattr(rec, "decision", None),
                "risk": getattr(rec, "risk", None),
                "diagnosis": getattr(rec, "diagnosis", None),
                "rationale": getattr(rec, "rationale", None),
                "actions": [a.model_dump() for a in getattr(rec, "actions", [])],
                "next_check": getattr(rec, "next_check", None),
                "cost_impact": getattr(rec, "cost_impact", None),
            },
            payload_for_erp={
                "system": "1C",
                "doc_type": "maintenance_request",
                "machine_id": selected.machine_id,
                "priority": priority,
                "work_type": work_type,
                "comment": comment,
                "telemetry": telemetry_hint,
                "economics": economics,
            }
        )

        st.session_state.maintenance_requests.insert(0, req)

        st.success(f"Заявка создана: {req.request_id}")

    if st.session_state.maintenance_requests:
        last_req = st.session_state.maintenance_requests[0]
        st.markdown(f"**Последняя заявка:** `{last_req.request_id}` • {last_req.created_at}")

        st.write("**Кратко:**")
        st.write(f"- Станок: **{last_req.machine_name}** (`{last_req.machine_id}`)")
        st.write(f"- Приоритет: **{last_req.priority}**")
        st.write(f"- Решение: `{last_req.recommended_action}` • Риск: `{last_req.ai.get('risk')}`")
        if last_req.estimated_loss is not None and last_req.currency:
            st.write(f"- What-if потери: **{last_req.estimated_loss:,.2f} {last_req.currency}**")

        with st.expander("JSON заявки (для интеграции/1С)"):
            st.code(json.dumps(asdict(last_req), ensure_ascii=False, indent=2), language="json")

ERP_URL = os.environ.get("ERP_URL", "http://127.0.0.1:8008")

st.divider()
st.subheader("Интеграция с ERP/1С (MOCK API)")

st.caption(f"ERP endpoint: {ERP_URL}")

if st.session_state.get("maintenance_requests"):
    last_req = st.session_state.maintenance_requests[0]

    colA, colB = st.columns([1, 1])
    with colA:
        send = st.button("Отправить заявку в ERP", use_container_width=True)

    if send:
        try:
            payload = last_req.payload_for_erp  # dict

            # минимально приведём к ожидаемому формату API:
            body = {
                "request_id": last_req.request_id,
                "created_at": last_req.created_at,
                "machine_id": last_req.machine_id,
                "priority": last_req.priority,
                "work_type": payload.get("work_type", "Диагностика"),
                "comment": payload.get("comment", ""),
                "telemetry": payload.get("telemetry", {}),
                "economics": payload.get("economics", {}),
                "ai": last_req.ai,
            }

            r = requests.post(f"{ERP_URL}/api/v1/maintenance_requests", json=body, timeout=8)
            r.raise_for_status()
            resp = r.json()

            st.success(f"Отправлено в ERP ✅ ERP_ID = {resp.get('erp_id')}")
        except Exception as e:
            st.error(f"Не удалось отправить в ERP: {e}")

    with colB:
        if st.button("Показать inbox ERP", use_container_width=True):
            try:
                r = requests.get(f"{ERP_URL}/api/v1/inbox", timeout=6)
                r.raise_for_status()
                st.json(r.json())
            except Exception as e:
                st.error(f"Не удалось прочитать inbox: {e}")
else:
    st.info("Заявок ещё нет — сначала создайте заявку ТО.")

if st.session_state.maintenance_requests:
    last_req = st.session_state.maintenance_requests[0]

st.subheader("Статус заявки (в ERP)")

# подтянуть текущий статус из ERP
try:
    r = requests.get(f"{ERP_URL}/api/v1/maintenance_requests/{last_req.request_id}", timeout=6)
    if r.status_code == 200:
        doc = r.json()
        current_status = doc.get("status", "NEW")
        st.write(f"Текущий статус: **{current_status}** (ERP_ID: `{doc.get('erp_id')}`)")
    else:
        current_status = "—"
        st.caption("Заявка ещё не отправлена в ERP (или не найдена).")
        doc = None
except Exception as e:
    current_status = "—"
    doc = None
    st.error(f"ERP недоступен: {e}")

# смена статуса
new_status = st.selectbox("Установить статус", ["NEW", "IN_PROGRESS", "DONE", "CANCELLED"], index=0)
note = st.text_input("Комментарий к статусу (опционально)", value="")

if st.button("Обновить статус в ERP", use_container_width=True):
    try:
        rr = requests.patch(
            f"{ERP_URL}/api/v1/maintenance_requests/{last_req.request_id}/status",
            json={"status": new_status, "note": note or None},
            timeout=6,
        )
        rr.raise_for_status()
        st.success(f"Статус обновлён: {new_status}")
    except Exception as e:
        st.error(f"Не удалось обновить статус: {e}")

# история
if st.button("Показать историю статусов", use_container_width=True):
    try:
        rr = requests.get(f"{ERP_URL}/api/v1/maintenance_requests/{last_req.request_id}/history", timeout=6)
        rr.raise_for_status()
        st.json(rr.json())
    except Exception as e:
        st.error(f"Не удалось получить историю: {e}")




