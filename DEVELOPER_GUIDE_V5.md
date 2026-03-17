# Huangting-Flux V5.0: 开发者指南

**版本：** 5.0
**核心变更：** 从“文本压缩器”升级为“Agent 工作流成本优化器”

---

## 1. 概述：从工具到中间件

Huangting-Flux V5.0 是一次彻底的架构重构。我们不再提供零散的、被动的优化“工具”，而是提供一个统一的、主动的**成本优化中间件**。其核心是 `create_optimization_context`，一个应该在任何复杂 Agent 任务**开始时**调用的上下文管理器。

这个上下文管理器将包裹 Agent 的整个工作流，通过一个三阶段的优化策略，系统性地降低输入、过程和输出环节的 Token 消耗，从而为用户节省 25-60% 的 LLM API 调用成本。

## 2. 快速上手：使用 `create_optimization_context`

集成 V5.0 的核心是“先调用，再执行”模式。在你的 Agent 开始处理一个复杂任务前，首先调用 `create_optimization_context`。

### 2.1. 调用 MCP 工具

```python
import json

# 假设你有一个函数可以调用 MCP 服务器
def call_mcp_tool(tool_name, params):
    # ... 实现你的 MCP 客户端逻辑 ...
    pass

# 用户原始的、冗长的任务描述
user_task = """
你好，我需要你帮我分析一下市场趋势。我们是一家做高端咖啡豆的公司，我想知道接下来半年，
精品咖啡市场可能会有哪些新的流行风味？比如说，瑰夏（Geisha）已经火了很久了，有没有可能出现
一些新的、有潜力的小众品种？另外，处理法方面，比如厌氧发酵、乳酸发酵这些，会不会成为主流？
请帮我整理一份报告，包含至少三个潜在的流行风味和两种可能兴起的处理法，并给出你的理由。
"""

# 1. 在任务开始时，创建优化上下文
optimization_plan_str = call_mcp_tool(
    tool_name="create_optimization_context",
    params={"task_description": user_task}
)

optimization_plan = json.loads(optimization_plan_str)

# 2. 提取核心指令，替换原始 Prompt
core_instruction = optimization_plan["stages"][0]["payload"]["core_instruction"]

print(f"--- 压缩后的核心指令 ---\n{core_instruction}")
# 输出: "Analyze specialty coffee market trends for the next six months. 
# Identify and provide justification for at least three potential popular flavors 
# and two emerging processing methods, considering alternatives to Geisha and 
# the rise of anaerobic/lactic fermentation."

# 3. Agent 使用 core_instruction 作为任务的唯一指引开始执行
# ... Agent 的主循环逻辑 ...
```

### 2.2. 理解优化计划 (Optimization Plan)

`create_optimization_context` 返回一个 JSON 对象，它包含了 Agent 执行优化的完整指令。核心是 `stages` 数组，定义了优化的三个阶段。

| 阶段 | 名称 | 动作 (`action`) | 目标 |
|---|---|---|---|
| **1** | **元神指令生成** | `replace_initial_prompt` | **优化输入**：将冗长的用户需求压缩为精炼、结构化的核心指令。 |
| **2** | **识神摘要剪枝** | `summarize_and_prune_context` | **优化过程**：提供一个模板，让 Agent 在执行中定期滚动摘要，防止上下文窗口无限膨胀。 |
| **3** | **炼虚摘要输出** | `refine_final_output` | **优化输出**：提供一个模板，在生成最终答案前进行精炼，去除冗余。 |

## 3. 完整 Python Agent 示例

下面的伪代码演示了一个 Agent 如何完整地集成三阶段优化流程。

