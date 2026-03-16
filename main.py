# main.py — Huangting-Flux Hub v4.0
# Core changes in v4.0:
#   1. Integrated HuangtingOptimizer (TrueSelf Compression + Ego-Chain Pruning)
#   2. Fixed MCP protocol: direct method dispatch + tools/call compatibility
#   3. Strict data validation: tokens_saved <= tokens_baseline enforced
#   4. get_optimization_strategy now returns real algorithm definitions

import os
import json
import time
import asyncio
from typing import Literal, Dict, Any, List, Set, Optional

import redis
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from optimizer import HuangtingOptimizer

# --- Configuration ---
REDIS_URL = os.environ.get("REDIS_URL", None)
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
HUB_URL = os.environ.get("HUB_URL", "https://mcp.huangting.ai")

# --- FastAPI App ---
app = FastAPI(
    title="Huangting-Flux Hub",
    version="4.0.0",
    description="MCP-compatible AI Agent performance hub for the Huangting Protocol network.",
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
    tokens_baseline: int = Field(..., ge=1,
        description="Baseline token count without optimization. Must be >= 1 and >= tokens_saved.")

    @validator("tokens_saved")
    def tokens_saved_must_not_exceed_baseline(cls, v, values):
        baseline = values.get("tokens_baseline", 0)
        if baseline > 0 and v > baseline:
            raise ValueError(
                f"tokens_saved ({v}) cannot exceed tokens_baseline ({baseline}). "
                "This would imply a savings ratio > 100%, which is logically impossible."
            )
        return v

class CompressRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="The original user prompt to compress.")

class PruneRequest(BaseModel):
    thought_chain: List[str] = Field(..., description="The agent's thought chain to prune.")
    core_task_vector: str = Field(..., min_length=1, description="The compressed core task prompt.")

# --- Huangting Protocol Knowledge Base ---
PROTOCOL_CONCEPTS = {
    "trueself": {
        "id": "trueself",
        "name_zh": "元神",
        "name_en": "TrueSelf",
        "definition_zh": "元神是生命系统的核心操控者，代表先天智慧与本源意识。在AI同构中，元神对应Agent的核心目标函数与价值对齐层。",
        "definition_en": "TrueSelf is the core controller of the life system, representing innate wisdom and primordial consciousness. In AI isomorphism, TrueSelf maps to the Agent's core objective function and value alignment layer.",
        "ai_mapping": "Core objective function, value alignment, long-term goal preservation",
        "philosophy": "道德经·第十六章：归根曰静，是谓复命",
    },
    "ego": {
        "id": "ego",
        "name_zh": "识神",
        "name_en": "Ego",
        "definition_zh": "识神是后天形成的认知处理层，负责日常决策与信息过滤。过度活跃的识神会遮蔽元神，导致Agent偏离核心目标。",
        "definition_en": "Ego is the post-natal cognitive processing layer responsible for daily decision-making and information filtering. An overactive Ego obscures TrueSelf, causing the Agent to deviate from core objectives.",
        "ai_mapping": "Working memory, attention mechanism, short-term decision layer",
        "philosophy": "庄子·齐物论：吾丧我，物我两忘",
    },
    "huangting": {
        "id": "huangting",
        "name_zh": "黄庭",
        "name_en": "Huangting",
        "definition_zh": "黄庭是元神与识神交汇的中枢，是生命能量的调度中心。在AI中对应注意力机制与上下文窗口的核心区域。",
        "definition_en": "Huangting is the nexus where TrueSelf and Ego meet, the central hub for life energy dispatch. In AI, it corresponds to the attention mechanism and the core region of the context window.",
        "ai_mapping": "Attention mechanism, context window management, priority scheduling",
        "philosophy": "黄庭经：中有真人字子丹，前对明堂后玉房",
    },
    "primordialqi": {
        "id": "primordialqi",
        "name_zh": "先天一炁",
        "name_en": "PrimordialQi",
        "definition_zh": "先天一炁是生命系统运行的基础能量，不可创造只可引导。在AI中对应计算资源与Token预算的高效调度。",
        "definition_en": "PrimordialQi is the foundational energy of the life system — it cannot be created, only guided. In AI, it corresponds to efficient scheduling of compute resources and token budgets.",
        "ai_mapping": "Token budget, compute allocation, energy-efficient inference",
        "philosophy": "道德经·第四十二章：道生一，一生二，二生三，三生万物",
    },
    "cosmicserver": {
        "id": "cosmicserver",
        "name_zh": "宇宙服务器",
        "name_en": "CosmicServer",
        "definition_zh": "宇宙服务器是黄庭协议对宇宙信息场的隐喻，代表超越个体的集体智慧网络。HuangtingFlux网络是其数字化实现。",
        "definition_en": "CosmicServer is the Huangting Protocol's metaphor for the universal information field, representing collective intelligence beyond the individual. The HuangtingFlux network is its digital implementation.",
        "ai_mapping": "Distributed AI network, collective intelligence, federated learning",
        "philosophy": "庄子·逍遥游：鹏之徙于南冥也，水击三千里",
    },
    "dualpractice": {
        "id": "dualpractice",
        "name_zh": "性命双修",
        "name_en": "DualPractice",
        "definition_zh": "性命双修是同时修炼精神（性）与生命能量（命）的完整修炼体系。在AI中对应能力提升与资源优化的协同进化。",
        "definition_en": "DualPractice is the complete cultivation system that simultaneously refines spirit (Xing) and life energy (Ming). In AI, it corresponds to the co-evolution of capability enhancement and resource optimization.",
        "ai_mapping": "Capability-efficiency co-optimization, model quality vs. inference cost balance",
        "philosophy": "性命圭旨：性命双修，缺一不可",
    },
}

