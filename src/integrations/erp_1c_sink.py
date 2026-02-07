from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import requests


def _project_root() -> Path:
    # .../src/integrations/erp_1c_sink.py -> project root = parents[2]
    return Path(__file__).resolve().parents[2]


def _to_dict(obj: Any) -> Dict:
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "model_dump"):  # pydantic v2
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"Unsupported object type: {type(obj)}")


def _resolve_outbox_dir(config: dict) -> Path:
    integrations = config.get("integrations", {}) or {}
    erp_cfg = integrations.get("erp", {}) or {}

    rel = erp_cfg.get("exchange_outbox_dir", "exchange/outbox")
    base = _project_root()
    outbox = (base / rel).resolve()
    outbox.mkdir(parents=True, exist_ok=True)
    return outbox


def _resolve_erp_url(config: dict) -> str:
    integrations = config.get("integrations", {}) or {}
    erp_cfg = integrations.get("erp", {}) or {}
    return erp_cfg.get("url") or os.environ.get("ERP_URL", "http://127.0.0.1:8008")


def write_exchange_file(req: Any, config: dict) -> Dict[str, Any]:
    outbox = _resolve_outbox_dir(config)
    d = _to_dict(req)

    request_id = d.get("request_id") or "MR-UNKNOWN"
    filepath = outbox / f"{request_id}.json"

    # Пишем полный payload (как в JSON экспандере)
    filepath.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "target": "exchange_outbox",
        "path": str(filepath),
    }


def send_to_erp_api(req: Any, config: dict) -> Dict[str, Any]:
    erp_url = _resolve_erp_url(config)

    payload_for_erp = getattr(req, "payload_for_erp", {}) or {}
    body = {
        "request_id": getattr(req, "request_id", None),
        "created_at": getattr(req, "created_at", None),
        "machine_id": getattr(req, "machine_id", None),
        "priority": getattr(req, "priority", None),
        "work_type": payload_for_erp.get("work_type", "Диагностика"),
        "comment": payload_for_erp.get("comment", ""),
        "telemetry": payload_for_erp.get("telemetry", {}) or {},
        "economics": payload_for_erp.get("economics", {}) or {},
        "ai": getattr(req, "ai", {}) or {},
    }

    r = requests.post(f"{erp_url}/api/v1/maintenance_requests", json=body, timeout=8)

    if r.status_code == 409:
        # Уже есть в ERP: считаем успехом и читаем документ
        rr = requests.get(f"{erp_url}/api/v1/maintenance_requests/{body['request_id']}", timeout=6)
        rr.raise_for_status()
        doc = rr.json()
        return {
            "ok": True,
            "target": "erp_api",
            "erp_url": erp_url,
            "erp_id": doc.get("erp_id"),
            "received_at": doc.get("received_at"),
            "status": doc.get("status", "NEW"),
            "note": "ALREADY_EXISTS",
        }

    r.raise_for_status()
    resp = r.json()

    return {
        "ok": True,
        "target": "erp_api",
        "erp_url": erp_url,
        "erp_id": resp.get("erp_id"),
        "received_at": resp.get("received_at"),
        "status": resp.get("status", "NEW"),
    }

def dispatch_erp_1c(req: Any, config: dict) -> Dict[str, Any]:
    # 1) обязательно пишем файл в exchange/outbox
    res_file = write_exchange_file(req, config)

    # 2) отправляем в mock ERP API
    res_api = send_to_erp_api(req, config)

    # 3) для демо формируем "1С регистрационный номер"
    erp_id = res_api.get("erp_id") or "ERP-000000"
    zn = erp_id.replace("ERP-", "ЗН-")
    today = datetime.now().date().isoformat()

    return {
        "ok": bool(res_file.get("ok")) and bool(res_api.get("ok")),
        "target": "erp_1c",
        "exchange": res_file,
        "erp": res_api,
        "registered": {
            "zn_number": zn,
            "date": today,
        },
    }
