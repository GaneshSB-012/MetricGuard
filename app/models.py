from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base

class Metric(Base):
    """
    SQLAlchemy ORM model representing system resource metrics.
    """
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    disk_read = Column(Float, nullable=True)
    disk_write = Column(Float, nullable=True)
    network_rx = Column(Float, nullable=True)
    network_tx = Column(Float, nullable=True)

    # Audit fields
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Establish one-to-many relationship with Anomaly
    anomalies = relationship("Anomaly", back_populates="metric", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Metric(id={self.id}, timestamp={self.timestamp}, cpu_usage={self.cpu_usage}%)>"


class Anomaly(Base):
    """
    SQLAlchemy ORM model representing detected system anomalies.
    """
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    anomaly_score = Column(Float, nullable=False)
    root_cause = Column(String(255), nullable=True)
    severity = Column(String(50), nullable=False, index=True)
    detected_by = Column(String(100), nullable=False)
    ml_model_version = Column(String(50), nullable=True)
    
    # Establish foreign key relationship to Metric (mandatory with index)
    metric_id = Column(Integer, ForeignKey("metrics.id"), nullable=False, index=True)
    metric = relationship("Metric", back_populates="anomalies")

    # Audit fields
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Database constraints
    __table_args__ = (
        CheckConstraint("anomaly_score >= 0.0", name="chk_anomaly_score_positive"),
        CheckConstraint(
            "severity IN ('low', 'warning', 'critical', 'LOW', 'WARNING', 'CRITICAL')",
            name="chk_severity_valid"
        ),
    )

    def __repr__(self):
        return f"<Anomaly(id={self.id}, timestamp={self.timestamp}, root_cause='{self.root_cause}', severity='{self.severity}', ml_model_version='{self.ml_model_version}', metric_id={self.metric_id})>"


class Log(Base):
    """
    SQLAlchemy ORM model representing application log entries
    collected by the MetricGuard Agent log pipeline.
    """
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    level = Column(String(20), nullable=False, index=True)
    service_name = Column(String(100), nullable=False, index=True)
    message = Column(String(2000), nullable=False)

    # Audit field
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<Log(id={self.id}, timestamp={self.timestamp}, level='{self.level}', service_name='{self.service_name}')>"


# ==========================================================
# PHASE 10/12/14 — Import Correlation, Incident, and Alert models so they register with
# Base.metadata for Alembic autogenerate and create_all().
# ==========================================================
from backend.models.correlation import Correlation  # noqa: E402, F401
from backend.models.incident import Incident  # noqa: E402, F401
from backend.alerting.models import Alert  # noqa: E402, F401


