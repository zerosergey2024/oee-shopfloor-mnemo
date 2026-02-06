from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict
import json

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


def _resolve_path(p: str) -> str:
    pp = Path(p)
    if pp.is_absolute():
        return str(pp)
    base = Path(__file__).resolve().parents[2]
    return str((base / pp).resolve())


def _to_dict(obj: Any) -> Dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Unsupported object type for export: {type(obj)}")


def create_maintenance_event(req: Any, cfg: dict) -> Dict[str, Any]:
    cal_cfg = (cfg.get("integrations", {}) or {}).get("google_calendar", {}) or {}

    creds_path = cal_cfg.get("credentials_json_path")
    calendar_id = cal_cfg.get("calendar_id", "primary")
    duration_min = int(cal_cfg.get("default_duration_min", 120))

    if not creds_path:
        raise ValueError("Google Calendar config missing: credentials_json_path")

    creds_path = _resolve_path(creds_path)

    scopes = ["https://www.googleapis.com/auth/calendar"]
    credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)

    d = _to_dict(req)

    # старт события: created_at заявки (можно поменять на “через час” и т.п.)
    start_dt = datetime.fromisoformat(d["created_at"])
    end_dt = start_dt + timedelta(minutes=duration_min)

    machine_name = d.get("machine_name") or d.get("machine_id")
    summary = f"ТО: {machine_name} [{d.get('priority', 'MEDIUM')}]"
    description = {
        "request_id": d.get("request_id"),
        "machine_id": d.get("machine_id"),
        "reason": d.get("reason"),
        "decision": (d.get("ai", {}) or {}).get("decision"),
        "risk": (d.get("ai", {}) or {}).get("risk"),
        "estimated_loss": d.get("estimated_loss"),
        "currency": d.get("currency"),
    }

    event = {
        "summary": summary,
        "description": json.dumps(description, ensure_ascii=False, indent=2),
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
    }

    created = service.events().insert(calendarId=calendar_id, body=event).execute()
    return {
        "ok": True,
        "target": "google_calendar",
        "calendar_id": calendar_id,
        "calendar_event_id": created.get("id"),
        "htmlLink": created.get("htmlLink"),
    }
