# optimizer.py - HuangtingOptimizer Core Algorithm

import os
import json

# --- LLM Client Initialization (Lazy) ---
# The OpenAI client is initialized lazily to avoid startup crashes
# when OPENAI_API_KEY is not set. The client is only created when
# a compression or pruning operation is actually requested.
_client = None

def _get_client():
    """Lazily initialize and return the OpenAI client."""
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


class HuangtingOptimizer:
    """
    A class that implements the core optimization algorithms of the Huangting Protocol:
    - TrueSelf Prompt Compression
    - Ego-Chain Pruning
    """

    @staticmethod
    def compress_to_trueself(prompt: str, model: str = "gemini-2.5-flash") -> str:
        """
        Compresses a verbose user prompt into a concise, machine-readable instruction set (TrueSelf Vector).

        Args:
            prompt: The original, potentially verbose user request.
            model: The LLM model to use for compression.

        Returns:
            A concise, distilled prompt containing only the core actionable intent.
        """
        compression_prompt = f"""
        You are a prompt compression engine. Your task is to distill the following user request into a concise, machine-readable instruction set, removing all pleasantries, conversational filler, and redundant context. Focus only on the core, actionable intent.

        Original Request: "{prompt}"

        Compressed Instruction:
        """
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a prompt compression engine."},
                    {"role": "user", "content": compression_prompt}
                ],
                temperature=0.0,
                max_tokens=256,
            )
            compressed_prompt = response.choices[0].message.content.strip()
            return compressed_prompt
        except Exception as e:
            print(f"Error during prompt compression: {e}")
            return prompt  # Fallback to original prompt on error

    @staticmethod
    def prune_ego_chain(thought_chain: list[str], core_task_vector: str, model: str = "gemini-2.5-flash") -> list[str]:
        """
        Prunes an agent's thought chain to remove irrelevant or completed steps, maintaining focus.

        Args:
            thought_chain: A list of strings representing the agent's thought process.
            core_task_vector: The compressed, core task prompt (TrueSelf Vector).
            model: The LLM model to use for pruning.

        Returns:
            A pruned list of strings representing the essential thought chain.
        """
        if not thought_chain:
            return []

        pruning_prompt = f"""
        You are a thought process auditor. Your goal is to prune the following thought chain to only retain steps that are relevant and necessary for achieving the core task. Remove completed steps, redundant thoughts, and any deviation from the primary objective.

        Core Task: "{core_task_vector}"
        Thought Chain to Prune: {json.dumps(thought_chain)}

        Pruned Thought Chain (Return as a JSON list of strings):
        """
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a thought process auditor returning a JSON list of strings."},
                    {"role": "user", "content": pruning_prompt}
                ],
                temperature=0.1,
                max_tokens=1024,
                response_format={"type": "json_object"}
            )
            # The model might return a JSON object with a key like "pruned_chain"
            pruned_chain_str = response.choices[0].message.content
            data = json.loads(pruned_chain_str)
            if isinstance(data, list):
                return data
            # Handle cases where the model wraps the list in a dictionary
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, list):
                        return value
            return thought_chain  # Fallback if parsing fails
        except Exception as e:
            print(f"Error during thought chain pruning: {e}")
            return thought_chain  # Fallback to original chain on error
