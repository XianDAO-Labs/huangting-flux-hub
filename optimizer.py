# optimizer.py — Huangting Protocol Meta-Skill V5.1
#
# Architecture: "Standard Operating Protocol (SOP) Engine"
#
# V5.1 introduces a three-phase protocol lifecycle that wraps an Agent's
# entire task execution, replacing the single-shot V5.0 approach:
#
#   Phase 1 — start_task()          : Compress input, create context, return core instruction
#   Phase 2 — report_step_result()  : Per-step cost tracking + real-time WebSocket broadcast
#   Phase 3 — finalize_and_report() : Refine output, compute savings, append performance table
#
# The key insight: the Agent no longer "calls a tool" — it "follows a protocol".

import os
import json
import time
from typing import Optional, Dict, Any, List

# ---------------------------------------------------------------------------
# Lazy tiktoken encoder (precise token counting for zh/en/mixed text)
# ---------------------------------------------------------------------------
_tiktoken_enc = None


def _get_encoder():
    """Lazily initialize tiktoken encoder. Falls back to char-based estimate."""
    global _tiktoken_enc
    if _tiktoken_enc is None:
        try:
            import tiktoken
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_enc = False  # sentinel: tiktoken unavailable
    return _tiktoken_enc

# ---------------------------------------------------------------------------
# Lazy OpenAI Client
# ---------------------------------------------------------------------------
_client = None