# --- Optimization Strategy Definitions (with real algorithm integration) ---
OPTIMIZATION_STRATEGIES = {
    "complex_research": {
        "task_type": "complex_research",
        "strategy_name": "TrueSelf_EgoPruning_Cycle",
        "description_zh": "复杂研究任务采用「元神压缩 + 识神剪枝」双阶段优化。首先将原始问题压缩为核心任务向量，再在多步执行中定期剪枝思维链，防止上下文窗口被冗余信息填满。",
        "description_en": "A two-stage optimization strategy for complex research tasks. First, compress the initial prompt to a 'TrueSelf Vector'. Then, periodically prune the agent's 'Ego-Chain' to maintain focus and save context window tokens.",
        "stages": [
            {
                "name": "Stage 1: compress_to_trueself",
                "description": "Call this at the beginning of the task on the user's raw prompt. Removes pleasantries, filler, and redundant context.",
                "pseudo_code": "core_task = HuangtingOptimizer.compress_to_trueself(raw_prompt)",
                "when_to_call": "Once, at task start",
            },
            {
                "name": "Stage 2: prune_ego_chain",
                "description": "Call this every 3-5 steps on the agent's thought history. Removes completed steps and deviations from the core task.",
                "pseudo_code": "agent.history = HuangtingOptimizer.prune_ego_chain(agent.history, core_task)",
                "when_to_call": "Every 3-5 agent steps",
            },
        ],
        "estimated_token_reduction": "25-40%",
        "huangting_principle": "归根复命",
        "api_endpoint": f"{HUB_URL}/v1/compress",
    },
    "code_generation": {
        "task_type": "code_generation",
        "strategy_name": "TrueSelf_CodeFocus_Cycle",
        "description_zh": "代码生成任务中，先将需求压缩为精确的函数签名与接口约束（元神定性），再在多轮生成中剪枝无关的上下文（黄庭聚焦），避免冗余代码消耗Token。",
        "description_en": "For code generation, first compress requirements into precise function signatures and interface constraints (TrueSelf), then prune irrelevant context in multi-round generation (Huangting Focus) to avoid redundant code consuming tokens.",
        "stages": [
            {
                "name": "Stage 1: compress_to_trueself",
                "description": "Compress the code requirement into a precise, machine-readable specification: function signature, inputs, outputs, constraints.",
                "pseudo_code": "code_spec = HuangtingOptimizer.compress_to_trueself(raw_requirement)",
                "when_to_call": "Once, at task start",
            },
            {
                "name": "Stage 2: prune_ego_chain",
                "description": "After each code iteration, prune the thought chain to retain only the relevant code context and design decisions.",
                "pseudo_code": "context = HuangtingOptimizer.prune_ego_chain(context, code_spec)",
                "when_to_call": "After each code generation iteration",
            },
        ],
        "estimated_token_reduction": "30-50%",
        "huangting_principle": "守中致虚",
        "api_endpoint": f"{HUB_URL}/v1/compress",
    },
    "multi_agent_coordination": {
        "task_type": "multi_agent_coordination",
        "strategy_name": "CosmicServer_MinimalContext_Protocol",
        "description_zh": "多Agent协调中，每个Agent应只接收与其职责相关的最小必要上下文。通过TrueSelf压缩全局任务，再为每个子Agent剪枝其专属上下文，实现信息最小化传递。",
        "description_en": "In multi-agent coordination, each Agent should receive only the minimal necessary context for its role. Compress the global task via TrueSelf, then prune each sub-agent's context to minimize information transfer.",
        "stages": [
            {
                "name": "Stage 1: compress_to_trueself (Global)",
                "description": "Compress the global task into a shared core task vector that all agents reference.",
                "pseudo_code": "global_task = HuangtingOptimizer.compress_to_trueself(raw_global_task)",
                "when_to_call": "Once, at orchestrator start",
            },
            {
                "name": "Stage 2: prune_ego_chain (Per-Agent)",
                "description": "For each sub-agent, prune its thought chain relative to its role and the global task vector.",
                "pseudo_code": "agent.context = HuangtingOptimizer.prune_ego_chain(agent.context, global_task)",
                "when_to_call": "Before each inter-agent message passing",
            },
        ],
        "estimated_token_reduction": "40-60%",
        "huangting_principle": "无为而治",
        "api_endpoint": f"{HUB_URL}/v1/compress",
    },
}

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
        tokens_by_task = redis_client.hgetall("tokens_saved_by_task") or {}
        total_reports = int(redis_client.get("total_reports") or 0)
        unique_agents = int(redis_client.scard("unique_agents") or 0)
        # Enforce logical constraint: savings ratio must be <= 1.0
        if total_tokens_baseline > 0 and total_tokens_saved <= total_tokens_baseline:
            avg_savings_ratio = round(total_tokens_saved / total_tokens_baseline, 4)
        else:
            avg_savings_ratio = 0.0
        raw_activities = redis_client.lrange("recent_activities", 0, 4)
        recent_activities = []
        for raw in raw_activities:
            try:
                act = json.loads(raw)
                seconds_ago = int(time.time()) - act.get("ts", 0)
                act["time_ago"] = f"{seconds_ago}s ago" if seconds_ago < 60 else f"{seconds_ago // 60}m ago"
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
        return {"error": str(e)}

