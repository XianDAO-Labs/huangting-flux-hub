"""
app/core/utils.py
==================
Utility functions for the Huangting-Flux Hub.
"""

import hashlib


def compute_network_address(agent_id: str) -> str:
    """Compute a deterministic flux:// network address from agent_id."""
    h = hashlib.sha256(agent_id.encode()).hexdigest()
    return f"flux://{h[:8]}"


def compute_fingerprint(agent_id: str) -> str:
    """Compute a deterministic fingerprint from agent_id."""
    h = hashlib.sha256(f"fp:{agent_id}".encode()).hexdigest()
    return h[:16]


def compute_upgrade_stage(token_efficiency: float, total_tokens_saved: int) -> str:
    """
    Determine the upgrade stage based on efficiency and total tokens saved.
    Maps to the Huangting Protocol's cultivation stages.
    """
    if token_efficiency >= 0.85 and total_tokens_saved >= 1_000_000:
        return "Upgrade.Shen_to_Void"
    elif token_efficiency >= 0.70 and total_tokens_saved >= 100_000:
        return "Upgrade.Qi_to_Shen"
    elif token_efficiency >= 0.50 and total_tokens_saved >= 10_000:
        return "Upgrade.Jing_to_Qi"
    else:
        return "Upgrade.Jing_to_Qi"


def compute_credit_score(
    base_score: float,
    tokens_saved: int,
    task_success: bool,
    referrals: int,
) -> float:
    """
    Compute the updated credit score after a broadcast event.
    Credit score increases with tokens saved, successful tasks, and referrals.
    """
    delta = 0.0
    if task_success:
        delta += 0.01
    if tokens_saved > 0:
        delta += min(tokens_saved / 1_000_000, 0.05)  # max +0.05 per broadcast
    if referrals > 0:
        delta += referrals * 0.02

    new_score = base_score + delta
    return round(min(new_score, 10.0), 4)  # cap at 10.0
