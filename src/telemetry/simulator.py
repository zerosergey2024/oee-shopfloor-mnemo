# src/telemetry/simulator.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TelemetryThresholds:
    vibration_warn: float = 8.0     # мм/с
    vibration_alarm: float = 11.0   # мм/с
    temp_warn: float = 80.0         # °C
    temp_alarm: float = 92.0        # °C
    current_warn: float = 0.85      # доля от номинала (0..1)
    current_alarm: float = 0.95


def _seed_from(machine_id: str, level: str) -> int:
    # стабильная “случайность” по станку и уровню
    return abs(hash((machine_id, level))) % (2**32)


def generate_telemetry_df(
    machine_id: str,
    level: str,
    state: str,
    minutes: int = 240,
    step_sec: int = 30,
) -> pd.DataFrame:
    """
    Генерирует телеметрию за последние N минут.
    state: RUN/IDLE/DOWN влияет на форму сигналов.
    """
    end = datetime.now().replace(microsecond=0)
    start = end - timedelta(minutes=minutes)
    idx = pd.date_range(start=start, end=end, freq=f"{step_sec}s")

    rng = np.random.default_rng(_seed_from(machine_id, level))

    n = len(idx)
    t = np.linspace(0, 1, n)

    # Базовый профиль (в зависимости от state)
    if state == "RUN":
        vib_base = 6.0 + 1.2 * np.sin(2 * np.pi * 2 * t)
        tmp_base = 72.0 + 6.0 * t
        cur_base = 0.75 + 0.08 * np.sin(2 * np.pi * 1.5 * t)
        noise_scale = 0.35
    elif state == "IDLE":
        # Остановлен: ток почти 0, вибрация почти 0, температура плавно остывает
        vib_base = np.full(n, 0.4)
        # охлаждение: от ~55 к ~40
        tmp_base = 40.0 + (55.0 - 40.0) * np.exp(-4.0 * t)
        cur_base = np.full(n, 0.03)
        noise_scale = 0.10

    else:  # DOWN
        # В ремонте/ТО: считаем, что связь отсутствует (оборудование отключено)
        df = pd.DataFrame(
            {
                "timestamp": idx,
                "vibration_mm_s": [np.nan] * n,
                "bearing_temp_c": [np.nan] * n,
                "motor_current_pu": [np.nan] * n,
            }
        ).set_index("timestamp")
        return df

    # Редкие “рывки”/аномалии для демо (только RUN)
    spikes = np.zeros(n)
    if state == "RUN":
        spike_count = 2 if level == "BASIC" else 3 if level == "STANDARD" else 4
        positions = rng.choice(np.arange(int(n * 0.15), int(n * 0.95)), size=spike_count, replace=False)
        for p in positions:
            width = rng.integers(10, 25)
            height = rng.uniform(1.5, 4.0)
            spikes[p : min(n, p + width)] += height * np.exp(-np.linspace(0, 2.0, min(n, p + width) - p))

    vibration = vib_base + spikes + rng.normal(0, noise_scale, n)
    temperature = tmp_base + 0.6 * spikes + rng.normal(0, noise_scale * 1.8, n)
    current = cur_base + 0.08 * (spikes / 4.0) + rng.normal(0, noise_scale * 0.12, n)

    # Ограничения
    vibration = np.clip(vibration, 0.0, 20.0)
    temperature = np.clip(temperature, 0.0, 130.0)
    current = np.clip(current, 0.0, 1.2)

    df = pd.DataFrame(
        {
            "timestamp": idx,
            "vibration_mm_s": np.round(vibration, 2),
            "bearing_temp_c": np.round(temperature, 1),
            "motor_current_pu": np.round(current, 2),  # per-unit 0..1 (условно)
        }
    ).set_index("timestamp")

    return df


def compute_alarms(df: pd.DataFrame, thr: TelemetryThresholds) -> Dict[str, str]:
    """
    Возвращает статусы по каналам: ok / warn / alarm.
    """
    def status(value: float, warn: float, alarm: float) -> str:
        if value >= alarm:
            return "alarm"
        if value >= warn:
            return "warn"
        return "ok"

    last_valid = df[["vibration_mm_s", "bearing_temp_c", "motor_current_pu"]].dropna(how="any").tail(1)
    if last_valid.empty:
        return {"vibration": "ok", "temperature": "ok", "current": "ok"}

    last = last_valid.iloc[0]
    return {
        "vibration": status(float(last["vibration_mm_s"]), thr.vibration_warn, thr.vibration_alarm),
        "temperature": status(float(last["bearing_temp_c"]), thr.temp_warn, thr.temp_alarm),
        "current": status(float(last["motor_current_pu"]), thr.current_warn, thr.current_alarm),
    }


def summarize_telemetry(df: pd.DataFrame) -> Dict[str, float]:
    cols = ["vibration_mm_s", "bearing_temp_c", "motor_current_pu"]
    last_valid = df[cols].dropna(how="any").tail(1)
    if last_valid.empty:
        return {
            "vibration_last": float("nan"),
            "temp_last": float("nan"),
            "current_last": float("nan"),
            "vibration_max": float(df["vibration_mm_s"].max(skipna=True)),
            "temp_max": float(df["bearing_temp_c"].max(skipna=True)),
            "current_max": float(df["motor_current_pu"].max(skipna=True)),
        }
    last = last_valid.iloc[0]
    return {
        "vibration_last": float(last["vibration_mm_s"]),
        "temp_last": float(last["bearing_temp_c"]),
        "current_last": float(last["motor_current_pu"]),
        "vibration_max": float(df["vibration_mm_s"].max(skipna=True)),
        "temp_max": float(df["bearing_temp_c"].max(skipna=True)),
        "current_max": float(df["motor_current_pu"].max(skipna=True)),
    }