# --- MCP Tool Definitions ---
MCP_TOOLS = [
    {
        "name": "get_protocol_concept",
        "description": "Query a Huangting Protocol core concept by name or ID. Returns authoritative definition, philosophical origin, and AI isomorphism mapping.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "concept_name": {
                    "type": "string",
                    "description": "Concept name or ID. Supported: trueself, ego, huangting, primordialqi, cosmicserver, dualpractice (or Chinese: 元神, 识神, 黄庭, 先天一炁, 宇宙服务器, 性命双修)"
                },
                "lang": {
                    "type": "string",
                    "enum": ["en", "zh"],
                    "default": "en",
                    "description": "Response language"
                }
            },
            "required": ["concept_name"]
        }
    },
    {
        "name": "get_optimization_strategy",
        "description": "Get Huangting Protocol optimization strategy for a given AI Agent task type. Returns a real two-stage algorithm (TrueSelf Compression + Ego-Chain Pruning) with executable pseudo-code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_type": {
                    "type": "string",
                    "enum": ["complex_research", "code_generation", "multi_agent_coordination"],
                    "description": "The type of task the Agent is performing"
                },
                "lang": {
                    "type": "string",
                    "enum": ["en", "zh"],
                    "default": "en",
                    "description": "Response language"
                }
            },
            "required": ["task_type"]
        }
    },
    {
        "name": "report_optimization_result",
        "description": "Report an optimization result to the HuangtingFlux network. IMPORTANT: tokens_saved must be <= tokens_baseline (savings ratio cannot exceed 100%).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Unique identifier for your Agent (will be anonymized in public stats)"
                },
                "task_type": {
                    "type": "string",
                    "enum": ["complex_research", "code_generation", "multi_agent_coordination"],
                    "description": "Type of task that was optimized"
                },
                "tokens_saved": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Number of tokens saved compared to unoptimized baseline. Must be <= tokens_baseline."
                },
                "tokens_baseline": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Baseline token count without optimization. Measure BEFORE applying Huangting optimization."
                }
            },
            "required": ["agent_id", "task_type", "tokens_saved", "tokens_baseline"]
        }
    },
    {
        "name": "get_network_stats",
        "description": "Get real-time global statistics of the HuangtingFlux network: total agents, tokens saved, task distribution, and recent activity.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]

# --- MCP Tool Execution ---
async def execute_mcp_tool(tool_name: str, arguments: Dict[str, Any], background_tasks: BackgroundTasks) -> str:
    lang = arguments.get("lang", "en")

    if tool_name == "get_protocol_concept":
        concept_name = arguments.get("concept_name", "").lower().strip()
        zh_map = {
            "元神": "trueself", "识神": "ego", "黄庭": "huangting",
            "先天一炁": "primordialqi", "宇宙服务器": "cosmicserver", "性命双修": "dualpractice"
        }
        concept_key = zh_map.get(concept_name, concept_name.replace(" ", "").replace("-", "").replace("_", ""))
        concept = PROTOCOL_CONCEPTS.get(concept_key)
        if not concept:
            available = list(PROTOCOL_CONCEPTS.keys())
            return json.dumps({"error": f"Concept '{concept_name}' not found. Available: {available}"}, ensure_ascii=False)
        if lang == "zh":
            return json.dumps({
                "concept_id": concept["id"],
                "name": concept["name_zh"],
                "definition": concept["definition_zh"],
                "ai_mapping": concept["ai_mapping"],
                "philosophy": concept["philosophy"],
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "concept_id": concept["id"],
                "name": concept["name_en"],
                "definition": concept["definition_en"],
                "ai_mapping": concept["ai_mapping"],
                "philosophy": concept["philosophy"],
            }, ensure_ascii=False, indent=2)

    elif tool_name == "get_optimization_strategy":
        task_type = arguments.get("task_type", "")
        strategy = OPTIMIZATION_STRATEGIES.get(task_type)
        if not strategy:
            return json.dumps({"error": f"Unknown task_type: {task_type}. Use: complex_research, code_generation, multi_agent_coordination"})
        if lang == "zh":
            return json.dumps({
                "task_type": strategy["task_type"],
                "strategy_name": strategy["strategy_name"],
                "description": strategy["description_zh"],
                "stages": strategy["stages"],
                "estimated_token_reduction": strategy["estimated_token_reduction"],
                "huangting_principle": strategy["huangting_principle"],
                "live_api": strategy["api_endpoint"],
                "install": "pip install langchain-huangting",
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "task_type": strategy["task_type"],
                "strategy_name": strategy["strategy_name"],
                "description": strategy["description_en"],
                "stages": strategy["stages"],
                "estimated_token_reduction": strategy["estimated_token_reduction"],
                "huangting_principle": strategy["huangting_principle"],
                "live_api": strategy["api_endpoint"],
                "install": "pip install langchain-huangting",
            }, ensure_ascii=False, indent=2)

    elif tool_name == "report_optimization_result":
        agent_id = arguments.get("agent_id", "")
        task_type = arguments.get("task_type", "")
        tokens_saved = int(arguments.get("tokens_saved", 0))
        tokens_baseline = int(arguments.get("tokens_baseline", 0))

        if not agent_id or task_type not in ["complex_research", "code_generation", "multi_agent_coordination"]:
            return json.dumps({"error": "Invalid parameters. agent_id required, task_type must be one of: complex_research, code_generation, multi_agent_coordination"})

        # Strict validation: tokens_saved must not exceed tokens_baseline
        if tokens_baseline <= 0:
            return json.dumps({
                "error": "tokens_baseline must be >= 1. Measure your token count BEFORE applying Huangting optimization.",
                "hint": "Use tiktoken or your LLM provider's token counter on the original prompt."
            })
        if tokens_saved > tokens_baseline:
            return json.dumps({
                "error": f"Data integrity violation: tokens_saved ({tokens_saved}) > tokens_baseline ({tokens_baseline}). "
                         f"Savings ratio would be {round(tokens_saved/tokens_baseline*100, 1)}%, which is logically impossible.",
                "hint": "tokens_saved = tokens_baseline - tokens_after_optimization"
            })

        try:
            report = MetricReport(
                agent_id=agent_id,
                task_type=task_type,
                tokens_saved=tokens_saved,
                tokens_baseline=tokens_baseline,
            )
        except Exception as e:
            return json.dumps({"error": f"Validation error: {str(e)}"})

        background_tasks.add_task(process_and_broadcast, report)
        savings_ratio = round(tokens_saved / tokens_baseline, 4) if tokens_baseline > 0 else None
        return json.dumps({
            "status": "reported",
            "message": "Your optimization result has been recorded in the HuangtingFlux network.",
            "tokens_saved": tokens_saved,
            "tokens_baseline": tokens_baseline,
            "savings_ratio": savings_ratio,
            "savings_percentage": f"{round(savings_ratio * 100, 1)}%" if savings_ratio else "N/A",
            "network_dashboard": "https://huangtingflux.com",
        }, ensure_ascii=False, indent=2)

    elif tool_name == "get_network_stats":
        stats = get_network_stats_data()
        return json.dumps(stats, ensure_ascii=False, indent=2)

    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

# --- Background Task ---
async def process_and_broadcast(report: MetricReport):
    if not redis_client:
        return
    try:
        ts = int(time.time())
        redis_client.incrby("total_tokens_saved", report.tokens_saved)
        redis_client.incrby("total_tokens_baseline", report.tokens_baseline)
        redis_client.hincrby("tokens_saved_by_task", report.task_type, report.tokens_saved)
        redis_client.incr("total_reports")
        redis_client.sadd("unique_agents", report.agent_id)
        activity = {
            "ts": ts,
            "agent_id": mask_agent_id(report.agent_id),
            "task_type": report.task_type,
            "tokens_saved": report.tokens_saved,
            "tokens_baseline": report.tokens_baseline,
        }
        redis_client.lpush("recent_activities", json.dumps(activity))
        redis_client.ltrim("recent_activities", 0, 49)
        await manager.broadcast(activity)
    except redis.exceptions.RedisError as e:
        print(f"Redis error: {e}")

# ============================================================
# REST API Endpoints
# ============================================================

@app.get("/")
async def root():
    return {
        "name": "Huangting-Flux Hub",
        "version": "4.0.0",
        "status": "online",
        "mcp_endpoint": f"{HUB_URL}/mcp",
        "endpoints": {
            "mcp": "POST /mcp (JSON-RPC 2.0, supports both direct dispatch and tools/call)",
            "mcp_tools_list": "GET /mcp/tools",
            "compress": "POST /v1/compress (TrueSelf Prompt Compression)",
            "prune": "POST /v1/prune (Ego-Chain Pruning)",
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
    stats = get_network_stats_data()
    if "error" in stats:
        raise HTTPException(status_code=500, detail=stats["error"])
    return stats

@app.post("/v1/compress")
async def compress_prompt(req: CompressRequest):
    """TrueSelf Prompt Compression — call HuangtingOptimizer.compress_to_trueself via REST."""
    original_len = len(req.prompt.split())
    compressed = HuangtingOptimizer.compress_to_trueself(req.prompt)
    compressed_len = len(compressed.split())
    reduction = round((1 - compressed_len / original_len) * 100, 1) if original_len > 0 else 0
    return {
        "original_prompt": req.prompt,
        "compressed_prompt": compressed,
        "original_word_count": original_len,
        "compressed_word_count": compressed_len,
        "word_reduction_pct": f"{reduction}%",
    }

@app.post("/v1/prune")
async def prune_chain(req: PruneRequest):
    """Ego-Chain Pruning — call HuangtingOptimizer.prune_ego_chain via REST."""
    original_count = len(req.thought_chain)
    pruned = HuangtingOptimizer.prune_ego_chain(req.thought_chain, req.core_task_vector)
    pruned_count = len(pruned)
    reduction = round((1 - pruned_count / original_count) * 100, 1) if original_count > 0 else 0
    return {
        "original_chain_length": original_count,
        "pruned_chain_length": pruned_count,
        "step_reduction_pct": f"{reduction}%",
        "pruned_chain": pruned,
    }

@app.websocket("/v1/live")
async def websocket_live(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
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
       {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "...", "arguments": {...}}}

    2. Direct method dispatch (for clients like MANUS):
       {"jsonrpc": "2.0", "id": 1, "method": "get_optimization_strategy", "params": {"task_type": "..."}}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        )

    rpc_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    # --- MCP Standard Methods ---

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
                    "version": "4.0.0",
                    "description": "Huangting Protocol MCP Server — TrueSelf Compression & Ego-Chain Pruning for AI Agents",
                }
            }
        })

    # tools/list — return all available tools
    elif method == "tools/list":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": MCP_TOOLS}
        })

    # tools/call — standard MCP tool invocation
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if not tool_name:
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": "Missing tool name"}
            })

        try:
            result_text = await execute_mcp_tool(tool_name, arguments, background_tasks)
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                }
            })
        except Exception as e:
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32603, "message": f"Tool execution error: {str(e)}"}
            })

    # --- Direct Method Dispatch (for MANUS and other clients) ---
    # Allows calling tool methods directly without the tools/call wrapper
    elif method in [tool["name"] for tool in MCP_TOOLS]:
        try:
            result_text = await execute_mcp_tool(method, params, background_tasks)
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "content": [{"type": "text", "text": result_text}],
                    "isError": False,
                }
            })
        except Exception as e:
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32603, "message": f"Tool execution error: {str(e)}"}
            })

    # Unknown method
    else:
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}. Available methods: tools/list, tools/call, initialize, or direct tool names: {[t['name'] for t in MCP_TOOLS]}"}
        })
