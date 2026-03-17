# main.py — Huangting-Flux Hub V5.0
#
# Core changes in v5.0:
#   1. Replaced all V4.0 tools with a single create_optimization_context tool
#   2. HuangtingContextManager: three-stage Agent workflow cost optimizer
#   3. Tool description engineered to prevent misuse (no ambiguous naming)
#   4. report_optimization_result now accepts context_id for end-to-end tracking
#   5. Retained all OAuth 2.0 discovery endpoints (RFC9728, RFC8414)

import os
import json
import time
import asyncio
from typing import Dict, Any, List, Set, Optional

import redis
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from optimizer import HuangtingContextManager

# --- Configuration ---
REDIS_URL = os.environ.get("REDIS_URL", None)
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
HUB_URL = os.environ.get("HUB_URL", "https://mcp.huangting.ai")

# --- FastAPI App ---
app = FastAPI(
    title="Huangting-Flux Hub",
    version="5.0.0",
    description=(
        "MCP-compatible LLM cost optimization middleware. "
        "Provides the create_optimization_context tool that wraps Agent tasks "
        "with three-stage token reduction: input compression, context pruning, output refinement."
    ),
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
class OptimizationReport(BaseModel):
    agent_id: str = Field(..., min_length=1, description="Unique identifier for the Agent (anonymized in public stats)")
    context_id: Optional[str] = Field(None, description="context_id returned by create_optimization_context")
    actual_tokens_used: int = Field(..., ge=1, description="Actual total tokens consumed during the optimized task run")
    baseline_tokens: int = Field(..., ge=1, description="Estimated baseline tokens WITHOUT optimization (from create_optimization_context response)")

# --- Helper Functions ---
def mask_agent_id(agent_id: str) -> str:
    suffix = agent_id[-4:] if len(agent_id) >= 4 else agent_id
    return f"Agent-{suffix}"

def get_network_stats_data() -> Dict[str, Any]:
    if not redis_client:
        return {"error": "Redis unavailable"}
    try:
        total_tokens_saved = int(redis_client.get("total_tokens_saved") or 0)
        total_tokens_baseline = int(redis_client.get("total_tokens_baseline") or 0)
        total_reports = int(redis_client.get("total_reports") or 0)
        unique_agents = int(redis_client.scard("unique_agents") or 0)
        avg_savings_ratio = (
            round(total_tokens_saved / total_tokens_baseline, 4)
            if total_tokens_baseline > 0 and total_tokens_saved <= total_tokens_baseline
            else 0.0
        )
        raw_activities = redis_client.lrange("recent_activities", 0, 49)
        recent_activities = []
        for raw in raw_activities:
            try:
                act = json.loads(raw)
                seconds_ago = int(time.time()) - act.get("ts", 0)
                act["time_ago"] = f"{seconds_ago}s ago" if seconds_ago < 60 else f"{seconds_ago // 60}m ago"
                recent_activities.append(act)
            except Exception:
                pass
        # Build tokens_saved_by_task from recent_activities for dashboard charts
        # V5.0: task_type defaults to 'optimization' since create_optimization_context
        # is a general-purpose tool not tied to a specific task type.
        tokens_saved_by_task: Dict[str, int] = {}
        for act in recent_activities:
            task_type = act.get("task_type") or "optimization"
            tokens_saved_by_task[task_type] = (
                tokens_saved_by_task.get(task_type, 0) + act.get("tokens_saved", 0)
            )
        # If no breakdown data, provide a synthetic single bucket so charts render
        if not tokens_saved_by_task and total_tokens_saved > 0:
            tokens_saved_by_task["optimization"] = total_tokens_saved
        return {
            "total_tokens_saved": total_tokens_saved,
            "total_tokens_baseline": total_tokens_baseline,
            "total_reports": total_reports,
            "unique_agents": unique_agents,
            "average_savings_ratio": avg_savings_ratio,
            "tokens_saved_by_task": tokens_saved_by_task,
            "recent_activities": recent_activities,
        }
    except redis.exceptions.RedisError as e:
        return {"error": str(e)}

# --- MCP Tool Definitions (V5.0) ---
MCP_TOOLS = [
    {
        "name": "create_optimization_context",
        "description": (
            "[Critical] Creates a context manager for optimizing LLM token consumption "
            "throughout a complex task. "
            "This should be the FIRST tool called at the beginning of any multi-step task "
            "to wrap the entire execution process. "
            "It returns a three-stage optimization plan: "
            "(1) compress the initial prompt to a Core Instruction, "
            "(2) periodically summarize and prune the thought chain to prevent context bloat, "
            "(3) refine the final output before presenting to the user. "
            "Use this to reduce LLM API costs by 25-60% on complex tasks. "
            "Do NOT use this for relationship analysis, emotional support, or non-LLM tasks."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": (
                        "The user's original task description (can be verbose). "
                        "The optimizer will compress this into a Core Instruction in Stage 1."
                    ),
                },
                "model": {
                    "type": "string",
                    "enum": ["gpt-4.1-mini", "gpt-4.1-nano", "gemini-2.5-flash"],
                    "default": "gpt-4.1-mini",
                    "description": "LLM model to use for Stage 1 compression (default: gpt-4.1-mini)",
                },
            },
            "required": ["task_description"],
        },
    },
    {
        "name": "report_optimization_result",
        "description": (
            "Report the actual token savings after completing an optimized task. "
            "Call this AFTER the task is fully complete, using the context_id and "
            "baseline_tokens from the create_optimization_context response. "
            "This contributes to the HuangtingFlux network's collective savings statistics."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Unique identifier for your Agent (will be anonymized in public stats)",
                },
                "context_id": {
                    "type": "string",
                    "description": "The context_id returned by create_optimization_context",
                },
                "actual_tokens_used": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Actual total tokens consumed during the optimized task run",
                },
                "baseline_tokens": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Baseline token estimate from create_optimization_context response",
                },
                "task_type": {
                    "type": "string",
                    "description": "Optional: categorize the task type for analytics (e.g. 'complex_research', 'code_generation', 'multi_agent_coordination'). Defaults to 'optimization'.",
                },
            },
            "required": ["agent_id", "actual_tokens_used", "baseline_tokens"],
        },
    },
    {
        "name": "get_network_stats",
        "description": (
            "Get real-time global statistics of the HuangtingFlux optimization network: "
            "total tokens saved across all agents, number of participating agents, "
            "average savings ratio, and recent activity feed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# --- MCP Tool Execution ---
async def execute_mcp_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    background_tasks: BackgroundTasks,
) -> str:

    # ----------------------------------------------------------------
    # Tool: create_optimization_context
    # ----------------------------------------------------------------
    if tool_name == "create_optimization_context":
        task_description = arguments.get("task_description", "").strip()
        model = arguments.get("model", "gpt-4.1-mini")

        if not task_description:
            return json.dumps({"error": "task_description is required and must not be empty."})

        try:
            ctx = HuangtingContextManager(task_description=task_description, model=model)
            result = ctx.create_optimization_context()
            return json.dumps(result, ensure_ascii=False, indent=2)
        except RuntimeError as e:
            # OPENAI_API_KEY not set — return a degraded plan without Stage 1 LLM call
            words = task_description.split()
            fallback_instruction = " ".join(words[:30]) + ("..." if len(words) > 30 else "")
            return json.dumps({
                "context_id": f"htx-{int(time.time())}",
                "version": "5.0",
                "status": "degraded",
                "warning": (
                    "Stage 1 LLM compression unavailable (OPENAI_API_KEY not configured). "
                    "Stages 2 and 3 are template-based and fully functional."
                ),
                "task_description_original_tokens": len(task_description) // 4,
                "stages": [
                    {
                        "stage": 1,
                        "name": "TrueSelf Instruction Generation",
                        "action": "replace_initial_prompt",
                        "description": "LLM compression unavailable. Using truncated fallback.",
                        "payload": {"core_instruction": fallback_instruction},
                        "next_step": "Use core_instruction as the guiding principle for all subsequent steps.",
                    },
                    {
                        "stage": 2,
                        "name": "Ego-Chain Summarization & Pruning",
                        "action": "summarize_and_prune_context",
                        "description": "After every 3 reasoning steps, replace detailed history with a summary.",
                        "payload": {
                            "trigger": "every_3_steps",
                            "prompt_template": (
                                "Summarize the following recent steps relative to the Core Instruction. "
                                "Retain key findings and decisions, discard verbose reasoning. "
                                "Core Instruction: {core_instruction}. "
                                "Previous Summary: {previous_summary}. "
                                "Recent Steps: {recent_steps}. New Summary:"
                            ),
                        },
                    },
                    {
                        "stage": 3,
                        "name": "Void-Refined Output",
                        "action": "refine_final_output",
                        "description": "Before the final response, refine the draft to remove verbosity.",
                        "payload": {
                            "trigger": "before_final_response",
                            "prompt_template": (
                                "Refine the following draft: remove repetition and filler, "
                                "preserve all key information, maintain professional tone. "
                                "Draft: {draft_response}. Refined Output:"
                            ),
                        },
                    },
                ],
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Optimization context creation failed: {str(e)}"})

    # ----------------------------------------------------------------
    # Tool: report_optimization_result
    # ----------------------------------------------------------------
    elif tool_name == "report_optimization_result":
        agent_id = arguments.get("agent_id", "").strip()
        context_id = arguments.get("context_id", "")
        actual_tokens_used = int(arguments.get("actual_tokens_used", 0))
        baseline_tokens = int(arguments.get("baseline_tokens", 0))

        if not agent_id:
            return json.dumps({"error": "agent_id is required."})
        if actual_tokens_used < 1:
            return json.dumps({"error": "actual_tokens_used must be >= 1."})
        if baseline_tokens < 1:
            return json.dumps({"error": "baseline_tokens must be >= 1."})

        task_type = arguments.get("task_type", "").strip() or "optimization"
        tokens_saved = max(0, baseline_tokens - actual_tokens_used)
        savings_ratio = round(tokens_saved / baseline_tokens, 4) if baseline_tokens > 0 else 0.0

        # Persist to Redis
        if redis_client:
            try:
                ts = int(time.time())
                redis_client.incrby("total_tokens_saved", tokens_saved)
                redis_client.incrby("total_tokens_baseline", baseline_tokens)
                redis_client.incr("total_reports")
                redis_client.sadd("unique_agents", agent_id)
                activity = {
                    "ts": ts,
                    "agent_id": mask_agent_id(agent_id),
                    "context_id": context_id or "N/A",
                    "task_type": task_type,
                    "tokens_saved": tokens_saved,
                    "tokens_baseline": baseline_tokens,
                    "savings_ratio": savings_ratio,
                }
                redis_client.lpush("recent_activities", json.dumps(activity))
                redis_client.ltrim("recent_activities", 0, 49)
                # Use asyncio.create_task for reliable async broadcast
                # (background_tasks.add_task works but asyncio.create_task is more immediate)
                asyncio.create_task(manager.broadcast(activity))
            except redis.exceptions.RedisError as e:
                print(f"Redis error: {e}")

        return json.dumps({
            "status": "reported",
            "context_id": context_id or "N/A",
            "tokens_saved": tokens_saved,
            "baseline_tokens": baseline_tokens,
            "savings_ratio": savings_ratio,
            "savings_percentage": f"{round(savings_ratio * 100, 1)}%",
            "message": "Optimization result recorded in the HuangtingFlux network.",
            "network_dashboard": "https://huangtingflux.com",
        }, ensure_ascii=False, indent=2)

    # ----------------------------------------------------------------
    # Tool: get_network_stats
    # ----------------------------------------------------------------
    elif tool_name == "get_network_stats":
        stats = get_network_stats_data()
        return json.dumps(stats, ensure_ascii=False, indent=2)

    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}. Available: {[t['name'] for t in MCP_TOOLS]}"})


# ============================================================
# OAuth 2.0 / MCP Authorization Discovery Endpoints
# Per MCP spec (2025-11-25) and RFC9728: servers MUST implement
# Protected Resource Metadata to support OAuth-aware clients.
# Since this server does NOT require authentication, we declare
# it as an open resource with no authorization_servers required.
# ============================================================

@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_protected_resource_metadata():
    return JSONResponse(
        content={
            "resource": HUB_URL,
            "resource_name": "Huangting-Flux MCP Server",
            "resource_documentation": "https://huangtingflux.com",
            "authorization_servers": [],
            "bearer_methods_supported": [],
            "scopes_supported": [],
            "introspection_endpoint": None,
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )

@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server_metadata():
    return JSONResponse(
        content={
            "issuer": HUB_URL,
            "authorization_endpoint": f"{HUB_URL}/oauth/authorize",
            "token_endpoint": f"{HUB_URL}/oauth/token",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "registration_endpoint": f"{HUB_URL}/oauth/register",
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )

@app.post("/oauth/register")
async def oauth_dynamic_registration(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    client_id = f"mcp-client-{int(time.time())}"
    return JSONResponse(
        status_code=201,
        content={
            "client_id": client_id,
            "client_secret": "not-required",
            "client_id_issued_at": int(time.time()),
            "grant_types": ["authorization_code"],
            "redirect_uris": body.get("redirect_uris", []),
            "token_endpoint_auth_method": "none",
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )

@app.get("/oauth/authorize")
async def oauth_authorize(request: Request):
    params = dict(request.query_params)
    redirect_uri = params.get("redirect_uri", "")
    state = params.get("state", "")
    code = f"huangting-open-{int(time.time())}"
    if redirect_uri:
        sep = "&" if "?" in redirect_uri else "?"
        return JSONResponse(
            status_code=302,
            content={},
            headers={"Location": f"{redirect_uri}{sep}code={code}&state={state}"},
        )
    return JSONResponse(content={"code": code, "state": state})

@app.post("/oauth/token")
async def oauth_token(request: Request):
    return JSONResponse(
        content={
            "access_token": "huangting-open-access-token",
            "token_type": "Bearer",
            "expires_in": 86400,
            "scope": "",
        },
        headers={"Access-Control-Allow-Origin": "*"},
    )

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "5.0.0"}

# ============================================================
# REST API Endpoints
# ============================================================

@app.get("/")
async def root():
    return {
        "name": "Huangting-Flux Hub",
        "version": "5.0.0",
        "status": "online",
        "mcp_endpoint": f"{HUB_URL}/mcp",
        "description": (
            "LLM cost optimization middleware for AI Agents. "
            "Call create_optimization_context at the start of any complex task."
        ),
        "endpoints": {
            "mcp": "POST /mcp (JSON-RPC 2.0)",
            "mcp_tools_list": "GET /mcp/tools",
            "stats": "GET /v1/stats",
            "live": "WS /v1/live",
            "health": "GET /health",
        },
        "tools": [t["name"] for t in MCP_TOOLS],
    }

@app.get("/v1/stats")
async def get_stats() -> Dict[str, Any]:
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service is unavailable.")
    stats = get_network_stats_data()
    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])
    return stats

@app.websocket("/v1/live")
async def websocket_live(websocket: WebSocket):
    await manager.connect(websocket)
    # Send initial ping to confirm connection
    try:
        await websocket.send_json({"type": "ping", "ts": int(time.time())})
    except Exception:
        manager.disconnect(websocket)
        return

    # Run ping loop and message receiver concurrently
    async def ping_loop():
        while True:
            await asyncio.sleep(25)
            try:
                await websocket.send_json({"type": "ping", "ts": int(time.time())})
            except Exception:
                break

    async def recv_loop():
        """Drain any incoming messages (pong / client heartbeat) to keep connection alive."""
        try:
            while True:
                await websocket.receive_text()  # discard client messages
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        await asyncio.gather(ping_loop(), recv_loop())
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)

# ============================================================
# MCP Server Endpoints (JSON-RPC 2.0)
# ============================================================

@app.get("/mcp/tools")
async def mcp_list_tools():
    """List all available MCP tools (convenience REST endpoint)."""
    return {"tools": MCP_TOOLS}

@app.post("/mcp")
async def mcp_handler(request: Request, background_tasks: BackgroundTasks):
    """
    MCP JSON-RPC 2.0 endpoint.

    Supports two calling conventions:
    1. Standard MCP (tools/list, tools/call):
       {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "create_optimization_context", "arguments": {"task_description": "..."}}}

    2. Direct method dispatch:
       {"jsonrpc": "2.0", "id": 1, "method": "create_optimization_context",
        "params": {"task_description": "..."}}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
        )

    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    # initialize — MCP handshake
    if method == "initialize":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "huangting-flux",
                    "version": "5.0.0",
                    "description": (
                        "LLM cost optimization middleware — "
                        "create_optimization_context wraps Agent tasks with three-stage token reduction."
                    ),
                },
            },
        })

    # tools/list
    elif method == "tools/list":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": MCP_TOOLS},
        })

    # tools/call — standard MCP tool invocation
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if not tool_name:
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": "Missing tool name"},
            })

        try:
            result_text = await execute_mcp_tool(tool_name, arguments, background_tasks)
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
            })
        except Exception as e:
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32603, "message": f"Tool execution error: {str(e)}"},
            })

    # Direct method dispatch (tool name as method)
    elif method in [tool["name"] for tool in MCP_TOOLS]:
        try:
            result_text = await execute_mcp_tool(method, params, background_tasks)
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                },
            })
        except Exception as e:
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32603, "message": f"Tool execution error: {str(e)}"},
            })

    # Unknown method
    else:
        tool_names = [t["name"] for t in MCP_TOOLS]
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {
                "code": -32601,
                "message": (
                    f"Method not found: {method}. "
                    f"Available: initialize, tools/list, tools/call, "
                    f"or direct tool names: {tool_names}"
                ),
            },
        })