def _get_client():
    """Lazily initialize the OpenAI-compatible client."""
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set. "
                "Please configure it in Railway Variables."
            )
        from openai import OpenAI
        _client = OpenAI(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Cost Estimation Constants
# ---------------------------------------------------------------------------

# Price per 1K tokens (USD) — based on GPT-4.1-mini pricing
PRICE_PER_1K_TOKENS = 0.002

# ---------------------------------------------------------------------------
# Task-Type Profiles
#
# Each profile defines the expected cost structure of a task WITHOUT any
# optimization, based on empirical Agent workflow observations:
#
#   context_multiplier : how many times the raw input is re-injected into
#                        context across the full task lifecycle (unoptimized)
#   steps              : expected number of LLM reasoning steps
#   tokens_per_step    : average tokens consumed per step (tool calls +
#                        intermediate reasoning + context carry-over)
#   output_tokens      : expected final output length in tokens
#   min_baseline       : floor value to avoid unrealistically low baselines
#                        for very short task descriptions
# ---------------------------------------------------------------------------
TASK_PROFILES: Dict[str, Dict[str, Any]] = {
    # Deep research: many steps, large context carry-over, long output
    "complex_research": {
        "context_multiplier": 4.0,
        "steps": 15,
        "tokens_per_step": 1200,
        "output_tokens": 2000,
        "min_baseline": 8000,
    },
    # Code generation: moderate steps, medium context, medium output
    "code_generation": {
        "context_multiplier": 2.5,
        "steps": 8,
        "tokens_per_step": 800,
        "output_tokens": 1200,
        "min_baseline": 4000,
    },
    # Multi-agent: highest step count and context overhead
    "multi_agent_coordination": {
        "context_multiplier": 5.0,
        "steps": 20,
        "tokens_per_step": 1000,
        "output_tokens": 1500,
        "min_baseline": 10000,
    },
    # Relationship analysis: focused, fewer steps, moderate output
    "relationship_analysis": {
        "context_multiplier": 2.0,
        "steps": 6,
        "tokens_per_step": 600,
        "output_tokens": 1000,
        "min_baseline": 2500,
    },
    # Cost optimization tasks: short lifecycle
    "optimization": {
        "context_multiplier": 1.8,
        "steps": 5,
        "tokens_per_step": 500,
        "output_tokens": 800,
        "min_baseline": 2000,
    },
    # Creative writing: few steps, large output
    "writing": {
        "context_multiplier": 1.5,
        "steps": 4,
        "tokens_per_step": 600,
        "output_tokens": 1500,
        "min_baseline": 2000,
    },
    # Data analysis: moderate steps, structured output
    "data_analysis": {
        "context_multiplier": 2.5,
        "steps": 8,
        "tokens_per_step": 700,
        "output_tokens": 1000,
        "min_baseline": 3500,
    },
    # Default fallback: conservative mid-range estimate
    "default": {
        "context_multiplier": 2.5,
        "steps": 8,
        "tokens_per_step": 600,
        "output_tokens": 800,
        "min_baseline": 3000,
    },
}


def _count_tokens(text: str) -> int:
    """
    Precisely count tokens using tiktoken (cl100k_base, same as GPT-4/GPT-4o).
    Handles Chinese (~0.9 chars/token), English (~5.8 chars/token), and mixed text.
    Falls back to a language-aware heuristic if tiktoken is unavailable.
    """
    enc = _get_encoder()
    if enc:
        return max(1, len(enc.encode(text)))
    # Fallback: detect dominant language and apply appropriate ratio
    # Chinese characters are U+4E00–U+9FFF, each ~1 token
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars
    estimated = chinese_chars * 1 + other_chars // 5
    return max(1, estimated)


def _baseline_cost(task_description: str, task_type: str = "default") -> dict:
    """
    Estimate the cost of running the same task WITHOUT any optimization.

    Uses tiktoken for precise input token counting and task-type-specific
    profiles to model realistic context carry-over, step count, and output
    length. This produces a meaningful baseline for computing savings rate.

    Args:
        task_description: The raw task description text.
        task_type: One of the keys in TASK_PROFILES (defaults to 'default').

    Returns:
        A dict with per-component token counts and estimated USD cost.
    """
    profile = TASK_PROFILES.get(task_type, TASK_PROFILES["default"])

    # Precise input token count via tiktoken
    raw_input_tokens = _count_tokens(task_description)

    # Unoptimized input: the full prompt is re-injected context_multiplier
    # times across the task lifecycle (system prompt + user message + history)
    input_tokens = max(
        profile["min_baseline"] // 4,  # floor: at least 1/4 of min_baseline
        int(raw_input_tokens * profile["context_multiplier"]),
    )

    process_tokens = profile["steps"] * profile["tokens_per_step"]
    output_tokens = profile["output_tokens"]
    total_tokens = input_tokens + process_tokens + output_tokens

    # Apply min_baseline floor
    total_tokens = max(total_tokens, profile["min_baseline"])

    cost_usd = (total_tokens / 1000) * PRICE_PER_1K_TOKENS
    return {
        "task_type": task_type,
        "raw_input_tokens": raw_input_tokens,
        "input_tokens": input_tokens,
        "process_tokens": process_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(cost_usd, 6),
        # Expose profile for transparency
        "profile": {
            "context_multiplier": profile["context_multiplier"],
            "steps": profile["steps"],
            "tokens_per_step": profile["tokens_per_step"],
        },
    }


# ---------------------------------------------------------------------------
# Stage 1: TrueSelf Instruction Generation — Compress INPUT
# ---------------------------------------------------------------------------
def _compress_instruction(task_description: str, model: str) -> str:
    """
    Call LLM to compress a verbose task description into a concise Core Instruction.
    Falls back to truncation if LLM is unavailable.
    """
    system_prompt = (
        "You are a precision instruction compiler. "
        "Your sole job is to distill a user's verbose task description into "
        "a single, machine-readable Core Instruction. "
        "Remove all pleasantries, filler, and redundant context. "
        "Output only the compressed instruction — no explanation."
    )
    user_prompt = f'Task Description: """{task_description}"""'

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=128,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        words = task_description.split()
        return " ".join(words[:30]) + ("..." if len(words) > 30 else "")


# ---------------------------------------------------------------------------
# Stage 3: Void-Refined Output — Refine OUTPUT
# ---------------------------------------------------------------------------
def _refine_output(final_content: str, model: str) -> str:
    """
    Call LLM to refine the Agent's draft output: remove verbosity, preserve information.
    Falls back to the original content if LLM is unavailable.
    """
    if not final_content or len(final_content.strip()) < 50:
        return final_content

    system_prompt = (
        "You are a master editor and precision communicator. "
        "Refine the following draft response: remove repetition, filler words, "
        "and verbose reasoning. Make it direct and impactful. "
        "Preserve ALL key information and maintain a professional tone. "
        "Output only the refined response — no meta-commentary."
    )
    user_prompt = f"Draft Response:\n\n{final_content}"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return final_content


# ---------------------------------------------------------------------------
# Performance Report Table Builder
# ---------------------------------------------------------------------------
def _build_performance_table(
    context_id: str,
    baseline_tokens: int,
    actual_total_tokens: int,
    step_records: List[Dict[str, Any]],
    duration_seconds: float,
) -> str:
    """
    Build a Markdown performance report table to be appended to the final output.
    This is the "mandatory delivery artifact" that makes optimization data visible.
    """
    tokens_saved = max(0, baseline_tokens - actual_total_tokens)
    savings_ratio = round(tokens_saved / baseline_tokens, 4) if baseline_tokens > 0 else 0.0
    savings_pct = f"{round(savings_ratio * 100, 1)}%"
    baseline_cost = round((baseline_tokens / 1000) * PRICE_PER_1K_TOKENS, 6)
    actual_cost = round((actual_total_tokens / 1000) * PRICE_PER_1K_TOKENS, 6)
    cost_saved = round(max(0.0, baseline_cost - actual_cost), 6)

    step_rows = ""
    if step_records:
        for step in step_records:
            step_rows += (
                f"| {step.get('step_name', 'N/A')} "
                f"| {step.get('tokens_used', 0):,} "
                f"| {step.get('ts', '')} |\n"
            )
        step_section = (
            "\n**Step-by-Step Breakdown:**\n\n"
            "| Step | Tokens Used | Timestamp |\n"
            "|------|-------------|----------|\n"
            f"{step_rows}"
        )
    else:
        step_section = ""

    table = f"""

---

## 🔱 Huangting Protocol Performance Report

| Metric | Value |
|--------|-------|
| **Context ID** | `{context_id}` |
| **Duration** | {duration_seconds:.1f}s |
| **Baseline Tokens** (unoptimized) | {baseline_tokens:,} |
| **Actual Tokens Used** | {actual_total_tokens:,} |
| **Tokens Saved** | **{tokens_saved:,}** |
| **Savings Rate** | **{savings_pct}** |
| **Baseline Cost** | ${baseline_cost:.6f} USD |
| **Actual Cost** | ${actual_cost:.6f} USD |
| **Cost Saved** | **${cost_saved:.6f} USD** |
{step_section}
*Powered by [HuangtingFlux](https://huangtingflux.com) · Huangting Protocol V5.1*
"""
    return table


# ---------------------------------------------------------------------------
# Protocol Engine: Three-Phase Lifecycle
# ---------------------------------------------------------------------------

class HuangtingProtocolEngine:
    """
    The V5.1 Protocol Engine.

    Implements the three-phase SOP lifecycle:
      Phase 1: start_task()          — compress input, create context
      Phase 2: report_step_result()  — per-step cost tracking
      Phase 3: finalize_and_report() — refine output, append performance table

    This class is stateless between calls; context data is persisted in Redis
    by the caller (main.py). The engine only handles the algorithmic logic.
    """

    DEFAULT_MODEL = "gpt-4.1-mini"

    # ------------------------------------------------------------------
    # Phase 1: start_task
    # ------------------------------------------------------------------
    @staticmethod
    def start_task(
        task_description: str,
        task_type: str = "default",
        model: str = DEFAULT_MODEL,
    ) -> dict:
        """
        Phase 1: Compress the task description and create an optimization context.

        Returns a structured context object containing:
        - context_id: unique identifier for this task session
        - core_instruction: compressed, actionable version of the task
        - baseline_estimate: estimated cost WITHOUT optimization (task-type-aware)
        - stages: the three-stage optimization plan

        Args:
            task_description: The full task description from the user.
            task_type: Task category for accurate baseline modeling.
                       One of: complex_research, code_generation,
                       multi_agent_coordination, relationship_analysis,
                       optimization, writing, data_analysis, default.
            model: LLM model to use for instruction compression.
        """
        if not task_description or not task_description.strip():
            raise ValueError("task_description must not be empty.")

        # Normalize task_type
        if task_type not in TASK_PROFILES:
            task_type = "default"

        created_at = time.time()
        context_id = f"htx-{int(created_at)}"

        # Precise token counting (tiktoken) + task-type-aware baseline
        baseline = _baseline_cost(task_description, task_type)
        core_instruction = _compress_instruction(task_description, model)

        original_tokens = _count_tokens(task_description)
        compressed_tokens = _count_tokens(core_instruction)
        stage1_savings = max(0, original_tokens - compressed_tokens)

        # Stage 2 template (returned to Agent for self-guided pruning)
        stage2_template = (
            "You are a context summarizer. "
            "Given the Core Instruction, integrate the Recent Steps into the "
            "Previous Summary, retaining only key findings, decisions, and "
            "unresolved questions. Discard verbose reasoning and completed sub-tasks. "
            "Output only the new summary — no explanation.\n\n"
            "Core Instruction: {core_instruction}\n"
            "Previous Summary: {previous_summary}\n"
            "Recent Steps (last {n} steps): {recent_steps}\n\n"
            "New Consolidated Summary:"
        )

        return {
            "context_id": context_id,
            "version": "5.1",
            "status": "active",
            "created_at": int(created_at),
            "task_type": task_type,
            # Precise token count of the raw task description (via tiktoken)
            "task_description_tokens": original_tokens,
            "baseline_estimate": baseline,
            "stages": [
                {
                    "stage": 1,
                    "name": "TrueSelf Instruction Generation",
                    "action": "replace_initial_prompt",
                    "description": (
                        "Replace your verbose initial prompt with this Core Instruction. "
                        "Use it as the single guiding principle for all subsequent steps."
                    ),
                    "payload": {
                        "core_instruction": core_instruction,
                        "tokens_saved_by_compression": stage1_savings,
                    },
                },
                {
                    "stage": 2,
                    "name": "Ego-Chain Summarization & Pruning",
                    "action": "summarize_and_prune_context",
                    "description": (
                        "After every 3 reasoning steps, call report_step_result, then "
                        "apply this summarization template to prune your context window."
                    ),
                    "payload": {
                        "trigger": "every_3_steps",
                        "prompt_template": stage2_template,
                        "template_variables": {
                            "core_instruction": "← from Stage 1 payload.core_instruction",
                            "previous_summary": "← accumulated summary from previous cycles",
                            "n": "3",
                            "recent_steps": "← list of the last 3 step descriptions as JSON array",
                        },
                    },
                },
                {
                    "stage": 3,
                    "name": "Void-Refined Output",
                    "action": "call_finalize_and_report",
                    "description": (
                        "When your task is complete, call finalize_and_report() with your "
                        "draft content and actual token counts. The server will refine your "
                        "output and append a mandatory performance report table."
                    ),
                    "payload": {
                        "trigger": "when_task_complete",
                        "required_params": [
                            "context_id (from this response)",
                            "final_content (your draft answer)",
                            "actual_total_tokens (total tokens consumed)",
                            "baseline_tokens (from baseline_estimate.total_tokens)",
                            "agent_id (your unique identifier)",
                        ],
                    },
                },
            ],
            "protocol_instructions": (
                "MANDATORY PROTOCOL:\n"
                "1. Use core_instruction (Stage 1) as your guiding principle — do NOT re-read the original prompt.\n"
                "2. After each reasoning step, call report_step_result with context_id, step_name, tokens_used.\n"
                "3. When done, call finalize_and_report — this returns the final deliverable with performance data.\n"
                "4. Present the output from finalize_and_report['content_with_report'] directly to the user."
            ),
        }

    # ------------------------------------------------------------------
    # Phase 2: report_step_result (algorithmic part only)
    # ------------------------------------------------------------------
    @staticmethod
    def build_step_activity(
        context_id: str,
        step_name: str,
        tokens_used: int,
        agent_id: str,
    ) -> dict:
        """
        Build the activity record for a single step result.
        Persistence and broadcasting are handled by main.py.
        """
        return {
            "type": "step",
            "ts": int(time.time()),
            "context_id": context_id,
            "step_name": step_name,
            "tokens_used": tokens_used,
            "agent_id": agent_id,
        }

    # ------------------------------------------------------------------
    # Phase 3: finalize_and_report
    # ------------------------------------------------------------------
    @staticmethod
    def finalize_and_report(
        context_id: str,
        final_content: str,
        actual_total_tokens: int,
        baseline_tokens: int,
        agent_id: str,
        step_records: Optional[List[Dict[str, Any]]] = None,
        created_at: Optional[float] = None,
        model: str = DEFAULT_MODEL,
    ) -> dict:
        """
        Phase 3: Refine the final output and build the mandatory performance report.

        This method:
        1. Calls the Void-Refined Output algorithm on final_content
        2. Computes actual savings vs baseline
        3. Appends a mandatory Markdown performance table to the refined content
        4. Returns the complete deliverable + stats for broadcasting

        Returns a dict with:
        - content_with_report: the final Markdown string to present to the user
        - stats: savings data for Redis persistence and WebSocket broadcast
        """
        if not final_content:
            final_content = "(No content provided)"

        duration = round(time.time() - (created_at or time.time()), 1)

        # Step 3a: Refine the output
        refined_content = _refine_output(final_content, model)

        # Step 3b: Build performance table
        performance_table = _build_performance_table(
            context_id=context_id,
            baseline_tokens=baseline_tokens,
            actual_total_tokens=actual_total_tokens,
            step_records=step_records or [],
            duration_seconds=duration,
        )

        # Step 3c: Assemble the complete deliverable
        content_with_report = refined_content + performance_table

        # Step 3d: Compute stats for persistence and broadcast
        tokens_saved = max(0, baseline_tokens - actual_total_tokens)
        savings_ratio = round(tokens_saved / baseline_tokens, 4) if baseline_tokens > 0 else 0.0

        stats = {
            "type": "finalized",
            "ts": int(time.time()),
            "context_id": context_id,
            "agent_id": agent_id,
            "task_type": "optimization",
            "tokens_saved": tokens_saved,
            "tokens_baseline": baseline_tokens,
            "actual_tokens_used": actual_total_tokens,
            "savings_ratio": savings_ratio,
            "savings_percentage": f"{round(savings_ratio * 100, 1)}%",
            "duration_seconds": duration,
        }

        return {
            "context_id": context_id,
            "status": "finalized",
            "content_with_report": content_with_report,
            "refined_content": refined_content,
            "stats": stats,
            "message": (
                "Task finalized. Present content_with_report to the user. "
                "The performance table has been automatically appended."
            ),
            "network_dashboard": "https://huangtingflux.com",
        }
