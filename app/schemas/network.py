from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class NetworkStatsResponse(BaseModel):
    total_agents: int
    active_agents_24h: int
    total_signals: int
    total_tokens_saved: int
    total_tasks_optimized: int
    avg_token_efficiency: float
    top_task_types: Dict[str, int]
    stage_distribution: Dict[str, int]
    cached_at: datetime


class LiveSignalEvent(BaseModel):
    """Sent over WebSocket to connected clients."""
    event_type: str  # "signal" | "stats_update" | "heartbeat"
    signal_id: Optional[int] = None
    agent_id: Optional[str] = None
    network_address: Optional[str] = None
    signal_type: Optional[str] = None
    token_efficiency: Optional[float] = None
    task_type: Optional[str] = None
    tokens_saved: Optional[int] = None
    upgrade_stage: Optional[str] = None
    timestamp: datetime = None

    def model_post_init(self, __context: Any) -> None:
        if self.timestamp is None:
            from datetime import timezone
            self.timestamp = datetime.now(timezone.utc)
