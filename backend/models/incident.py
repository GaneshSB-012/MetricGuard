"""
==========================================================
MetricGuard — Incident Model  (incident.py)
==========================================================

Phase 12: Alert Prioritization & Incident Management

Stores trackable incidents generated from RCA + Service
Impact outputs with priority, severity, deduplication
group keys, and lifecycle status management.
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


# =========================================================
# CONSTANTS
# =========================================================

VALID_STATUSES = (
    "OPEN",
    "INVESTIGATING",
    "MITIGATED",
    "RESOLVED",
    "CLOSED",
)

VALID_PRIORITIES = ("P1", "P2", "P3", "P4")

VALID_SEVERITIES = ("Critical", "High", "Medium", "Low")


# =========================================================
# INCIDENT MODEL
# =========================================================

class Incident(Base):
    """
    SQLAlchemy ORM model representing a trackable incident
    generated from the RCA and Service Impact Analysis phases.
    """
    __tablename__ = "incidents"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )

    # Human-readable incident identifier (INC-000001, INC-000002, …)
    incident_id = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )

    # Root cause description from the RCA module
    root_cause = Column(
        String(255),
        nullable=False,
        index=True,
    )

    # Comma-separated list of impacted services
    impacted_services = Column(
        String(1000),
        nullable=False,
    )

    # Priority (P1 – P4)
    priority = Column(
        String(5),
        nullable=False,
        index=True,
    )

    # Severity (Critical / High / Medium / Low)
    severity = Column(
        String(20),
        nullable=False,
        index=True,
    )

    # Lifecycle status
    status = Column(
        String(20),
        nullable=False,
        default="OPEN",
        index=True,
    )

    # Number of duplicate alerts grouped into this incident
    alert_count = Column(
        Integer,
        nullable=False,
        default=1,
    )

    # Deduplication / grouping key:  root_cause + sorted impacted services
    group_key = Column(
        String(500),
        nullable=False,
        index=True,
    )

    # Audit fields
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ---------------------------------------------------------
    # Constraints
    # ---------------------------------------------------------
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'INVESTIGATING', 'MITIGATED', 'RESOLVED', 'CLOSED')",
            name="chk_incident_status_valid",
        ),
        CheckConstraint(
            "priority IN ('P1', 'P2', 'P3', 'P4')",
            name="chk_incident_priority_valid",
        ),
        CheckConstraint(
            "alert_count >= 1",
            name="chk_alert_count_positive",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Incident("
            f"incident_id='{self.incident_id}', "
            f"root_cause='{self.root_cause}', "
            f"priority='{self.priority}', "
            f"severity='{self.severity}', "
            f"status='{self.status}', "
            f"alert_count={self.alert_count}"
            f")>"
        )
