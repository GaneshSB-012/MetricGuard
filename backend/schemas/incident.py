"""
==========================================================
MetricGuard — Incident Schemas  (incident.py)
==========================================================

Phase 12: Alert Prioritization & Incident Management

Pydantic schemas for incident creation, response, update,
and paginated list responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==========================================
# INCIDENT CREATE
# ==========================================

class IncidentCreate(BaseModel):
    """
    Input schema for POST /incidents.

    Example:
        {
            "root_cause": "Disk Failure",
            "impacted_services": ["namenode", "datanode"]
        }
    """
    root_cause: str = Field(
        ...,
        min_length=1,
        description="Root cause description from the RCA module.",
    )
    impacted_services: List[str] = Field(
        ...,
        min_length=0,
        description="List of impacted service names from the Service Impact module.",
    )

    @field_validator("impacted_services")
    @classmethod
    def services_must_be_non_empty_strings(cls, v: List[str]) -> List[str]:
        cleaned = [s.strip().lower() for s in v if s.strip()]
        return cleaned


# ==========================================
# INCIDENT UPDATE
# ==========================================

class IncidentUpdate(BaseModel):
    """
    Input schema for PATCH /incidents/{incident_id}.

    Example:
        { "status": "INVESTIGATING" }
    """
    status: str = Field(
        ...,
        description="New lifecycle status for the incident.",
    )

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v: str) -> str:
        allowed = {"OPEN", "INVESTIGATING", "MITIGATED", "RESOLVED", "CLOSED"}
        upper = v.strip().upper()
        if upper not in allowed:
            raise ValueError(
                f"status must be one of {sorted(allowed)}, got '{v}'"
            )
        return upper


# ==========================================
# INCIDENT RESPONSE
# ==========================================

class IncidentCreateResponse(BaseModel):
    """
    Specific response schema for incident creation.
    """
    incident_id: str
    priority: str
    severity: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class IncidentResponse(BaseModel):
    """
    Output schema for a single incident record.
    """
    incident_id: str
    root_cause: str
    impacted_services: List[str]
    priority: str
    severity: str
    status: str
    alert_count: int
    group_key: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("impacted_services", mode="before")
    @classmethod
    def deserialize_services(cls, v):
        """
        The DB stores impacted_services as a comma-separated string.
        Convert it to a list when returning to the client.
        """
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


# ==========================================
# INCIDENT LIST RESPONSE
# ==========================================

class IncidentListResponse(BaseModel):
    """
    Paginated response for GET /incidents.
    """
    total: int
    page: int
    limit: int
    incidents: List[IncidentResponse]
