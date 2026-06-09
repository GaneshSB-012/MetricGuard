"""
==========================================================
MetricGuard — Correlation Model  (correlation.py)
==========================================================

Phase 10: Metric-Log Correlation Engine
"""

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class Correlation(Base):
    """
    SQLAlchemy ORM model representing a detected correlation
    between a metric anomaly and a log anomaly.
    """
    __tablename__ = "correlations"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # Foreign key to the metric anomaly that triggered the correlation
    metric_anomaly_id = Column(
        Integer,
        ForeignKey("anomalies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Foreign key to the log entry identified as a log anomaly
    log_anomaly_id = Column(
        Integer,
        ForeignKey("logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Correlation score (0.0 to 1.0)
    correlation_score = Column(
        Float,
        nullable=False,
    )

    # Human-readable root cause inferred from log message keywords
    inferred_cause = Column(
        String(255),
        nullable=True,
    )

    # Confidence percentage (0 to 100)
    confidence = Column(
        Float,
        nullable=False,
    )

    # Audit field
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Phase 11 Prep: Service/Host context
    service_name = Column(
        String(100),
        nullable=True,
    )
    host_name = Column(
        String(100),
        nullable=True,
    )
    container_id = Column(
        String(100),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Relationships
    # ---------------------------------------------------------
    metric_anomaly = relationship(
        "Anomaly",
        foreign_keys=[metric_anomaly_id],
        lazy="select",
    )

    log_entry = relationship(
        "Log",
        foreign_keys=[log_anomaly_id],
        lazy="select",
    )

    # ---------------------------------------------------------
    # Constraints & Table Arguments
    # ---------------------------------------------------------
    __table_args__ = (
        UniqueConstraint(
            "metric_anomaly_id",
            "log_anomaly_id",
            name="uq_metric_log_correlation",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Correlation("
            f"id={self.id}, "
            f"metric_anomaly_id={self.metric_anomaly_id}, "
            f"log_anomaly_id={self.log_anomaly_id}, "
            f"score={self.correlation_score}, "
            f"cause='{self.inferred_cause}', "
            f"service='{self.service_name}'"
            f")>"
        )
