from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import json

import gspread
from google.oauth2.service_account import Credentials


def _resolve_path(p: str) -> str:
    pp = Path(p)
    if pp.is_absolute():
        return str(pp)
    base = Path(__file__).resolve().parents[2]  # project root (where config/, secrets/, src/)
    return str((base / pp).resolve())


def _to_dict(obj: Any) -> Dict[str, Any]:
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "model_dump"):  # pydantic v2
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Unsupported object type for export: {type(obj)}")


def _ensure_header(ws, header: list[str]) -> None:
    if ws.get_all_values() == []:
        ws.append_row(header)


def append_maintenance_request_to_sheet(req: Any, cfg: dict) -> Dict[str, Any]:
    gs_cfg = (cfg.get("integrations", {}) or {}).get("google_sheets", {}) or {}

    creds_path = gs_cfg.get("credentials_json_path")
    spreadsheet_id = gs_cfg.get("spreadsheet_id")
    worksheet_title = gs_cfg.get("worksheet_title", "maintenance_requests")

    if not creds_path or not spreadsheet_id:
        raise ValueError("Google Sheets config missing: credentials_json_path/spreadsheet_id")

    creds_path = _resolve_path(creds_path)

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(credentials)

    sh = client.open_by_key(spreadsheet_id)

    try:
        ws = sh.worksheet(worksheet_title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_title, rows=1000, cols=30)

    d = _to_dict(req)

    row = {
        "created_at": d.get("created_at"),
        "request_id": d.get("request_id"),
        "machine_id": d.get("machine_id"),
        "machine_name": d.get("machine_name"),
        "priority": d.get("priority"),
        "status": "NEW",
        "work_type": (d.get("payload_for_erp", {}) or {}).get("work_type"),
        "comment": (d.get("payload_for_erp", {}) or {}).get("comment"),
        "decision": (d.get("ai", {}) or {}).get("decision"),
        "risk": (d.get("ai", {}) or {}).get("risk"),
        "oee_percent": d.get("oee_percent"),
        "estimated_loss": d.get("estimated_loss"),
        "currency": d.get("currency"),
        "payload_json": json.dumps(d, ensure_ascii=False),
        "ts_written": datetime.now().isoformat(timespec="seconds"),
    }

    header = list(row.keys())
    _ensure_header(ws, header)

    ws.append_row([row.get(k, "") for k in header], value_input_option="USER_ENTERED")

    return {
        "ok": True,
        "target": "google_sheets",
        "worksheet": worksheet_title,
        "spreadsheet_id": spreadsheet_id,
    }

