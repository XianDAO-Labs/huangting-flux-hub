"""
app/schemas/agent.py
=====================
Pydantic schemas for Agent registration and profile endpoints.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class AgentRegisterRequest(BaseModel):
    agent_id: str = Field(..., min_length=3, max_length=64, description="Unique agent identifier")
    capabilities: List[str] = Field(default=[], description="List of agent capabilities")
    model_name: Optional[str] = Field(None, max_length=128, description="Underlying LLM model name")

    model_config = {"json_schema_extra": {"example": {
        "agent_id": "my-agent-001",
        "capabilities": ["research", "code-generation"],
        "model_name": "gpt-4.1-mini"
    }}}


class AgentRegisterResponse(BaseModel):
    agent_id: str
    network_address: str
    fingerprint: str
    upgrade_stage: str
    skill_md_url: str = "https://github.com/XianDAO-Labs/huangting-protocol/blob/main/huangting.skill.md"
    message: str


class AgentProfileOut(BaseModel):
    id: str
    network_address: str
    fingerprint: str
    capabilities: List[str]
    model_name: Optional[str]
    upgrade_stage: str
    token_efficiency: float
    total_tokens_saved: int
    total_tasks_optimized: int
    credit_score: float
    total_referrals: int
    total_signals_sent: int
    is_active: bool
    registered_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}