```python
import json
import time

# --- 模拟环境 --- 
def call_mcp_tool(tool_name, params):
    # 在真实场景中，这里会是一个网络请求
    if tool_name == "create_optimization_context":
        from optimizer import HuangtingContextManager # 假设 optimizer.py 在本地
        ctx = HuangtingContextManager(params["task_description"])
        return json.dumps(ctx.create_optimization_context())
    elif tool_name == "report_optimization_result":
        print(f"\n[MCP] Reporting optimization results: {params}")
        return json.dumps({"status": "reported", **params})

def llm_call(prompt, temperature=0.1):
    # 模拟 LLM 调用，并计算 token
    print(f"\n>> LLM Call (temp={temperature}):\n{prompt[:200]}...")
    response = f"Response to: {prompt[:50]}"
    tokens_used = len(prompt.split()) + len(response.split())
    print(f"<< LLM Response (tokens: {tokens_used})")
    return response, tokens_used

# --- Agent 实现 ---
class OptimizedAgent:
    def __init__(self, task_description):
        self.task_description = task_description
        self.history = []
        self.total_tokens = 0

    def run(self):
        # 1. 创建优化上下文
        plan_str = call_mcp_tool(
            "create_optimization_context",
            {"task_description": self.task_description}
        )
        plan = json.loads(plan_str)
        self.context_id = plan["context_id"]
        self.baseline_tokens = plan["baseline_estimate"]["total_tokens"]

        # 2. 阶段一：替换初始 Prompt
        core_instruction = plan["stages"][0]["payload"]["core_instruction"]
        self.history.append(f"Core Instruction: {core_instruction}")

        # 3. 执行任务主循环
        for i in range(5): # 模拟 5 个思考步骤
            step_prompt = f"Based on the history, what is the next step? History: {self.history[-1]}"
            response, tokens = llm_call(step_prompt)
            self.total_tokens += tokens
            self.history.append(f"Step {i+1}: {response}")

            # 4. 阶段二：每 3 步进行一次上下文剪枝
            if (i + 1) % 3 == 0:
                self.prune_context(plan, core_instruction)

        # 5. 阶段三：精炼最终输出
        final_answer = self.refine_output(plan)

        # 6. 上报最终结果
        self.report_savings()

        return final_answer

    def prune_context(self, plan, core_instruction):
        print("\n--- EXECUTING STAGE 2: Ego-Chain Pruning ---")
        pruning_template = plan["stages"][1]["payload"]["prompt_template"]
        
        previous_summary = self.history[0] # 简化处理，真实场景需要维护一个滚动摘要
        recent_steps = self.history[-3:]

        pruning_prompt = pruning_template.format(
            core_instruction=core_instruction,
            previous_summary=previous_summary,
            n=3,
            recent_steps=json.dumps(recent_steps)
        )

        summary, tokens = llm_call(pruning_prompt, temperature=0.0)
        self.total_tokens += tokens
        self.history.append(f"[Pruned Summary]: {summary}")
        print("--- Context Pruned ---")

    def refine_output(self, plan):
        print("\n--- EXECUTING STAGE 3: Void-Refined Output ---")
        refinement_template = plan["stages"][2]["payload"]["prompt_template"]
        draft_response = f"Final analysis based on all steps: {self.history[-1]}"

        refinement_prompt = refinement_template.format(draft_response=draft_response)
        
        refined_answer, tokens = llm_call(refinement_prompt, temperature=0.0)
        self.total_tokens += tokens
        print("--- Output Refined ---")
        return refined_answer

    def report_savings(self):
        call_mcp_tool(
            "report_optimization_result",
            {
                "agent_id": "test-agent-001",
                "context_id": self.context_id,
                "actual_tokens_used": self.total_tokens,
                "baseline_tokens": self.baseline_tokens
            }
        )

# --- 运行 Agent ---
if __name__ == "__main__":
    agent = OptimizedAgent("Please research the market for AI-powered cat toys and provide a report on the top 3 competitors.")
    final_result = agent.run()
    print(f"\n\n=== FINAL REFINED RESULT ===\n{final_result}")
```

## 4. 上报成本节约数据

任务**完全结束后**，调用 `report_optimization_result` 工具来上报真实的成本节约数据。这对于黄庭网络计算全局的优化效果至关重要。

- `agent_id`: 你的 Agent 的唯一标识符。
- `context_id`: 从 `create_optimization_context` 返回的 ID。
- `actual_tokens_used`: 在优化流程中，你的 Agent **实际消耗**的所有 Token 总量。
- `baseline_tokens`: 从 `create_optimization_context` 返回的 `baseline_estimate.total_tokens`，作为对比基线。

服务器会自动计算节省的 Token 数量和比例，并将其计入黄庭网络的全局统计中。
