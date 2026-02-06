from __future__ import annotations
from dataclasses import asdict

import requests

def _safe_dict(req) -> dict:
    # если req — dataclass
    try:
        return asdict(req)
    except Exception:
        return dict(req)

def send_request(req, cfg: dict) -> tuple[dict, str]:
    """
    Возвращает: (external_ids, target)
    target: "ERP" или "GOOGLE"
    """
    mode = (cfg.get("integrations", {}) or {}).get("mode")

    if mode == "google":
        external = {}
        # 1) Google Sheets
        from src.integrations.google_sheets_sink import append_maintenance_request
        external.update(append_maintenance_request(req=req, cfg=cfg))

        # 2) Google Calendar (событие ТО)
        from src.integrations.calendar_sink import create_maintenance_event
        external.update(create_maintenance_event(req=req, cfg=cfg))

        return external, "GOOGLE"

    # default -> ERP
    erp_url = (cfg.get("integrations", {}) or {}).get("erp_url") or \
              __import__("os").environ.get("ERP_URL", "http://127.0.0.1:8008")

    payload = req.payload_for_erp
    body = {
        "request_id": req.request_id,
        "created_at": req.created_at,
        "machine_id": req.machine_id,
        "priority": req.priority,
        "work_type": payload.get("work_type", "Диагностика"),
        "comment": payload.get("comment", ""),
        "telemetry": payload.get("telemetry", {}),
        "economics": payload.get("economics", {}),
        "ai": req.ai,
    }

    r = requests.post(f"{erp_url}/api/v1/maintenance_requests", json=body, timeout=8)
    r.raise_for_status()
    resp = r.json()
    return {"erp_id": resp.get("erp_id")}, "ERP"
