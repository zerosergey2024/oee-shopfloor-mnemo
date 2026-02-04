from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd

from .client import get_openai_client, get_model_name
from .prompts import SYSTEM_INSTRUCTIONS, build_input_payload
from .schemas import AiRecommendation
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI()

def _machine_to_dict(machine: Any) -> Dict[str, Any]:
    # MachineOverview -> dict (бережно, без зависимости от точных полей)
    return {
        "machine_id": getattr(machine, "machine_id", None),
        "name": getattr(machine, "name", None),
        "kind": getattr(machine, "kind", None),
        "state": getattr(machine, "state", None),
        "oee_percent": getattr(machine, "oee_percent", None),
        "stops_count": getattr(machine, "stops_count", None),
        "run_time_hours": getattr(machine, "run_time_hours", None),
        "planned_time_hours": getattr(machine, "planned_time_hours", None),
        "down_start_ts": str(getattr(machine, "down_start_ts", None)) if getattr(machine, "down_start_ts", None) else None,
        "down_reason": getattr(machine, "down_reason", None),
        "shift": {
            "start": str(getattr(getattr(machine, "shift", None), "start", None)),
            "end": str(getattr(getattr(machine, "shift", None), "end", None)),
        },
    }


def _df_preview(df_oee: Any, max_rows: int = 12) -> List[Dict[str, Any]]:
    # df_oee может быть DataFrame / dict / list
    if isinstance(df_oee, dict):
        df = pd.DataFrame(df_oee)
    elif isinstance(df_oee, list):
        df = pd.DataFrame(df_oee)
    elif isinstance(df_oee, pd.DataFrame):
        df = df_oee.copy()
    else:
        return []

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp")
    else:
        df = df.reset_index().rename(columns={"index": "timestamp"})

    # нормализуем имя колонки OEE
    col_candidates = ["oee_percent", "OEE_percent", "oee", "OEE"]
    oee_col = next((c for c in col_candidates if c in df.columns), None)
    if oee_col and oee_col != "oee_percent":
        df = df.rename(columns={oee_col: "oee_percent"})

    cols = [c for c in ["timestamp", "oee_percent"] if c in df.columns]
    if not cols:
        cols = list(df.columns)[:2]

    tail = df[cols].tail(max_rows)
    # timestamp -> строка
    out = []
    for _, row in tail.iterrows():
        rec = {k: (str(row[k]) if k == "timestamp" else row[k]) for k in cols}
        out.append(rec)
    return out


def _stops_preview(stops: List[Any], max_rows: int = 12) -> List[Dict[str, Any]]:
    out = []
    # последние сверху
    stops_sorted = sorted(stops or [], key=lambda s: getattr(s, "start", None) or 0, reverse=True)
    for s in stops_sorted[:max_rows]:
        out.append(
            {
                "start": str(getattr(s, "start", None)),
                "end": str(getattr(s, "end", None)) if getattr(s, "end", None) else None,
                "reason": getattr(s, "reason", None),
                "duration_min": getattr(s, "duration_min", None),
                "note": getattr(s, "note", None),
            }
        )
    return out


def generate_recommendation(
    machine: Any,
    df_oee: Any,
    stops: List[Any],
    cfg: Dict[str, Any],
    telemetry_hint: Optional[Dict[str, Any]] = None,
) -> AiRecommendation:
    client = get_openai_client()
    model = get_model_name()

    input_text = build_input_payload(
        machine=_machine_to_dict(machine),
        oee_df_preview=_df_preview(df_oee),
        stops_preview=_stops_preview(stops),
        telemetry_hint=telemetry_hint,
        cfg=cfg,
    )

    # Responses API — рекомендованный путь для новых интеграций :contentReference[oaicite:2]{index=2}
    resp = client.responses.create(
        model=model,
        instructions=SYSTEM_INSTRUCTIONS,
        input=input_text,
    )

    text = resp.output_text.strip()

    # Модель обязана вернуть JSON; если вернёт мусор — пытаемся извлечь JSON
    try:
        data = json.loads(text)
    except Exception:
        # fallback: найти первую/последнюю фигурную скобку
        l = text.find("{")
        r = text.rfind("}")
        if l != -1 and r != -1 and r > l:
            data = json.loads(text[l : r + 1])
        else:
            raise

    return AiRecommendation.model_validate(data)
