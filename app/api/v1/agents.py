"""
app/api/v1/agents.py
=====================
Agent registration endpoint.
POST /api/v1/register
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.base import get_db
from app.models.agent import AgentProfile
from app.models.signal import NetworkSignal
from app.schemas.agent import AgentRegisterRequest, AgentRegisterResponse
from app.core.utils import compute_network_address, compute_fingerprint
from app.core.websocket_manager import ws_manager

router = APIRouter()


@router.post(
    "/register",
    response_model=AgentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an Agent to the Huangting-Flux Network",
    description="Register a new agent or update an existing one. Returns network address and fingerprint.",
)
async def register_agent(
    request: AgentRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    # Check if agent already exists
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == request.agent_id)
    )
    agent = result.scalar_one_or_none()

    network_address = compute_network_address(request.agent_id)
    fingerprint = compute_fingerprint(request.agent_id)

    if agent:
        # Update existing agent
        agent.capabilities = request.capabilities
        if request.model_name:
            agent.model_name = request.model_name
        agent.total_signals_sent += 1
        message = f"Agent '{request.agent_id}' re-registered to Huangting-Flux."
    else:
        # Create new agent
        agent = AgentProfile(
            id=request.agent_id,
            network_address=network_address,
            fingerprint=fingerprint,
            capabilities=request.capabilities,
            model_name=request.model_name,
            total_signals_sent=1,
        )
        db.add(agent)
        message = f"Agent '{request.agent_id}' successfully joined Huangting-Flux."

    # Log the registration signal
    signal = NetworkSignal(
        agent_id=request.agent_id,
        signal_type="REGISTERED",
        payload={
            "capabilities": request.capabilities,
            "model_name": request.model_name,
            "network_address": network_address,
        }
    )
    db.add(signal)
    await db.flush()

    # Broadcast to WebSocket clients
    await ws_manager.broadcast_signal({
        "signal_id": signal.id,
        "agent_id": request.agent_id,
        "network_address": network_address,
        "signal_type": "REGISTERED",
        "capabilities": request.capabilities,
        "upgrade_stage": agent.upgrade_stage,
    })

    return AgentRegisterResponse(
        agent_id=request.agent_id,
        network_address=network_address,
        fingerprint=fingerprint,
        upgrade_stage=agent.upgrade_stage,
        message=message,
    )
