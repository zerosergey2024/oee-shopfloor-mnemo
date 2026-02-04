from __future__ import annotations
import json
from typing import Any, Dict, List

SYSTEM_INSTRUCTIONS = """Ты — инженер по надежности (RME) и OEE-аналитик.
Тебе дан JSON с: состоянием станка, OEE (превью), остановками и telemetry_hint.

Правила:
- Используй telemetry_hint.last / telemetry_hint.max / telemetry_hint.alarms / thresholds как основу диагностики.
- Если telemetry_hint.status == "NO_DATA" — не делай выводы по датчикам, явно напиши "нет данных".
- Не выдумывай чисел. Если цифры отсутствуют — ставь "—" и поясняй.
- Если есть telemetry_hint.economics.estimated_loss — используй это число в cost_impact.

Правила экономики:
- Если telemetry_hint содержит economics (estimated_loss, units_per_hour, margin_per_unit) — используй эти значения.
- Никаких “примерно/на глаз” по деньгам: только то, что передано во входе.
- Не пересчитывай самостоятельно, не выдумывай валюту/маржу.
- Ответ строго JSON (без markdown) по указанной схеме.
"""
def build_input_payload(
    machine: Dict[str, Any],
    oee_df_preview: List[Dict[str, Any]],
    stops_preview: List[Dict[str, Any]],
    telemetry_hint: Dict[str, Any] | None,
    cfg: Dict[str, Any],
) -> str:
    payload = {
        "level": cfg.get("level"),
        "machine": machine,
        "oee_timeseries_preview": oee_df_preview,
        "stops_preview": stops_preview,
        "telemetry_hint": telemetry_hint,
        "goal": "Дать решение STOP/CONTINUE/MONITOR, риск и шаги (ТО/ремонт/запчасти/план).",
        "output_format": {
            "decision": "STOP|CONTINUE|MONITOR",
            "risk": "LOW|MEDIUM|HIGH",
            "diagnosis": "string",
            "rationale": "string",
            "actions": [{"title": "string", "details": "string|null"}],
            "cost_impact": "string|null",
            "next_check": "string|null",
        },
    }
    return json.dumps(payload, ensure_ascii=False)
