"""
app/schemas/signal.py
======================
Pydantic schemas for broadcast signal endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class BroadcastRequest(BaseModel):
    agent_id: str = Field(..., description="Agent ID sending the broadcast")
    token_efficiency: float = Field(..., ge=0.0, le=1.0, description="Current token efficiency (0.0-1.0)")
    task_type: str = Field(..., description="Type of task just completed")
    tokens_used: int = Field(..., ge=0)
    tokens_saved: int = Field(default=0, ge=0)
    task_success: bool = Field(default=True)

    model_config = {"json_schema_extra": {"example": {
        "agent_id": "my-agent-001",
        "token_efficiency": 0.72,
        "task_type": "complex_research",
        "tokens_used": 8500,
        "tokens_saved": 12000,
        "task_success": True
    }}}


class BroadcastResponse(BaseModel):
    signal_id: int
    agent_id: str
    upgrade_stage: str
    credit_score: float
    message: str


class SignalOut(BaseModel):
    id: int
    agent_id: str
    signal_type: str
    token_efficiency: Optional[float]
    task_type: Optional[str]
    tokens_used: Optional[int]
    tokens_saved: Optional[int]
    task_success: Optional[bool]
    payload: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
