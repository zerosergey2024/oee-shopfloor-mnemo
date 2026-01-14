from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
import pandas as pd
from ..models import MachineOverview, StopEvent

class ShopfloorProvider(ABC):
    @abstractmethod
    def get_overview(self) -> List[MachineOverview]:
        ...

    @abstractmethod
    def get_oee_timeseries(self, machine_id: str) -> pd.DataFrame:
        ...

    @abstractmethod
    def get_stops(self, machine_id: str) -> List[StopEvent]:
        ...
