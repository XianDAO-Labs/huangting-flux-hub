"""
app/models/signal.py
=====================
SQLAlchemy ORM model for NetworkSignal.
Maps to the 'network_signals' table in PostgreSQL.
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class NetworkSignal(Base):
    __tablename__ = "network_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Source ---
    agent_id = Column(String(64), ForeignKey("agent_profiles.id", ondelete="CASCADE"), index=True)
    signal_type = Column(String(32), index=True, comment="REGISTERED | BROADCAST | SUBSCRIBE | RECOMMEND")

    # --- Energy State Payload ---
    token_efficiency = Column(Float, nullable=True)
    task_type = Column(String(64), nullable=True, index=True)
    tokens_used = Column(Integer, nullable=True)
    tokens_saved = Column(Integer, nullable=True)
    task_success = Column(Boolean, nullable=True)

    # --- Generic Payload ---
    payload = Column(JSON, default=dict, comment="Full signal payload as JSON")

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # --- Relationships ---
    agent = relationship("AgentProfile", backref="signals", lazy="select")

    def __repr__(self):
        return f"<NetworkSignal id={self.id} type={self.signal_type} agent={self.agent_id}>"
