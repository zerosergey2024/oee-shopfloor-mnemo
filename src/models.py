from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

MachineState = Literal["RUN", "IDLE", "DOWN"]
DownReason = Optional[Literal["MAINT", "REPAIR"]]

class ShiftInfo(BaseModel):
    start: datetime
    end: datetime

class MachineOverview(BaseModel):
    machine_id: str
    name: str
    kind: str  # "Фрезерный ЧПУ", "Токарный ЧПУ", "Крой металла"
    state: MachineState

    # RUN/IDLE
    shift: ShiftInfo
    stops_count: int = 0
    run_time_hours: float = 0.0
    planned_time_hours: float = 0.0
    oee_percent: Optional[float] = None

    # DOWN
    down_start_ts: Optional[datetime] = None
    down_reason: DownReason = None
