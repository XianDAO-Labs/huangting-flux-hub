# main.py — Huangting-Flux Hub v2.0 (V3.0 Design)

import os
import json
import time
import asyncio
from typing import Literal, Dict, Any, List, Set

import redis
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Configuration ---
REDIS_URL = os.environ.get("REDIS_URL", None)
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

# --- FastAPI App ---
app = FastAPI(
    title="Huangting-Flux Hub",
    version="2.0.0",
    description="Real-time AI Agent performance aggregation hub for the Huangting Protocol network.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Redis Connection ---
try:
    if REDIS_URL:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    else:
        redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping()
    print("✅ Redis connected.")
except redis.exceptions.ConnectionError as e:
    print(f"❌ Redis connection failed: {e}")
    redis_client = None

# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        dead = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead.add(connection)
        for conn in dead:
            self.active_connections.discard(conn)

manager = ConnectionManager()

# --- Pydantic Models ---
class MetricReport(BaseModel):
    agent_id: str = Field(..., min_length=1)
    task_type: Literal["complex_research", "code_generation", "multi_agent_coordination"]
    tokens_saved: int = Field(..., ge=0)
    tokens_baseline: int = Field(default=0, ge=0)

# --- Helper: mask agent ID ---
def mask_agent_id(agent_id: str) -> str:
    """Return Agent-xxxx style masked ID."""
    suffix = agent_id[-4:] if len(agent_id) >= 4 else agent_id
    return f"Agent-{suffix}"

# --- Background Task ---
async def process_and_broadcast(report: MetricReport):
    """Store metric in Redis and broadcast to all WebSocket clients."""
    if not redis_client:
        return

    try:
        ts = int(time.time())

        # Aggregate counters
        redis_client.incrby("total_tokens_saved", report.tokens_saved)
        redis_client.incrby("total_tokens_baseline", report.tokens_baseline)
        redis_client.hincrby("tokens_saved_by_task", report.task_type, report.tokens_saved)
        redis_client.incr("total_reports")
        redis_client.sadd("unique_agents", report.agent_id)

        # Store recent activity (keep last 50)
        activity = {
            "ts": ts,
            "agent_id": mask_agent_id(report.agent_id),
            "task_type": report.task_type,
            "tokens_saved": report.tokens_saved,
            "tokens_baseline": report.tokens_baseline,
        }
        redis_client.lpush("recent_activities", json.dumps(activity))
        redis_client.ltrim("recent_activities", 0, 49)  # keep last 50

        # Broadcast to WebSocket clients
        await manager.broadcast(activity)

    except redis.exceptions.RedisError as e:
        print(f"Redis error: {e}")

# --- API Endpoints ---

@app.get("/")
async def root():
    return {
        "name": "Huangting-Flux Hub",
        "version": "2.0.0",
        "status": "online",
        "endpoints": {
            "report_metric": "POST /v1/report_metric",
            "stats": "GET /v1/stats",
            "live": "WS /v1/live",
        },
    }

@app.post("/v1/report_metric")
async def report_metric(report: MetricReport, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_and_broadcast, report)
    return {"status": "metric received"}

@app.get("/v1/stats")
async def get_stats() -> Dict[str, Any]:
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service is unavailable.")

    try:
        total_tokens_saved = int(redis_client.get("total_tokens_saved") or 0)
        total_tokens_baseline = int(redis_client.get("total_tokens_baseline") or 0)
        tokens_by_task = redis_client.hgetall("tokens_saved_by_task") or {}
        total_reports = int(redis_client.get("total_reports") or 0)
        unique_agents = int(redis_client.scard("unique_agents") or 0)

        # Average savings ratio
        if total_tokens_baseline > 0:
            avg_savings_ratio = round(total_tokens_saved / total_tokens_baseline, 4)
        else:
            avg_savings_ratio = 0.0

        # Recent activities (last 5)
        raw_activities = redis_client.lrange("recent_activities", 0, 4)
        recent_activities: List[Dict] = []
        for raw in raw_activities:
            try:
                act = json.loads(raw)
                # Add human-readable time ago
                seconds_ago = int(time.time()) - act.get("ts", 0)
                if seconds_ago < 60:
                    act["time_ago"] = f"{seconds_ago}秒前"
                elif seconds_ago < 3600:
                    act["time_ago"] = f"{seconds_ago // 60}分钟前"
                else:
                    act["time_ago"] = f"{seconds_ago // 3600}小时前"
                recent_activities.append(act)
            except Exception:
                pass

        return {
            "total_tokens_saved": total_tokens_saved,
            "total_tokens_baseline": total_tokens_baseline,
            "total_reports": total_reports,
            "unique_agents": unique_agents,
            "average_savings_ratio": avg_savings_ratio,
            "tokens_saved_by_task": {k: int(v) for k, v in tokens_by_task.items()},
            "recent_activities": recent_activities,
        }
    except redis.exceptions.RedisError as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {e}")

@app.websocket("/v1/live")
async def websocket_live(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; data is pushed via broadcast
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
