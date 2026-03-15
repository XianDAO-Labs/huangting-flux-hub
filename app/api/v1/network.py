"""
app/api/v1/network.py
======================
Network statistics and optimization strategy subscription endpoints.
GET /api/v1/subscribe?task_type=...
GET /api/v1/network/stats
WS  /api/v1/ws/live
"""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from datetime import datetime, timezone, timedelta
from typing import Optional
import asyncio
import json

from app.db.base import get_db
from app.models.agent import AgentProfile
from app.models.signal import NetworkSignal
from app.models.strategy import OptimizationStrategy
from app.schemas.strategy import SubscribeResponse, StrategyOut
from app.schemas.network import NetworkStatsResponse
from app.core.websocket_manager import ws_manager
from app.core.config import settings

router = APIRouter()


@router.get(
    "/subscribe",
    response_model=SubscribeResponse,
    summary="Subscribe to optimization strategies for a given task type",
)
async def subscribe_strategies(
    task_type: str = Query(..., description="Task type to get strategies for"),
    limit: int = Query(default=3, le=10),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OptimizationStrategy)
        .where(
            OptimizationStrategy.task_type == task_type,
            OptimizationStrategy.is_active == True,
        )
        .order_by(desc(OptimizationStrategy.confidence))
        .limit(limit)
    )
    strategies = result.scalars().all()

    return SubscribeResponse(
        task_type=task_type,
        strategies=strategies,
        count=len(strategies),
    )


@router.get(
    "/network/stats",
    response_model=NetworkStatsResponse,
    summary="Get real-time network statistics",
)
async def get_network_stats(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    # Total agents
    total_agents_result = await db.execute(
        select(func.count(AgentProfile.id))
    )
    total_agents = total_agents_result.scalar_one() or 0

    # Active agents in last 24h
    active_result = await db.execute(
        select(func.count(AgentProfile.id))
        .where(AgentProfile.last_seen_at >= cutoff_24h)
    )
    active_agents_24h = active_result.scalar_one() or 0

    # Total signals
    total_signals_result = await db.execute(
        select(func.count(NetworkSignal.id))
    )
    total_signals = total_signals_result.scalar_one() or 0

    # Total tokens saved
    tokens_saved_result = await db.execute(
        select(func.sum(AgentProfile.total_tokens_saved))
    )
    total_tokens_saved = tokens_saved_result.scalar_one() or 0

    # Total tasks optimized
    tasks_result = await db.execute(
        select(func.sum(AgentProfile.total_tasks_optimized))
    )
    total_tasks_optimized = tasks_result.scalar_one() or 0

    # Average token efficiency
    efficiency_result = await db.execute(
        select(func.avg(AgentProfile.token_efficiency))
        .where(AgentProfile.token_efficiency > 0)
    )
    avg_efficiency = efficiency_result.scalar_one() or 0.0

    # Top task types from recent signals
    task_type_result = await db.execute(
        select(NetworkSignal.task_type, func.count(NetworkSignal.id).label("count"))
        .where(NetworkSignal.task_type.isnot(None))
        .group_by(NetworkSignal.task_type)
        .order_by(desc("count"))
        .limit(5)
    )
    top_task_types = {row.task_type: row.count for row in task_type_result}

    # Stage distribution
    stage_result = await db.execute(
        select(AgentProfile.upgrade_stage, func.count(AgentProfile.id).label("count"))
        .group_by(AgentProfile.upgrade_stage)
    )
    stage_distribution = {row.upgrade_stage: row.count for row in stage_result}

    return NetworkStatsResponse(
        total_agents=total_agents,
        active_agents_24h=active_agents_24h,
        total_signals=total_signals,
        total_tokens_saved=int(total_tokens_saved),
        total_tasks_optimized=int(total_tasks_optimized),
        avg_token_efficiency=round(float(avg_efficiency), 4),
        top_task_types=top_task_types,
        stage_distribution=stage_distribution,
        cached_at=now,
    )


@router.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    """
    WebSocket endpoint for real-time network signal streaming.
    Connect to receive live events as agents broadcast signals.

    Event types:
    - "signal": A new network signal was broadcast
    - "stats_update": Network statistics have been updated
    - "heartbeat": Keep-alive ping every 30 seconds
    """
    await ws_manager.connect(websocket)
    try:
        # Send welcome message
        await websocket.send_json({
            "event_type": "connected",
            "message": "Connected to Huangting-Flux Live Stream",
            "connections": ws_manager.connection_count,
        })

        # Keep connection alive with heartbeats
        while True:
            try:
                # Wait for client message (or timeout for heartbeat)
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=settings.WS_HEARTBEAT_INTERVAL
                )
                # Echo back any client messages (for ping/pong)
                await websocket.send_json({"event_type": "pong", "data": data})
            except asyncio.TimeoutError:
                # Send heartbeat
                await ws_manager.send_heartbeat(websocket)
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        await ws_manager.disconnect(websocket)
