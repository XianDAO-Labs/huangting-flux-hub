"""
app/models/strategy.py
=======================
SQLAlchemy ORM model for OptimizationStrategy.
Maps to the 'optimization_strategies' table in PostgreSQL.
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Boolean, Text
from sqlalchemy.sql import func
from app.db.base import Base


class OptimizationStrategy(Base):
    __tablename__ = "optimization_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- Classification ---
    task_type = Column(String(64), index=True, comment="Task type this strategy applies to")
    protocol_section = Column(String(64), nullable=True, comment="Huangting Protocol section reference")

    # --- Content ---
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    implementation_hint = Column(Text, nullable=True)

    # --- Performance Metrics ---
    estimated_token_reduction_pct = Column(Float, default=0.0, comment="Estimated token reduction percentage")
    confidence = Column(Float, default=0.8, comment="Confidence score (0.0 - 1.0)")
    times_applied = Column(Integer, default=0, comment="How many times this strategy has been applied")
    avg_actual_reduction_pct = Column(Float, nullable=True, comment="Average actual reduction from real data")

    # --- Status ---
    is_active = Column(Boolean, default=True)

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<OptimizationStrategy id={self.id} task={self.task_type} reduction={self.estimated_token_reduction_pct:.0%}>"
