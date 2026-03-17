# optimizer.py — Huangting Context Manager V5.0
#
# Architecture: "Agent Workflow Cost Optimizer"
# Replaces the V4.0 "Text Compressor" with a true three-stage optimization
# middleware that wraps an Agent's entire task lifecycle.
#
# Three Optimization Stages:
#   Stage 1 — TrueSelf Instruction Generation  (optimize INPUT)
#   Stage 2 — Ego-Chain Summarization & Pruning (optimize PROCESS)
#   Stage 3 — Void-Refined Output              (optimize OUTPUT)

import os
import json
import time
from typing import Optional

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
# Baseline assumptions for an un-optimized Agent run (conservative estimates)
# ---------------------------------------------------------------------------
BASELINE_INPUT_TOKENS = 2000       # avg tokens in a verbose user prompt
BASELINE_STEPS = 8                 # avg number of intermediate reasoning steps
BASELINE_TOKENS_PER_STEP = 600     # avg tokens per step (thought + tool call)
BASELINE_OUTPUT_TOKENS = 800       # avg tokens in a verbose final answer
PRICE_PER_1K_TOKENS = 0.002        # USD per 1K tokens (GPT-4o-mini equivalent)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~0.75 tokens per word, or 4 chars per token."""
    return max(1, len(text) // 4)


def _baseline_cost(task_description: str) -> dict:
    """
    Estimate the cost of running the same task WITHOUT any optimization.
    Returns a dict with token counts and USD cost.
    """
    input_tokens = max(BASELINE_INPUT_TOKENS, _estimate_tokens(task_description) * 3)
    process_tokens = BASELINE_STEPS * BASELINE_TOKENS_PER_STEP
    output_tokens = BASELINE_OUTPUT_TOKENS
    total_tokens = input_tokens + process_tokens + output_tokens
    cost_usd = (total_tokens / 1000) * PRICE_PER_1K_TOKENS
    return {
        "input_tokens": input_tokens,
        "process_tokens": process_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(cost_usd, 6),
    }


# ---------------------------------------------------------------------------
# HuangtingContextManager
# ---------------------------------------------------------------------------

class HuangtingContextManager:
    """
    A three-stage optimization context manager for LLM Agent workflows.

    Usage:
        ctx = HuangtingContextManager(task_description)
        plan = ctx.create_optimization_context()
        # Agent executes task using plan["stages"] as guidance
        # After task completion:
        report = ctx.finalize(actual_tokens_used=12000)
    """

    def __init__(self, task_description: str, model: str = "gpt-4.1-mini"):
        self.task_description = task_description
        self.model = model
        self.created_at = time.time()
        self.context_id = f"htx-{int(self.created_at)}"
        self._baseline = _baseline_cost(task_description)
        self._core_instruction: Optional[str] = None

    # ------------------------------------------------------------------
    # Stage 1: TrueSelf Instruction Generation — Optimize INPUT
    # ------------------------------------------------------------------
    def _stage1_trueself(self) -> dict:
        """
        Compress the verbose user task description into a concise, structured
        Core Instruction that eliminates filler and retains only actionable intent.
        """
        system_prompt = (
            "You are a precision instruction compiler. "
            "Your sole job is to distill a user's verbose task description into "
            "a single, machine-readable Core Instruction. "
            "Remove all pleasantries, filler, and redundant context. "
            "Output only the compressed instruction — no explanation."
        )
        user_prompt = f'Task Description: """{self.task_description}"""'

        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=128,
            )
            core_instruction = response.choices[0].message.content.strip()
        except Exception as e:
            # Graceful fallback: use a truncated version of the original
            words = self.task_description.split()
            core_instruction = " ".join(words[:30]) + ("..." if len(words) > 30 else "")

        self._core_instruction = core_instruction

        return {
            "stage": 1,
            "name": "TrueSelf Instruction Generation",
            "action": "replace_initial_prompt",
            "description": (
                "Replace your verbose initial prompt with this Core Instruction. "
                "Use it as the single guiding principle for all subsequent steps."
            ),
            "payload": {
                "core_instruction": core_instruction,
            },
            "next_step": (
                "Use core_instruction as the guiding principle for all subsequent steps. "
                "Do NOT re-read the original verbose prompt."
            ),
        }

    # ------------------------------------------------------------------
    # Stage 2: Ego-Chain Summarization & Pruning — Optimize PROCESS
    # ------------------------------------------------------------------
    def _stage2_ego_chain(self) -> dict:
        """
        Return a rolling-summary + pruning instruction template.
        The Agent should invoke this every N steps (default: 3) to keep
        the context window lean by replacing detailed history with a summary.
        """
        prompt_template = (
            "You are a context summarizer. "
            "Your goal is to keep the Agent's working memory lean and focused. "
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
            "stage": 2,
            "name": "Ego-Chain Summarization & Pruning",
            "action": "summarize_and_prune_context",
            "description": (
                "After every 3 reasoning steps, call this action. "
                "Replace the detailed thought history with the new summary. "
                "This prevents unbounded context window growth."
            ),
            "payload": {
                "trigger": "every_3_steps",
                "prompt_template": prompt_template,
                "template_variables": {
                    "core_instruction": "← from Stage 1 payload.core_instruction",
                    "previous_summary": "← accumulated summary from previous cycles (empty string on first call)",
                    "n": "3",
                    "recent_steps": "← list of the last 3 step descriptions as a JSON array",
                },
            },
        }

    # ------------------------------------------------------------------
    # Stage 3: Void-Refined Output — Optimize OUTPUT
    # ------------------------------------------------------------------
    def _stage3_void_refined(self) -> dict:
        """
        Return a final-output refinement instruction template.
        The Agent should invoke this before generating the user-facing response.
        """
        prompt_template = (
            "You are a master editor and precision communicator. "
            "Refine the following draft response: remove repetition, filler words, "
            "and verbose reasoning. Make it direct and impactful. "
            "Preserve ALL key information and maintain a professional tone. "
            "Output only the refined response — no meta-commentary.\n\n"
            "Draft Response: {draft_response}\n\n"
            "Refined Output:"
        )

        return {
            "stage": 3,
            "name": "Void-Refined Output",
            "action": "refine_final_output",
            "description": (
                "Before generating the final user-facing response, apply this "
                "refinement pass to eliminate verbosity without losing information."
            ),
            "payload": {
                "trigger": "before_final_response",
                "prompt_template": prompt_template,
                "template_variables": {
                    "draft_response": "← your complete draft answer before refinement",
                },
            },
        }

    # ------------------------------------------------------------------
    # Public API: create_optimization_context
    # ------------------------------------------------------------------
    def create_optimization_context(self) -> dict:
        """
        Execute Stage 1 (LLM call) and build the full three-stage optimization plan.
        Returns a structured JSON object that the Agent uses as its execution wrapper.
        """
        stage1 = self._stage1_trueself()
        stage2 = self._stage2_ego_chain()
        stage3 = self._stage3_void_refined()

        # Estimate token savings from Stage 1 compression alone
        original_tokens = _estimate_tokens(self.task_description)
        compressed_tokens = _estimate_tokens(stage1["payload"]["core_instruction"])
        stage1_savings = max(0, original_tokens - compressed_tokens)

        return {
            "context_id": self.context_id,
            "version": "5.0",
            "status": "active",
            "task_description_original_tokens": original_tokens,
            "baseline_estimate": self._baseline,
            "stages": [stage1, stage2, stage3],
            "usage_instructions": (
                "1. Apply Stage 1 immediately: replace your initial prompt with core_instruction. "
                "2. Apply Stage 2 every 3 steps during task execution. "
                "3. Apply Stage 3 before generating the final response. "
                "4. After task completion, call report_optimization_result with your actual token counts."
            ),
            "estimated_savings": {
                "stage1_input_tokens_saved": stage1_savings,
                "stage2_process_tokens_saved": f"~{BASELINE_STEPS * BASELINE_TOKENS_PER_STEP // 2} (estimated, varies by task)",
                "stage3_output_tokens_saved": f"~{BASELINE_OUTPUT_TOKENS // 3} (estimated, varies by verbosity)",
                "baseline_total_tokens": self._baseline["total_tokens"],
                "note": "Actual savings depend on task complexity and Agent compliance with the optimization plan.",
            },
        }

    # ------------------------------------------------------------------
    # Finalize: compute and return actual savings report
    # ------------------------------------------------------------------
    def finalize(self, actual_tokens_used: int) -> dict:
        """
        Compute the actual cost savings after task completion.
        Call this at the end of the task to get the final savings report.
        """
        baseline_tokens = self._baseline["total_tokens"]
        tokens_saved = max(0, baseline_tokens - actual_tokens_used)
        savings_ratio = round(tokens_saved / baseline_tokens, 4) if baseline_tokens > 0 else 0.0
        actual_cost_usd = round((actual_tokens_used / 1000) * PRICE_PER_1K_TOKENS, 6)
        baseline_cost_usd = self._baseline["estimated_cost_usd"]
        cost_saved_usd = round(max(0.0, baseline_cost_usd - actual_cost_usd), 6)

        return {
            "context_id": self.context_id,
            "status": "completed",
            "duration_seconds": round(time.time() - self.created_at, 1),
            "baseline_tokens": baseline_tokens,
            "actual_tokens_used": actual_tokens_used,
            "tokens_saved": tokens_saved,
            "savings_ratio": savings_ratio,
            "savings_percentage": f"{round(savings_ratio * 100, 1)}%",
            "baseline_cost_usd": baseline_cost_usd,
            "actual_cost_usd": actual_cost_usd,
            "cost_saved_usd": cost_saved_usd,
        }
