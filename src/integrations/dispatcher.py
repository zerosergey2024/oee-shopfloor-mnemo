# src/integrations/dispatcher.py
from __future__ import annotations

from typing import Any, Dict


def _integration_mode(config: dict) -> str:
    integrations = config.get("integrations", {}) or {}
    mode = integrations.get("mode", "erp")
    return str(mode).lower()


def dispatch_send_request(req: Any, config: dict) -> Dict[str, Any]:
    if not isinstance(config, dict):
        raise TypeError(f"config must be dict, got: {type(config)}")

    mode = _integration_mode(config)

    if mode == "google":
        from .google_sheets_sink import append_maintenance_request_to_sheet
        from .google_calendar_sink import create_maintenance_event

        res_sheet = append_maintenance_request_to_sheet(req, config)
        res_cal = create_maintenance_event(req, config)

        return {
            "ok": bool(res_sheet.get("ok")) and bool(res_cal.get("ok")),
            "target": "google",
            "spreadsheet_id": res_sheet.get("spreadsheet_id"),
            "worksheet": res_sheet.get("worksheet"),
            "calendar_id": res_cal.get("calendar_id"),
            "calendar_event_id": res_cal.get("calendar_event_id"),
            "calendar_link": res_cal.get("calendar_link"),
        }

    if mode == "erp":
        from .erp_1c_sink import dispatch_erp_1c
        return dispatch_erp_1c(req, config)

    raise ValueError(f"Unknown integrations.mode: {mode} (use 'google' or 'erp')")




