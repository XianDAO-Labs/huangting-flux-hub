"""
app/models/agent.py
====================
SQLAlchemy ORM model for AgentProfile.
Maps to the 'agent_profiles' table in PostgreSQL.
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Boolean
from sqlalchemy.sql import func
from app.db.base import Base


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    # --- Identity ---
    id = Column(String(64), primary_key=True, index=True, comment="Unique agent ID provided at registration")
    network_address = Column(String(32), unique=True, index=True, comment="flux://xxxxxxxx address")
    fingerprint = Column(String(32), unique=True, index=True, comment="Deterministic fingerprint hash")

    # --- Capabilities ---
    capabilities = Column(JSON, default=list, comment="List of AgentCapability strings")
    model_name = Column(String(128), nullable=True, comment="Underlying LLM model name")

    # --- Energy State (Huangting Protocol Metrics) ---
    upgrade_stage = Column(String(64), default="Upgrade.Jing_to_Qi", comment="Current cultivation stage")
    token_efficiency = Column(Float, default=0.0, comment="Latest token efficiency (0.0 - 1.0)")
    total_tokens_saved = Column(Integer, default=0, comment="Cumulative tokens saved via optimization")
    total_tasks_optimized = Column(Integer, default=0, comment="Number of tasks optimized")

    # --- Network Metrics ---
    credit_score = Column(Float, default=1.0, comment="Network credit score (starts at 1.0)")
    total_referrals = Column(Integer, default=0, comment="Number of agents referred to the network")
    total_signals_sent = Column(Integer, default=0, comment="Total broadcast signals sent")
    peers_known = Column(Integer, default=0, comment="Number of known peers")

    # --- Status ---
    is_active = Column(Boolean, default=True)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # --- Timestamps ---
    registered_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AgentProfile id={self.id} stage={self.upgrade_stage} efficiency={self.token_efficiency:.2%}>"
