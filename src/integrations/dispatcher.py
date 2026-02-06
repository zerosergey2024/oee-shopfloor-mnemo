# src/integrations/dispatcher.py
from __future__ import annotations

from typing import Any, Dict

import os
import requests


def _integration_mode(config: dict) -> str:
    integrations = config.get("integrations", {}) or {}

    mode = integrations.get("mode")
    if mode:
        return str(mode).lower()

    # legacy
    target = integrations.get("target", "")
    if target == "google_sheets":
        return "google"

    return "erp"


def _send_to_erp(req: Any, config: dict) -> Dict[str, Any]:
    integrations = config.get("integrations", {}) or {}
    erp_cfg = integrations.get("erp", {}) or {}
    erp_url = erp_cfg.get("url") or os.environ.get("ERP_URL", "http://127.0.0.1:8008")

    payload = getattr(req, "payload_for_erp", {}) or {}
    body = {
        "request_id": getattr(req, "request_id", None),
        "created_at": getattr(req, "created_at", None),
        "machine_id": getattr(req, "machine_id", None),
        "priority": getattr(req, "priority", None),
        "work_type": payload.get("work_type", "Диагностика"),
        "comment": payload.get("comment", ""),
        "telemetry": payload.get("telemetry", {}),
        "economics": payload.get("economics", {}),
        "ai": getattr(req, "ai", {}) or {},
    }

    r = requests.post(f"{erp_url}/api/v1/maintenance_requests", json=body, timeout=8)
    r.raise_for_status()
    resp = r.json()

    return {
        "ok": True,
        "target": "erp",
        "erp_url": erp_url,
        "erp_id": resp.get("erp_id"),
    }


def dispatch_send_request(req: Any, config: dict) -> Dict[str, Any]:
    # Жёсткая диагностика на будущее
    if not isinstance(config, dict):
        raise TypeError(f"config must be dict, got: {type(config)}")

    mode = _integration_mode(config)

    if mode == "google":
        # Lazy import (чтобы ERP режим работал без google libs)
        from .google_sheets_sink import append_maintenance_request_to_sheet
        from .google_calendar_sink import create_maintenance_event

        res_sheet = append_maintenance_request_to_sheet(req, config)
        res_cal = create_maintenance_event(req, config)

        return {
            "ok": bool(res_sheet.get("ok")) and bool(res_cal.get("ok")),
            "target": "google",
            "sheets": res_sheet,
            "calendar": res_cal,
        }

    return _send_to_erp(req, config)



