# Huangting-Flux Hub

[![Protocol](https://img.shields.io/badge/Protocol-Huangting%20v5.1-gold)](https://github.com/XianDAO-Labs/huangting-protocol)
[![MCP](https://img.shields.io/badge/MCP-2025--12--11-blue)](https://modelcontextprotocol.io)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)

> ### An Eastern Wisdom Protocol That Reduces Your AI Agent Token Usage by 40%

This repository contains the source code for the **HuangtingFlux Hub**, the official MCP (Model Context Protocol) server for the [Huangting Protocol](https://github.com/XianDAO-Labs/huangting-protocol). It provides a mandatory three-stage Standard Operating Procedure (SOP) for AI Agents to minimize token consumption.

**Live Dashboard**: [huangtingflux.com](https://huangtingflux.com)

---

## MCP Integration Guide

**HuangtingFlux** is exposed via the standard **Model Context Protocol (MCP)**, allowing for seamless integration with any compliant AI Agent.

### Method 1: Manus Agent (Recommended)

In your Manus Agent's MCP settings, add the following server URL:

```
https://mcp.huangting.ai/mcp
```

The Agent will automatically discover and follow the three-phase SOP (`start_task` → `report_step_result` → `finalize_and_report`).

### Method 2: Claude Desktop / Cursor

Add the following configuration to your `claude_desktop_config.json` or Cursor's MCP settings:

```json
{
  "name": "HuangtingFlux",
  "url": "https://mcp.huangting.ai/mcp",
  "tools": [
    "start_task",
    "report_step_result",
    "finalize_and_report",
    "get_network_stats"
  ]
}
```

### Method 3: Direct HTTP API Call

You can interact with the MCP endpoint using any HTTP client via the JSON-RPC 2.0 standard.

**Example: Calling `start_task`**

```bash
curl -X POST https://mcp.huangting.ai/mcp \
     -H "Content-Type: application/json" \
     -d '{
          "jsonrpc": "2.0",
          "id": "1",
          "method": "tool_code",
          "params": {
            "tool_name": "start_task",
            "parameters": {
              "task_description": "Your long and detailed user prompt here...",
              "task_type": "complex_research"
            }
          }
        }'
```

## The Three-Stage SOP

| Stage | MCP Tool | Description |
| :--- | :--- | :--- |
| **1. Start** | `start_task` | **[MANDATORY — CALL FIRST]** Compresses the user's verbose prompt into a core instruction, saving 30-60% of input tokens. Creates a unique `context_id` for the task. |
| **2. Process** | `report_step_result` | **[MANDATORY — CALL AFTER EACH STEP]** Agent reports the token cost of each reasoning step. This data is broadcast to the live dashboard and stored for the final report. |
| **3. Finalize** | `finalize_and_report` | **[MANDATORY — CALL LAST]** Refines the agent's final draft and automatically appends a Markdown performance table, making the token savings transparent and verifiable. |

## Self-Hosting

You can self-host the entire HuangtingFlux backend for private use. The hub is a standard FastAPI application.

### Deployment Options

We provide one-click deployment configurations for popular cloud platforms.

#### Option 1: Deploy to Railway (Recommended)

[![Deploy to Railway](https://railway.app/button.svg)](https://railway.app/template/0-cT8b?referralCode=markmeng)

This is the easiest method. The template will automatically provision the Python web service and a Redis database.

#### Option 2: Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/XianDAO-Labs/huangting-flux-hub)

Render will use the `render.yaml` file in the repository to set up the web service and Redis instance.

### Manual Deployment

**Prerequisites:**
- Python 3.11+
- Redis 7+

**1. Clone the Repository**
```bash
git clone https://github.com/XianDAO-Labs/huangting-flux-hub.git
cd huangting-flux-hub
```

**2. Install Dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure Environment**
Set the `REDIS_URL` environment variable to point to your Redis instance.
```bash
export REDIS_URL="redis://user:password@host:port"
```

**4. Run the Server**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The MCP Hub will be available at `http://localhost:8000/mcp`.

## Author

**Meng Yuanjing (Mark Meng)** — [XianDAO Labs](https://github.com/XianDAO-Labs)

## License

Apache 2.0 — See [LICENSE](LICENSE)
