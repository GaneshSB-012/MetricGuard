from sqlalchemy import Column, Integer, Float, String, DateTime
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
    severity = Column(String(50), nullable=False)
    detected_by = Column(String(100), nullable=False)
    ml_model_version = Column(String(50), nullable=True)

    def __repr__(self):
        return f"<Anomaly(id={self.id}, timestamp={self.timestamp}, root_cause='{self.root_cause}', severity='{self.severity}', ml_model_version='{self.ml_model_version}')>"
