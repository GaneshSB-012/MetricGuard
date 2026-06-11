"""
==========================================================
MetricGuard — Service Impact Routes  (routes.py)
==========================================================

Phase 11: Service Impact Analysis & Dependency Graph

REST API endpoints:
    GET  /services             – list all registered services
    GET  /services/impacted    – list currently impacted services
    GET  /services/{name}      – single-service detail + health
    POST /services/analyze     – run impact analysis from RCA output
    GET  /services/graph       – return the full dependency graph
    GET  /services/dashboard   – dashboard-ready impact summary
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from backend.service_impact.service_graph import get_service_graph
from backend.service_impact.impact_analyzer import get_impact_analyzer
from backend.service_impact.service_health import get_service_health_engine
from backend.services.incident_service import get_incident_service

logger = logging.getLogger("metricguard.service_impact.routes")

router = APIRouter(prefix="/services", tags=["Service Impact Analysis"])


# =========================================================
# REQUEST / RESPONSE SCHEMAS
# =========================================================

class AnalyzeRequest(BaseModel):
    """Input payload for POST /services/analyze."""
    root_cause: str = Field(..., min_length=1, description="Root cause description from the RCA module.")
    affected_service: str = Field(..., min_length=1, description="Service where the failure originated.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="RCA confidence score (0–1).")


class AnalyzeResponse(BaseModel):
    """Output payload for POST /services/analyze."""
    root_cause: str
    affected_service: str
    confidence: float
    impacted_services: List[str]
    severity: str
    impact_chain: List[str]
    total_affected: int
    analysis_timestamp: str


class ServiceDetailResponse(BaseModel):
    """Output for GET /services/{service_name}."""
    service_name: str
    status: str
    severity: str
    root_dependency: Optional[str] = None
    dependencies: List[str]


class ServiceHealthResponse(BaseModel):
    """Individual health record inside list responses."""
    service_name: str
    status: str
    severity: str
    root_dependency: Optional[str] = None
    dependencies: List[str]


class ImpactedServicesResponse(BaseModel):
    """Output for GET /services/impacted."""
    impacted_services: List[str]


class DashboardResponse(BaseModel):
    """Dashboard-ready summary for the frontend."""
    root_cause: Optional[str] = None
    affected_service: Optional[str] = None
    impacted_services: List[str] = []
    severity: Optional[str] = None
    confidence: Optional[float] = None
    total_affected: int = 0
    service_health: List[ServiceHealthResponse] = []


# =========================================================
# ENDPOINTS
# =========================================================


# ----------------------------------------------------------
# GET /services
# ----------------------------------------------------------

@router.get("/", response_model=List[ServiceHealthResponse])
def list_services():
    """
    Return all registered services with their current health.
    """
    try:
        health_engine = get_service_health_engine()
        services = health_engine.compute_all_health()
        logger.info("[Services API] Returning %d services.", len(services))
        return services
    except Exception as e:
        logger.error("[Services API] Failed to list services: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list services: {str(e)}")


# ----------------------------------------------------------
# GET /services/impacted
# ----------------------------------------------------------

@router.get("/impacted", response_model=ImpactedServicesResponse)
def get_impacted_services():
    """
    Return the list of services currently impacted by the
    most recent impact analysis.
    """
    try:
        health_engine = get_service_health_engine()
        impacted = health_engine.get_impacted_services()
        logger.info("[Services API] Returning %d impacted service(s).", len(impacted))
        return ImpactedServicesResponse(impacted_services=impacted)
    except Exception as e:
        logger.error("[Services API] Failed to get impacted services: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get impacted services: {str(e)}")


# ----------------------------------------------------------
# GET /services/graph
# ----------------------------------------------------------

@router.get("/graph")
def get_dependency_graph():
    """
    Return the full service dependency graph as an adjacency list.
    """
    try:
        graph = get_service_graph()
        return {
            "services": graph.get_all_services(),
            "graph":    graph.get_graph(),
        }
    except Exception as e:
        logger.error("[Services API] Failed to get dependency graph: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get dependency graph: {str(e)}")


# ----------------------------------------------------------
# GET /services/dashboard
# ----------------------------------------------------------

@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard_summary():
    """
    Return a dashboard-ready summary combining the latest
    impact analysis and per-service health information.
    """
    try:
        analyzer = get_impact_analyzer()
        health_engine = get_service_health_engine()

        analysis = analyzer.get_last_analysis()
        all_health = health_engine.compute_all_health()

        if analysis is None:
            return DashboardResponse(
                service_health=[ServiceHealthResponse(**h) for h in all_health],
            )

        return DashboardResponse(
            root_cause=analysis.get("root_cause"),
            affected_service=analysis.get("affected_service"),
            impacted_services=analysis.get("impacted_services", []),
            severity=analysis.get("severity"),
            confidence=analysis.get("confidence"),
            total_affected=analysis.get("total_affected", 0),
            service_health=[ServiceHealthResponse(**h) for h in all_health],
        )
    except Exception as e:
        logger.error("[Services API] Dashboard error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dashboard error: {str(e)}")


# ----------------------------------------------------------
# POST /services/analyze
# ----------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_impact(payload: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Run service impact analysis using RCA output.

    Accepts:
        { "root_cause": "...", "affected_service": "...", "confidence": 0.94 }

    Returns the full analysis result including impacted services,
    severity, and the BFS impact chain.
    """
    try:
        analyzer = get_impact_analyzer()
        result = analyzer.analyze(
            root_cause=payload.root_cause,
            affected_service=payload.affected_service,
            confidence=payload.confidence,
        )
        logger.info(
            "[Services API] Impact analysis completed — severity=%s, impacted=%d",
            result["severity"],
            result["total_affected"],
        )

        # Automatically create or update an incident based on the analysis output
        try:
            incident_service = get_incident_service()
            incident_service.create_incident(
                db=db,
                root_cause=result["root_cause"],
                impacted_services=result["impacted_services"],
            )
        except Exception as err:
            logger.error(
                "[Services API] Automatically generating incident failed: %s",
                err,
                exc_info=True,
            )

        return AnalyzeResponse(**result)
    except ValueError as ve:
        logger.warning("[Services API] Validation error: %s", ve)
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error("[Services API] Analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Impact analysis failed: {str(e)}")


# ----------------------------------------------------------
# GET /services/{service_name}
# ----------------------------------------------------------

@router.get("/{service_name}", response_model=ServiceDetailResponse)
def get_service_detail(service_name: str):
    """
    Return detailed information for a single service, including
    its current health status and direct dependencies.
    """
    try:
        health_engine = get_service_health_engine()
        detail = health_engine.get_service_health(service_name)
        return ServiceDetailResponse(**detail)
    except ValueError as ve:
        logger.warning("[Services API] Service not found: %s", ve)
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error("[Services API] Failed to get service detail: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get service detail: {str(e)}")
