from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import List, Literal
import pandas as pd

from .models import MachineOverview, ShiftInfo, StopEvent
from .oee import calc_oee_percent

Profile = Literal["BASIC", "STANDARD", "ADVANCED"]

def _shift_window():
    shift_start = datetime.combine(date.today(), time(8, 0))
    shift_end = datetime.combine(date.today(), time(16, 0))
    return shift_start, shift_end

def get_mock_overview(profile: Profile) -> List[MachineOverview]:
    shift_start, shift_end = _shift_window()

    # БАЗОВЫЕ значения — общая “истина”
    oee_mill_base = calc_oee_percent(0.92, 0.88, 0.97)   # ~78.5
    oee_lathe_base = calc_oee_percent(0.85, 0.90, 0.99)  # ~75.7

    # Отличия по профилям:
    # BASIC: более “грубая” картина, меньше точность => чуть ниже OEE и меньше деталей
    # STANDARD: ближе к базе (MES агрегирует, стабилизирует)
    # ADVANCED: ближе к базе, но может показывать проблемы/провалы из-за микростопов
    if profile == "BASIC":
        oee_mill = max(0.0, oee_mill_base - 3.0)
        oee_lathe = max(0.0, oee_lathe_base - 2.0)
        mill_stops = 2
        lathe_stops = 1
    elif profile == "STANDARD":
        oee_mill = oee_mill_base
        oee_lathe = oee_lathe_base
        mill_stops = 3
        lathe_stops = 2
    else:  # ADVANCED
        oee_mill = oee_mill_base
        oee_lathe = oee_lathe_base
        mill_stops = 6  # больше событий, включая микростопы
        lathe_stops = 4

    # Можно сделать, чтобы BASIC чаще показывал IDLE (в реальности так и бывает из-за ручного ввода)
    lathe_state = "IDLE" if profile == "BASIC" else "IDLE"  # оставим как есть для демо
    cut_state = "DOWN"  # пусть всегда будет ремонтный пример

    return [
        MachineOverview(
            machine_id="CNC-MILL-1",
            name="Фрезерный станок",
            kind="Фрезерный ЧПУ",
            state="RUN",
            shift=ShiftInfo(start=shift_start, end=shift_end),
            stops_count=mill_stops,
            run_time_hours=7.5,
            planned_time_hours=8.0,
            oee_percent=oee_mill,
        ),
        MachineOverview(
            machine_id="CNC-LATHE-1",
            name="Токарный станок",
            kind="Токарный ЧПУ",
            state=lathe_state,
            shift=ShiftInfo(start=shift_start, end=shift_end),
            stops_count=lathe_stops,
            run_time_hours=5.2 if profile != "BASIC" else 4.8,
            planned_time_hours=8.0,
            oee_percent=oee_lathe,
        ),
        MachineOverview(
            machine_id="CNC-CUT-1",
            name="Станок кроя металла",
            kind="Крой металла",
            state=cut_state,
            shift=ShiftInfo(start=shift_start, end=shift_end),
            down_start_ts=datetime.combine(date.today(), time(10, 20)),
            down_reason="REPAIR",
        ),
    ]

def get_mock_machine_timeseries(machine_id: str, profile: Profile) -> pd.DataFrame:
    """
    OEE (%) за смену с шагом 15 минут.
    - BASIC: более грубые значения (меньше динамики, хуже точность)
    - STANDARD: сглаженные (агрегация MES)
    - ADVANCED: больше динамики, провалы от микростопов (near-real-time)
    """
    shift_start, shift_end = _shift_window()
    idx = pd.date_range(shift_start, shift_end, freq="15min")

    base_map = {
        "CNC-MILL-1": 78.5,
        "CNC-LATHE-1": 75.7,
        "CNC-CUT-1": 60.0,
    }
    base = base_map.get(machine_id, 70.0)

    vals = []
    for i, _ts in enumerate(idx):
        # базовая “волна”
        drift = (i % 8) - 4  # -4..+3
        v = base + drift * 1.2

        if profile == "BASIC":
            # BASIC: меньше детализации — сделаем ряд более “плоским”
            v = base + (drift * 0.6)
        elif profile == "STANDARD":
            # STANDARD: ближе к реальности и слегка сглажено
            v = base + (drift * 1.0)
        else:
            # ADVANCED: больше динамики + периодические просадки (микростопы)
            v = base + (drift * 1.4)
            if i % 6 == 0:  # провал раз в ~1.5 часа
                v *= 0.88

        vals.append(max(0.0, min(100.0, v)))

    df = pd.DataFrame({"timestamp": idx, "oee_percent": vals}).set_index("timestamp")

    # CNC-CUT-1: имитируем останов в 10:20 (после него OEE ~0)
    if machine_id == "CNC-CUT-1":
        down_ts = datetime.combine(date.today(), time(10, 20))
        df.loc[df.index >= down_ts, "oee_percent"] = 0.0

    # STANDARD: сглаживание (агрегация событий MES)
    if profile == "STANDARD":
        df["oee_percent"] = df["oee_percent"].rolling(3, min_periods=1).mean()

    return df

