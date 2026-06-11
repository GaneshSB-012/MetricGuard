"""
==========================================================
MetricGuard — Alert Model  (models.py)
==========================================================

Phase 14: Real-Time Alerting System
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    CheckConstraint,
    func,
)
from app.database import Base


class Alert(Base):
    """
    SQLAlchemy ORM model representing a trackable and notify-able alert.
    """
    __tablename__ = "alerts"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # Human-readable alert identifier (ALT-001, ALT-002, ...)
    alert_id = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    # Severity (CRITICAL / HIGH / MEDIUM / LOW)
    severity = Column(
        String(20),
        nullable=False,
        index=True,
    )

    # Title of the alert (usually root cause)
    title = Column(
        String(255),
        nullable=False,
        index=True,
    )

    # Informative message detailing the alert
    message = Column(
        String(1000),
        nullable=False,
    )

    # Comma-separated list of affected services
    affected_services = Column(
        String(1000),
        nullable=False,
    )

    # Current lifecycle status (OPEN / ACKNOWLEDGED / RESOLVED)
    status = Column(
        String(20),
        nullable=False,
        default="OPEN",
        index=True,
    )

    # Timestamp when the alert was created
    timestamp = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')",
            name="chk_alert_status_valid",
        ),
        CheckConstraint(
            "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')",
            name="chk_alert_severity_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Alert("
            f"alert_id='{self.alert_id}', "
            f"title='{self.title}', "
            f"severity='{self.severity}', "
            f"status='{self.status}'"
            f")>"
        )
