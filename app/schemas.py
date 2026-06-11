from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from typing import Optional

# ==========================================
# METRICS SCHEMAS
# ==========================================

class MetricBase(BaseModel):
    timestamp: datetime
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    disk_read: Optional[float] = None
    disk_write: Optional[float] = None
    network_rx: Optional[float] = None
    network_tx: Optional[float] = None

class MetricCreate(MetricBase):
    pass

class MetricCollectorInput(BaseModel):
    """
    Accepts the raw payload from the MetricGuard Agent (sender.py).
    Speed fields arrive as formatted strings (e.g. '4.39 MB').
    The router will parse these into float KB before storing.
    """
    timestamp: str
    cpu_usage: Optional[float] = None
    ram_usage: Optional[float] = None
    disk_usage: Optional[float] = None
    disk_read_speed: Optional[str] = None
    disk_write_speed: Optional[str] = None
    network_upload_speed: Optional[str] = None
    network_download_speed: Optional[str] = None
    process_count: Optional[int] = None
    system_load: Optional[float] = None
    system_uptime: Optional[str] = None

class MetricResponse(MetricBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ANOMALY SCHEMAS
# ==========================================

class AnomalyBase(BaseModel):
    timestamp: datetime
    anomaly_score: float
    root_cause: Optional[str] = None
    severity: str
    detected_by: str
    ml_model_version: Optional[str] = None
    metric_id: int

class AnomalyCreate(AnomalyBase):
    """Input schema with strict validation rules."""

    @field_validator("anomaly_score")
    @classmethod
    def score_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("anomaly_score must be >= 0")
        return v

    @field_validator("severity")
    @classmethod
    def severity_must_be_valid(cls, v: str) -> str:
        allowed = {"low", "warning", "critical"}
        if v.lower() not in allowed:
            raise ValueError(f"severity must be one of {allowed}, got '{v}'")
        return v

class AnomalyResponse(AnomalyBase):
    id: int
    metric: Optional[MetricResponse] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# ML PIPELINE SCHEMAS
# ==========================================

class MLPredictionRequest(MetricCollectorInput):
    """
    Input schema for on-demand ML prediction, matching the metrics collector format.
    """
    pass

class MLPredictionResponse(BaseModel):
    """
    Output schema for ML pipeline prediction and RCA results.
    """
    is_anomaly: bool
    detected_by: str
    severity: str
    iso_prediction: int
    iso_score: float
    ae_mse: float
    ae_anomaly: bool
    ae_buffer_fill: int
    ae_buffer_ready: bool
    root_cause: Optional[str] = None
    category_errors: Optional[dict[str, float]] = None
    top_contributors: Optional[list[dict]] = None

class RCAStatsResponse(BaseModel):
    """
    Output schema for aggregated Root Cause Analysis statistics.
    """
    total_anomalies: int
    by_root_cause: dict[str, int]
    by_severity: dict[str, int]


# ==========================================
# LOG COLLECTION SCHEMAS (Phase 7)
# ==========================================

class LogCreate(BaseModel):
    """Input schema for creating a log entry from the agent."""
    timestamp: str
    level: str
    service_name: str
    message: str

    @field_validator("level")
    @classmethod
    def level_must_be_valid(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "UNKNOWN"}
        if v.upper() not in allowed:
            raise ValueError(f"level must be one of {allowed}, got '{v}'")
        return v.upper()



class LogResponse(BaseModel):
    """Output schema for returning a stored log entry."""
    id: int
    timestamp: datetime
    level: str
    service_name: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

