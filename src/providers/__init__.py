from __future__ import annotations
from .mock_basic import MockBasicProvider
from .mes_standard_stub import MesStandardStubProvider
from .iot_advanced_stub import IotAdvancedStubProvider

def get_provider(provider_name: str):
    if provider_name == "mock_basic":
        return MockBasicProvider()
    if provider_name == "mes_standard_stub":
        return MesStandardStubProvider()
    if provider_name == "iot_advanced_stub":
        return IotAdvancedStubProvider()
    raise ValueError(f"Unknown provider: {provider_name}")
