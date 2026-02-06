from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Mock ERP API", version="0.2")

Status = Literal["NEW", "IN_PROGRESS", "DONE", "CANCELLED"]

STORE: Dict[str, Dict[str, Any]] = {}          # request_id -> document
HISTORY: Dict[str, List[Dict[str, Any]]] = {}  # request_id -> events


class MaintenanceRequestIn(BaseModel):
    request_id: str
    created_at: datetime
    machine_id: str
    priority: str
    work_type: str
    comment: Optional[str] = None
    telemetry: Dict[str, Any] = Field(default_factory=dict)
    economics: Dict[str, Any] = Field(default_factory=dict)
    ai: Dict[str, Any] = Field(default_factory=dict)


class MaintenanceRequestOut(BaseModel):
    ok: bool
    erp_id: str
    received_at: str
    status: Status


@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.now().isoformat(timespec="seconds")}


@app.post("/api/v1/maintenance_requests", response_model=MaintenanceRequestOut)
def create_request(req: MaintenanceRequestIn):
    if req.request_id in STORE:
        raise HTTPException(status_code=409, detail="request_id already exists")

    received_at = datetime.now().isoformat(timespec="seconds")
    erp_id = f"ERP-{len(STORE) + 1:06d}"

    doc = req.model_dump()
    doc.update({
        "created_at": req.created_at.isoformat(timespec="seconds"),
        "erp_id": erp_id,
        "received_at": received_at,
        "status": "NEW",
    })

    STORE[req.request_id] = doc
    HISTORY.setdefault(req.request_id, []).append({
        "ts": received_at,
        "event": "CREATED",
        "status": "NEW",
    })

    return {"ok": True, "erp_id": erp_id, "received_at": received_at, "status": "NEW"}


@app.get("/api/v1/inbox")
def inbox():
    items = list(STORE.values())
    items.sort(key=lambda x: x.get("received_at", ""), reverse=True)
    return {"count": len(items), "items": items[:50]}


@app.get("/api/v1/maintenance_requests/{request_id}")
def get_request(request_id: str):
    doc = STORE.get(request_id)
    if not doc:
        raise HTTPException(status_code=404, detail="request_id not found")
    return doc


class StatusUpdateIn(BaseModel):
    status: Status
    note: Optional[str] = None


@app.patch("/api/v1/maintenance_requests/{request_id}/status")
def update_status(request_id: str, upd: StatusUpdateIn):
    doc = STORE.get(request_id)
    if not doc:
        raise HTTPException(status_code=404, detail="request_id not found")

    ts = datetime.now().isoformat(timespec="seconds")
    doc["status"] = upd.status
    doc["status_updated_at"] = ts
    if upd.note:
        doc["status_note"] = upd.note
    else:
        doc.pop("status_note", None)

    HISTORY.setdefault(request_id, []).append({
        "ts": ts,
        "event": "STATUS_CHANGED",
        "status": upd.status,
        "note": upd.note,
    })

    return {"ok": True, "request_id": request_id, "status": upd.status, "ts": ts}


@app.get("/api/v1/maintenance_requests/{request_id}/history")
def get_history(request_id: str):
    if request_id not in HISTORY:
        raise HTTPException(status_code=404, detail="request_id not found")
    return {"request_id": request_id, "events": HISTORY[request_id]}


@app.get("/")
def root():
    return {
        "service": "Mock ERP API",
        "ok": True,
        "endpoints": ["/health", "/api/v1/maintenance_requests", "/api/v1/inbox"],
    }


