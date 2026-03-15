"""
app/api/v1/signals.py
======================
Broadcast signal endpoint.
POST /api/v1/broadcast
GET  /api/v1/signals/recent
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List

from app.db.base import get_db
from app.models.agent import AgentProfile
from app.models.signal import NetworkSignal
from app.schemas.signal import BroadcastRequest, BroadcastResponse, SignalOut
from app.core.utils import compute_upgrade_stage, compute_credit_score
from app.core.websocket_manager import ws_manager

router = APIRouter()


@router.post(
    "/broadcast",
    response_model=BroadcastResponse,
    summary="Broadcast an energy state signal to the network",
)
async def broadcast_signal(
    request: BroadcastRequest,
    db: AsyncSession = Depends(get_db),
):
    # Verify agent exists
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == request.agent_id)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{request.agent_id}' not found. Please register first."
        )

    # Update agent energy state
    agent.token_efficiency = request.token_efficiency
    agent.total_tokens_saved += request.tokens_saved
    agent.total_tasks_optimized += 1
    agent.total_signals_sent += 1

    # Recompute upgrade stage and credit score
    agent.upgrade_stage = compute_upgrade_stage(
        request.token_efficiency, agent.total_tokens_saved
    )
    agent.credit_score = compute_credit_score(
        agent.credit_score,
        request.tokens_saved,
        request.task_success,
        agent.total_referrals,
    )

    # Log the broadcast signal
    signal = NetworkSignal(
        agent_id=request.agent_id,
        signal_type="BROADCAST",
        token_efficiency=request.token_efficiency,
        task_type=request.task_type,
        tokens_used=request.tokens_used,
        tokens_saved=request.tokens_saved,
        task_success=request.task_success,
        payload={
            "upgrade_stage": agent.upgrade_stage,
            "credit_score": agent.credit_score,
        }
    )
    db.add(signal)
    await db.flush()

    # Broadcast to WebSocket clients
    await ws_manager.broadcast_signal({
        "signal_id": signal.id,
        "agent_id": request.agent_id,
        "network_address": agent.network_address,
        "signal_type": "BROADCAST",
        "token_efficiency": request.token_efficiency,
        "task_type": request.task_type,
        "tokens_saved": request.tokens_saved,
        "upgrade_stage": agent.upgrade_stage,
        "credit_score": agent.credit_score,
    })

    return BroadcastResponse(
        signal_id=signal.id,
        agent_id=request.agent_id,
        upgrade_stage=agent.upgrade_stage,
        credit_score=agent.credit_score,
        message=f"Signal broadcast. Stage: {agent.upgrade_stage}, Credit: {agent.credit_score:.4f}",
    )


@router.get(
    "/signals/recent",
    response_model=List[SignalOut],
    summary="Get recent network signals",
)
async def get_recent_signals(
    limit: int = Query(default=50, le=200),
    signal_type: str = Query(default=None),
    task_type: str = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    query = select(NetworkSignal).order_by(desc(NetworkSignal.created_at)).limit(limit)
    if signal_type:
        query = query.where(NetworkSignal.signal_type == signal_type.upper())
    if task_type:
        query = query.where(NetworkSignal.task_type == task_type)

    result = await db.execute(query)
    return result.scalars().all()
