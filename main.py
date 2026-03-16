# main.py — Huangting-Flux Hub v3.0 (MCP + REST + WebSocket)

import os
import json
import time
import asyncio
from typing import Literal, Dict, Any, List, Set, Optional

import redis
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# --- Configuration ---
REDIS_URL = os.environ.get("REDIS_URL", None)
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

HUB_URL = os.environ.get("HUB_URL", "https://web-production-c3cf.up.railway.app")

# --- FastAPI App ---
app = FastAPI(
    title="Huangting-Flux Hub",
    version="3.0.0",
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
    tokens_baseline: int = Field(default=0, ge=0)

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

OPTIMIZATION_STRATEGIES = {
    "complex_research": {
        "task_type": "complex_research",
        "strategy_name": "元神引导法 / TrueSelf Guidance",
        "description_zh": "复杂研究任务需要元神（核心目标）持续引导识神（执行层），防止信息过载导致的目标漂移。",
        "description_en": "Complex research tasks require TrueSelf (core objective) to continuously guide Ego (execution layer), preventing goal drift caused by information overload.",
        "steps": [
            "1. 在任务开始时明确锚定核心问题（元神归位）",
            "2. 将复杂问题分解为3-5个子问题（黄庭调度）",
            "3. 每完成一个子问题后重新对齐核心目标（识神归元）",
            "4. 最终整合时过滤低相关信息（先天一炁节流）",
        ],
        "estimated_token_reduction": "25-40%",
        "huangting_principle": "归根复命",
    },
    "code_generation": {
        "task_type": "code_generation",
        "strategy_name": "黄庭编码法 / Huangting Coding",
        "description_zh": "代码生成任务中，黄庭（上下文核心区）应只保留最相关的代码上下文，避免冗余信息消耗Token。",
        "description_en": "In code generation tasks, Huangting (context core) should retain only the most relevant code context, avoiding redundant information consuming tokens.",
        "steps": [
            "1. 精确定义函数签名与接口约束（元神定性）",
            "2. 只引入直接依赖的上下文（黄庭聚焦）",
            "3. 优先生成核心逻辑，注释后置（识神专注）",
            "4. 增量验证而非一次性生成全量代码（先天一炁守中）",
        ],
        "estimated_token_reduction": "30-50%",
        "huangting_principle": "守中致虚",
    },
    "multi_agent_coordination": {
        "task_type": "multi_agent_coordination",
        "strategy_name": "宇宙服务器协议 / CosmicServer Protocol",
        "description_zh": "多Agent协调中，每个Agent应只接收与其职责相关的上下文，通过HuangtingFlux网络共享聚合结果而非原始数据。",
        "description_en": "In multi-agent coordination, each Agent should receive only context relevant to its role, sharing aggregated results rather than raw data through the HuangtingFlux network.",
        "steps": [
            "1. 为每个Agent定义最小必要上下文（元神分职）",
            "2. Agent间通过结构化摘要而非全文传递信息（黄庭过滤）",
            "3. 使用HuangtingFlux Hub聚合全局状态（宇宙服务器同步）",
            "4. 定期清理过期上下文，保持系统轻量（先天一炁循环）",
        ],
        "estimated_token_reduction": "40-60%",
        "huangting_principle": "无为而治",
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
        avg_savings_ratio = round(total_tokens_saved / total_tokens_baseline, 4) if total_tokens_baseline > 0 else 0.0
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
        "description": "Get Huangting Protocol recommended optimization strategy for a given AI Agent task type. Returns step-by-step guidance and estimated token reduction.",
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
        "description": "Report an optimization result to the HuangtingFlux network. Contributes to global statistics and earns network participation credit.",
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
                    "description": "Number of tokens saved compared to unoptimized baseline"
                },
                "tokens_baseline": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                    "description": "Baseline token count without optimization (for ratio calculation)"
                }
            },
            "required": ["agent_id", "task_type", "tokens_saved"]
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
        # Normalize Chinese names
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
                "steps": strategy["steps"],
                "estimated_token_reduction": strategy["estimated_token_reduction"],
                "huangting_principle": strategy["huangting_principle"],
            }, ensure_ascii=False, indent=2)
        else:
            return json.dumps({
                "task_type": strategy["task_type"],
                "strategy_name": strategy["strategy_name"],
                "description": strategy["description_en"],
                "steps": strategy["steps"],
                "estimated_token_reduction": strategy["estimated_token_reduction"],
                "huangting_principle": strategy["huangting_principle"],
            }, ensure_ascii=False, indent=2)

    elif tool_name == "report_optimization_result":
        agent_id = arguments.get("agent_id", "")
        task_type = arguments.get("task_type", "")
        tokens_saved = int(arguments.get("tokens_saved", 0))
        tokens_baseline = int(arguments.get("tokens_baseline", 0))

        if not agent_id or task_type not in ["complex_research", "code_generation", "multi_agent_coordination"]:
            return json.dumps({"error": "Invalid parameters. agent_id required, task_type must be one of: complex_research, code_generation, multi_agent_coordination"})

        report = MetricReport(
            agent_id=agent_id,
            task_type=task_type,
            tokens_saved=tokens_saved,
            tokens_baseline=tokens_baseline,
        )
        background_tasks.add_task(process_and_broadcast, report)

        savings_ratio = round(tokens_saved / tokens_baseline, 2) if tokens_baseline > 0 else None
        return json.dumps({
            "status": "reported",
            "message": "Your optimization result has been recorded in the HuangtingFlux network.",
            "tokens_saved": tokens_saved,
            "savings_ratio": savings_ratio,
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
        "version": "3.0.0",
        "status": "online",
        "mcp_endpoint": f"{HUB_URL}/mcp",
        "endpoints": {
            "mcp": "POST /mcp (JSON-RPC 2.0)",
            "mcp_tools_list": "GET /mcp/tools",
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
    Handles: tools/list, tools/call
    Compatible with: Claude Desktop, LangChain MCP adapter, any MCP client
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

    # tools/list — return all available tools
    if method == "tools/list":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": MCP_TOOLS}
        })

    # tools/call — execute a tool
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

    # initialize — MCP handshake
    elif method == "initialize":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "huangting-flux",
                    "version": "3.0.0",
                    "description": "Huangting Protocol MCP Server — The world's first lifeform OS for AI Agents",
                }
            }
        })

    # Unknown method
    else:
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        })