def get_mock_stops(machine_id: str, profile: Profile) -> List[StopEvent]:
    """
    Остановки:
    - BASIC: только крупные остановки (ручной ввод)
    - STANDARD: структурированные причины (MES)
    - ADVANCED: добавляем микростопы (IoT)
    """
    shift_start, _shift_end = _shift_window()

    stops: List[StopEvent] = []

    if machine_id == "CNC-MILL-1":
        # Базовый набор (крупные)
        stops = [
            StopEvent(start=shift_start + timedelta(hours=3, minutes=35),
                      end=shift_start + timedelta(hours=3, minutes=55),
                      reason="SETUP", note="Смена инструмента"),
            StopEvent(start=shift_start + timedelta(hours=6, minutes=5),
                      end=shift_start + timedelta(hours=6, minutes=15),
                      reason="FAULT", note="Сигнал дверцы/датчик"),
        ]
        if profile in ("STANDARD", "ADVANCED"):
            stops.insert(0, StopEvent(
                start=shift_start + timedelta(hours=1, minutes=10),
                end=shift_start + timedelta(hours=1, minutes=18),
                reason="MICROSTOP" if profile == "ADVANCED" else "FAULT",
                note="Снятие стружки" if profile == "ADVANCED" else "Кратковременная остановка"
            ))
        if profile == "ADVANCED":
            stops += [
                StopEvent(start=shift_start + timedelta(hours=2, minutes=5),
                          end=shift_start + timedelta(hours=2, minutes=7),
                          reason="MICROSTOP", note="Автодетект: подача/стружка"),
                StopEvent(start=shift_start + timedelta(hours=5, minutes=15),
                          end=shift_start + timedelta(hours=5, minutes=16),
                          reason="MICROSTOP", note="Автодетект: датчик двери"),
            ]

    elif machine_id == "CNC-LATHE-1":
        stops = [
            StopEvent(start=shift_start + timedelta(hours=4, minutes=0),
                      end=shift_start + timedelta(hours=4, minutes=25),
                      reason="SETUP", note="Переналадка"),
        ]
        if profile == "ADVANCED":
            stops += [
                StopEvent(start=shift_start + timedelta(hours=1, minutes=50),
                          end=shift_start + timedelta(hours=1, minutes=52),
                          reason="MICROSTOP", note="Автодетект: краткая пауза"),
                StopEvent(start=shift_start + timedelta(hours=6, minutes=40),
                          end=shift_start + timedelta(hours=6, minutes=41),
                          reason="MICROSTOP", note="Автодетект: сброс датчика"),
            ]
        if profile == "BASIC":
            # BASIC: допустим, оператор внёс только одну крупную остановку без детализации
            stops = [
                StopEvent(start=shift_start + timedelta(hours=4, minutes=0),
                          end=shift_start + timedelta(hours=4, minutes=25),
                          reason="SETUP", note=None),
            ]

    elif machine_id == "CNC-CUT-1":
        # Пример ремонта одинаковый, но в ADVANCED можно “видеть” дополнительные события до отказа
        stops = [
            StopEvent(start=shift_start + timedelta(hours=2, minutes=20),
                      end=shift_start + timedelta(hours=4, minutes=0),
                      reason="REPAIR", note="Замена ремня/настройка подачи"),
        ]
        if profile == "ADVANCED":
            stops.insert(0, StopEvent(
                start=shift_start + timedelta(hours=2, minutes=5),
                end=shift_start + timedelta(hours=2, minutes=7),
                reason="MICROSTOP",
                note="Автодетект: рост нагрузки перед отказом"
            ))

    # STANDARD: причины более “MES-подобные” (без MICROSTOP как класса)
    if profile == "STANDARD":
        for s in stops:
            if s.reason == "MICROSTOP":
                s.reason = "FAULT"  # в MES часто уйдёт как “краткий простои/авария” без детализации

    return stops


