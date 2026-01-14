from __future__ import annotations
from typing import List
import pandas as pd

from .base import ShopfloorProvider
from ..models import MachineOverview, StopEvent
from ..data_mock import get_mock_overview, get_mock_machine_timeseries, get_mock_stops

class MesStandardStubProvider(ShopfloorProvider):
    profile = "STANDARD"

    def get_overview(self) -> List[MachineOverview]:
        return get_mock_overview(self.profile)

    def get_oee_timeseries(self, machine_id: str) -> pd.DataFrame:
        return get_mock_machine_timeseries(machine_id, self.profile)

    def get_stops(self, machine_id: str) -> List[StopEvent]:
        return get_mock_stops(machine_id, self.profile)

