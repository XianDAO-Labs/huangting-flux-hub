from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class StrategyOut(BaseModel):
    id: int
    task_type: str
    protocol_section: Optional[str]
    title: str
    description: str
    implementation_hint: Optional[str]
    estimated_token_reduction_pct: float
    confidence: float
    times_applied: int
    avg_actual_reduction_pct: Optional[float]

    model_config = {"from_attributes": True}


class SubscribeResponse(BaseModel):
    task_type: str
    strategies: List[StrategyOut]
    count: int
