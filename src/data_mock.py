from datetime import datetime, date, time
from typing import List
from .models import MachineOverview, ShiftInfo
from .oee import calc_oee_percent

def get_mock_overview() -> List[MachineOverview]:
    shift_start = datetime.combine(date.today(), time(8, 0))
    shift_end = datetime.combine(date.today(), time(16, 0))

    oee_mill = calc_oee_percent(0.92, 0.88, 0.97)   # ~78.5
    oee_lathe = calc_oee_percent(0.85, 0.90, 0.99)  # ~75.7

    return [
        MachineOverview(
            machine_id="CNC-MILL-1",
            name="Фрезерный станок",
            kind="Фрезерный ЧПУ",
            state="RUN",
            shift=ShiftInfo(start=shift_start, end=shift_end),
            stops_count=3,
            run_time_hours=7.5,
            planned_time_hours=8.0,
            oee_percent=oee_mill,
        ),
        MachineOverview(
            machine_id="CNC-LATHE-1",
            name="Токарный станок",
            kind="Токарный ЧПУ",
            state="IDLE",
            shift=ShiftInfo(start=shift_start, end=shift_end),
            stops_count=1,
            run_time_hours=5.2,
            planned_time_hours=8.0,
            oee_percent=oee_lathe,
        ),
        MachineOverview(
            machine_id="CNC-CUT-1",
            name="Станок кроя металла",
            kind="Крой металла",
            state="DOWN",
            shift=ShiftInfo(start=shift_start, end=shift_end),
            down_start_ts=datetime.combine(date.today(), time(10, 20)),
            down_reason="REPAIR",
        ),
    ]
