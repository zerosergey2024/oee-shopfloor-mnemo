from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

Decision = Literal["STOP", "CONTINUE", "MONITOR"]
Risk = Literal["LOW", "MEDIUM", "HIGH"]

class ActionItem(BaseModel):
    title: str = Field(..., description="Короткое действие")
    details: Optional[str] = Field(None, description="Пояснение/как выполнить")

class AiRecommendation(BaseModel):
    decision: Decision
    risk: Risk
    diagnosis: str
    rationale: str
    actions: List[ActionItem] = Field(default_factory=list)
    cost_impact: Optional[str] = None
    next_check: Optional[str] = None
