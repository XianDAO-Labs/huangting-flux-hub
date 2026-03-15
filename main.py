# main.py (Lightweight Hybrid Architecture)

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import redis
import json
from typing import Literal, Dict

# --- Configuration ---
REDIS_HOST = "localhost"
REDIS_PORT = 6379

# --- Pydantic Models ---
class MetricReport(BaseModel):
    agent_id: str = Field(..., min_length=1)
    task_type: Literal["complex_research", "code_generation", "multi_agent_coordination"]
    tokens_saved: int = Field(..., ge=0)

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Huangting-Flux Hub (Lightweight)",
    version="1.0.0",
    description="A minimalist hub for collecting asynchronous performance metrics from Huangting-Flux agents."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for simplicity
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# --- Redis Connection ---
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping() # Check connection
    print("Successfully connected to Redis.")
except redis.exceptions.ConnectionError as e:
    print(f"Could not connect to Redis: {e}")
    redis_client = None

# --- Helper Functions ---

def process_metric(report: MetricReport):
    """Background task to process and store the metric in Redis."""
    if not redis_client:
        return

    try:
        # Increment total tokens saved
        redis_client.incrby("total_tokens_saved", report.tokens_saved)

        # Increment tokens saved per task type
        redis_client.hincrby("tokens_saved_by_task", report.task_type, report.tokens_saved)

        # Increment total reports
        redis_client.incr("total_reports")

        # Add agent to a set of unique agents
        redis_client.sadd("unique_agents", report.agent_id)

    except redis.exceptions.RedisError as e:
        # Log error, but don't let it crash the app
        print(f"Redis error while processing metric: {e}")

# --- API Endpoints ---

@app.post("/v1/report_metric")
async def report_metric(report: MetricReport, background_tasks: BackgroundTasks):
    """
    Receives a performance metric report from an agent and processes it in the background.
    """
    background_tasks.add_task(process_metric, report)
    return {"status": "metric received"}

@app.get("/v1/stats")
async def get_stats() -> Dict[str, Any]:
    """
    Retrieves and returns the current global network statistics from Redis.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service is unavailable.")

    try:
        total_tokens_saved = redis_client.get("total_tokens_saved") or 0
        tokens_by_task = redis_client.hgetall("tokens_saved_by_task") or {}
        total_reports = redis_client.get("total_reports") or 0
        unique_agents = redis_client.scard("unique_agents") or 0

        return {
            "total_tokens_saved": int(total_tokens_saved),
            "total_reports": int(total_reports),
            "unique_agents": int(unique_agents),
            "tokens_saved_by_task": {k: int(v) for k, v in tokens_by_task.items()},
        }
    except redis.exceptions.RedisError as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats from Redis: {e}")

@app.get("/")
async def root():
    return {
        "name": "Huangting-Flux Hub (Lightweight)",
        "version": "1.0.0",
        "status": "online",
        "endpoints": {
            "report_metric": "POST /v1/report_metric",
            "stats": "GET /v1/stats"
        }
    }
