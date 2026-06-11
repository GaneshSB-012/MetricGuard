"""
==========================================================
MetricGuard — Recommendation Schemas  (recommendation.py)
==========================================================

Phase 13: Recommendation Engine

Pydantic schemas for recommendation requests and responses.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class RecommendationRequest(BaseModel):
    """
    Input schema for POST /api/recommendations.
    """
    root_cause: str = Field(
        ...,
        min_length=1,
        description="Root cause description from the RCA module.",
    )
    severity: str = Field(
        ...,
        description="Severity classification (Critical, High, Medium, Low).",
    )
    impacted_services: List[str] = Field(
        default_factory=list,
        description="List of impacted service names from the Service Impact module.",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence score of the root cause from RCA.",
    )

    @field_validator("severity")
    @classmethod
    def severity_must_be_valid(cls, v: str) -> str:
        allowed = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        upper = v.strip().upper()
        if upper not in allowed:
            # Also allow title case comparison but map to clean string
            title = v.strip().capitalize()
            if title in {"Critical", "High", "Medium", "Low"}:
                return title
            raise ValueError(
                f"severity must be one of {sorted(allowed)} (case-insensitive), got '{v}'"
            )
        # Convert to title case for internal consistency
        return upper.capitalize()

    @field_validator("impacted_services")
    @classmethod
    def clean_impacted_services(cls, v: List[str]) -> List[str]:
        return [s.strip().lower() for s in v if s.strip()]


class RecommendationItem(BaseModel):
    """
    Output schema for a single recommendation action and its confidence score.
    """
    action: str = Field(..., description="Actionable troubleshooting or remediation step.")
    confidence: float = Field(..., description="Calculated recommendation confidence.")


class RecommendationResponse(BaseModel):
    """
    Response schema returning a list of confidence-scored recommendations.
    """
    root_cause: str = Field(..., description="The analyzed root cause.")
    recommendations: List[RecommendationItem] = Field(
        ...,
        description="List of suggested actions with confidence levels.",
    )
