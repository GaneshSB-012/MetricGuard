"""
==========================================================
MetricGuard — Recommendation API  (api.py)
==========================================================

Phase 13: Recommendation Engine

REST API endpoints for Recommendation Engine.
"""

from __future__ import annotations

import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Response

from typing import Dict, Any, List
from backend.schemas.recommendation import RecommendationRequest, RecommendationResponse
from backend.recommendation_engine.recommendation_service import get_recommendation_service, RecommendationService
from backend.recommendation_engine.metrics import (
    record_request,
    record_generation_time,
    record_confidence,
    HAS_PROMETHEUS,
)


logger = logging.getLogger("metricguard.recommendation.api")

router = APIRouter(prefix="/api/recommendations", tags=["Recommendations"])


@router.post("", response_model=RecommendationResponse, status_code=200)
@router.post("/", response_model=RecommendationResponse, status_code=200, include_in_schema=False)
def generate_recommendations(
    payload: RecommendationRequest,
    service: RecommendationService = Depends(get_recommendation_service),
) -> Dict[str, Any]:
    """
    Generate actionable troubleshooting recommendations from RCA, Service Impact, and Severity details.
    
    Accepts:
        root_cause: str
        severity: str
        impacted_services: List[str]
        confidence: Optional[float]
    """
    start_time = time.perf_counter()
    try:
        logger.info(
            "[Recommendation API] Generating recommendations for: root_cause='%s', severity='%s', impacted_services=%s",
            payload.root_cause, payload.severity, payload.impacted_services
        )

        # 1. Record Prometheus Counter
        record_request(payload.root_cause, payload.severity)

        # 2. Retrieve recommendation items
        recs = service.get_recommendations(
            root_cause=payload.root_cause,
            severity=payload.severity,
            impacted_services=payload.impacted_services,
            confidence=payload.confidence,
        )

        # 3. Calculate latency and observe metric
        duration = time.perf_counter() - start_time
        record_generation_time(duration)

        # 4. Observe average confidence Gauge
        confidences = [item["confidence"] for item in recs]
        record_confidence(confidences)

        return {
            "root_cause": payload.root_cause,
            "recommendations": recs,
        }
    except Exception as e:
        logger.error("[Recommendation API] Failed to generate recommendations: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Recommendation generation failed: {str(e)}"
        )


@router.get("/metrics", tags=["Metrics"])
def get_recommendation_metrics():
    """
    Exposes recommendation-specific Prometheus metrics in standard format.
    """
    if not HAS_PROMETHEUS:
        return Response(
            content="# HELP recommendation_metrics_active status of prometheus_client package\n"
                    "# TYPE recommendation_metrics_active gauge\n"
                    "recommendation_metrics_active 0\n",
            media_type="text/plain"
        )
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.error("[Recommendation API] Failed to generate metrics output: %s", e)
        raise HTTPException(status_code=500, detail="Failed to scrape metrics")
