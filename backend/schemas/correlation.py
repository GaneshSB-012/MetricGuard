"""
==========================================================
MetricGuard — Correlation Schemas  (correlation.py)
==========================================================

Phase 10: Metric-Log Correlation Engine
"""

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


# ==========================================
# CORRELATION RESPONSE SCHEMAS
# ==========================================

class CorrelationResponse(BaseModel):
    """
    Output schema for a single correlation record.
    Used by GET /correlations and GET /correlations/latest.
    """
    id: int
    metric_anomaly_id: int
    log_anomaly_id: int
    correlation_score: float
    inferred_cause: Optional[str] = None
    confidence: float
    created_at: datetime

    # Phase 11 Prep columns
    service_name: Optional[str] = None
    host_name: Optional[str] = None
    container_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CorrelationRunResponse(BaseModel):
    """
    Output schema for POST /correlations/run.
    Reports how many correlations were created by the engine.
    """
    status: str
    correlations_created: int
