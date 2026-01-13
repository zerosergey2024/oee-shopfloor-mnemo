from datetime import datetime, date, time, timedelta
from typing import List
import pandas as pd

from .models import MachineOverview, ShiftInfo, StopEvent
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

def get_mock_machine_timeseries(machine_id: str) -> pd.DataFrame:
    """
    Возвращает временной ряд OEE (%) за смену с шагом 15 минут.
    Для DOWN станка ряд будет до момента останова (для демо).
    """
    shift_start = datetime.combine(date.today(), time(8, 0))
    shift_end = datetime.combine(date.today(), time(16, 0))
    idx = pd.date_range(shift_start, shift_end, freq="15min")

    # Базовые уровни по станкам (демо)
    base = {
        "CNC-MILL-1": 78.5,
        "CNC-LATHE-1": 75.7,
        "CNC-CUT-1": 60.0,
    }.get(machine_id, 70.0)

    # Простая “волна” без numpy, чтобы не тянуть зависимость
    vals = []
    for i, ts in enumerate(idx):
        drift = (i % 8) - 4  # -4..+3
        vals.append(max(0.0, min(100.0, base + drift * 1.2)))

    df = pd.DataFrame({"timestamp": idx, "oee_percent": vals}).set_index("timestamp")

    # Для CNC-CUT-1 имитируем останов в 10:20 (ряд после него занижаем)
    if machine_id == "CNC-CUT-1":
        down_ts = datetime.combine(date.today(), time(10, 20))
        df.loc[df.index >= down_ts, "oee_percent"] = 0.0

    return df

def get_mock_stops(machine_id: str) -> List[StopEvent]:
    shift_start = datetime.combine(date.today(), time(8, 0))

    if machine_id == "CNC-MILL-1":
        return [
            StopEvent(start=shift_start + timedelta(hours=1, minutes=10),
                      end=shift_start + timedelta(hours=1, minutes=18),
                      reason="MICROSTOP", note="Снятие стружки"),
            StopEvent(start=shift_start + timedelta(hours=3, minutes=35),
                      end=shift_start + timedelta(hours=3, minutes=55),
                      reason="SETUP", note="Смена инструмента"),
            StopEvent(start=shift_start + timedelta(hours=6, minutes=5),
                      end=shift_start + timedelta(hours=6, minutes=15),
                      reason="FAULT", note="Сигнал дверцы/датчик"),
        ]

    if machine_id == "CNC-LATHE-1":
        return [
            StopEvent(start=shift_start + timedelta(hours=4, minutes=0),
                      end=shift_start + timedelta(hours=4, minutes=25),
                      reason="SETUP", note="Переналадка"),
        ]

    if machine_id == "CNC-CUT-1":
        return [
            StopEvent(start=shift_start + timedelta(hours=2, minutes=20),
                      end=shift_start + timedelta(hours=4, minutes=0),
                      reason="REPAIR", note="Замена ремня/настройка подачи"),
        ]

    return []

