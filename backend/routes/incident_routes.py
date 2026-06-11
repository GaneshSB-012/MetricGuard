"""
==========================================================
MetricGuard — Incident Routes  (incident_routes.py)
==========================================================

Phase 12: Alert Prioritization & Incident Management

REST API endpoints for Incident Management:
    - POST  /incidents               – Generate or deduplicate an incident
    - GET   /incidents               – List incidents (with pagination & filtering)
    - GET   /incidents/{incident_id} – Get complete incident details
    - PATCH /incidents/{incident_id} – Update incident lifecycle status
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from backend.schemas import (
    IncidentCreate,
    IncidentCreateResponse,
    IncidentListResponse,
    IncidentResponse,
    IncidentUpdate,
    RecommendationResponse,
)
from backend.services.incident_service import get_incident_service

logger = logging.getLogger("metricguard.routers.incidents")

router = APIRouter(prefix="/incidents", tags=["Incidents"])

# Singleton service instance
_service = get_incident_service()



# ==========================================================
# POST /incidents
# ==========================================================

@router.post("/", response_model=IncidentCreateResponse, status_code=201)
def create_incident(payload: IncidentCreate, db: Session = Depends(get_db)):
    """
    Submit an RCA and Service Impact payload to create a trackable incident.
    Automations handle priority assignment, severity classification,
    deduplication, and alert grouping.
    """
    try:
        logger.info(
            "[Incident API] Creating incident for root cause='%s', impacted_services=%s",
            payload.root_cause,
            payload.impacted_services,
        )
        incident = _service.create_incident(
            db=db,
            root_cause=payload.root_cause,
            impacted_services=payload.impacted_services,
        )
        return incident
    except Exception as e:
        logger.error("[Incident API] Incident creation failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Incident creation failed: {str(e)}",
        )


# ==========================================================
# GET /incidents
# ==========================================================

@router.get("/", response_model=IncidentListResponse)
def list_incidents(
    page: int = Query(default=1, ge=1, description="Page number for pagination"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(default=None, description="Filter incidents by status"),
    priority: Optional[str] = Query(default=None, description="Filter incidents by priority"),
    db: Session = Depends(get_db),
):
    """
    Retrieve all incidents, supporting pagination and status/priority filtering.
    """
    try:
        incidents, total = _service.list_incidents(
            db=db,
            page=page,
            limit=limit,
            status=status,
            priority=priority,
        )
        logger.info(
            "[Incident API] Returning %d incidents (total %d) for page %d, limit %d",
            len(incidents),
            total,
            page,
            limit,
        )
        return IncidentListResponse(
            total=total,
            page=page,
            limit=limit,
            incidents=incidents,
        )
    except Exception as e:
        logger.error("[Incident API] Failed to list incidents: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list incidents: {str(e)}",
        )


# ==========================================================
# GET /incidents/{incident_id}
# ==========================================================

@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident_detail(incident_id: str, db: Session = Depends(get_db)):
    """
    Retrieve full details of an incident by its incident_id (e.g. INC-000001).
    """
    incident = _service.get_incident(db, incident_id)
    if incident is None:
        logger.warning("[Incident API] Incident not found: %s", incident_id)
        raise HTTPException(
            status_code=404,
            detail=f"Incident '{incident_id}' not found.",
        )
    return incident


# ==========================================================
# GET /incidents/{incident_id}/recommendations
# ==========================================================

@router.get("/{incident_id}/recommendations", response_model=RecommendationResponse)
def get_incident_recommendations(incident_id: str, db: Session = Depends(get_db)):
    """
    Retrieve remediation recommendations for a specific incident.
    """
    incident = _service.get_incident(db, incident_id)
    if incident is None:
        logger.warning("[Incident API] Incident not found: %s", incident_id)
        raise HTTPException(
            status_code=404,
            detail=f"Incident '{incident_id}' not found.",
        )
        
    from backend.recommendation_engine import get_recommendation_service
    rec_service = get_recommendation_service()
    
    # Impacted services stored as comma-separated string in DB
    services_list = [s.strip() for s in incident.impacted_services.split(",") if s.strip()]
    
    recs = rec_service.get_recommendations(
        root_cause=incident.root_cause,
        severity=incident.severity,
        impacted_services=services_list,
        confidence=None
    )
    
    return {
        "root_cause": incident.root_cause,
        "recommendations": recs
    }


# ==========================================================
# PATCH /incidents/{incident_id}

# ==========================================================

@router.patch("/{incident_id}", response_model=IncidentResponse)
def update_incident_status(
    incident_id: str,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
):
    """
    Update the lifecycle status of an incident.
    Validates state transitions (e.g., OPEN -> INVESTIGATING -> MITIGATED -> RESOLVED -> CLOSED).
    """
    try:
        logger.info(
            "[Incident API] Request to update status of %s to '%s'",
            incident_id,
            payload.status,
        )
        incident = _service.update_status(
            db=db,
            incident_id=incident_id,
            new_status=payload.status,
        )
        return incident
    except ValueError as ve:
        logger.warning("[Incident API] Validation error on PATCH: %s", ve)
        raise HTTPException(
            status_code=400,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(
            "[Incident API] Failed to update incident status: %s",
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update incident status: {str(e)}",
        )
