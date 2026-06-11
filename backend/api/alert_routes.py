"""
==========================================================
MetricGuard — Alerting Routes  (alert_routes.py)
==========================================================

Phase 14: Real-Time Alerting System
"""

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from backend.alerting.alert_manager import get_alert_manager
from backend.alerting.repository import AlertRepository
from backend.alerting.websocket_notifier import get_websocket_manager
from backend.services.incident_service import get_incident_service

logger = logging.getLogger("metricguard.routers.alerts")

router = APIRouter(tags=["Alerts"])


# ==========================================================
# PYDANTIC SCHEMAS
# ==========================================================

class AlertSendRequest(BaseModel):
    """
    Input payload schema for POST /alerts/send.
    """
    incident_id: str = Field(
        ...,
        description="Unique business identifier of the incident (e.g., INC-000001)."
    )


class AlertSendResponse(BaseModel):
    """
    Response schema for POST /alerts/send.
    """
    success: bool
    alert_id: str


class AlertResponse(BaseModel):
    """
    Output schema for alert details.
    """
    alert_id: str
    severity: str
    title: str
    message: str
    affected_services: List[str]
    timestamp: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)

    @field_validator("affected_services", mode="before")
    @classmethod
    def deserialize_services(cls, v):
        """
        Deserialize affected services stored as comma-separated CSV string.
        """
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


# ==========================================================
# REST API ENDPOINTS
# ==========================================================

@router.post("/alerts/send", response_model=AlertSendResponse, status_code=201)
def send_alert(payload: AlertSendRequest, db: Session = Depends(get_db)):
    """
    Generate an alert from an incident ID, notify matching channels, and persist alert.
    """
    logger.info("[Alerts API] POST /alerts/send request for incident: %s", payload.incident_id)

    # 1. Fetch the incident
    incident_service = get_incident_service()
    incident = incident_service.get_incident(db, payload.incident_id)
    if incident is None:
        logger.warning("[Alerts API] Incident '%s' not found.", payload.incident_id)
        raise HTTPException(
            status_code=404,
            detail=f"Incident '{payload.incident_id}' not found."
        )

    # 2. Convert and publish alert
    try:
        alert_manager = get_alert_manager()
        db_alert = alert_manager.create_alert(db, incident)
        return AlertSendResponse(success=True, alert_id=db_alert.alert_id)
    except Exception as e:
        logger.error("[Alerts API] Failed to trigger alert for %s: %s", payload.incident_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate alert: {str(e)}"
        )


@router.get("/alerts", response_model=List[AlertResponse])
def get_alerts(db: Session = Depends(get_db)):
    """
    Retrieve a list of all system alerts.
    """
    try:
        alerts = AlertRepository.get_all(db)
        logger.info("[Alerts API] GET /alerts returned %d alerts", len(alerts))
        return alerts
    except Exception as e:
        logger.error("[Alerts API] Failed to retrieve alerts: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve alerts: {str(e)}"
        )


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
def get_alert_by_id(alert_id: str, db: Session = Depends(get_db)):
    """
    Retrieve detailed metadata for a single alert.
    """
    logger.info("[Alerts API] GET /alerts/%s requested", alert_id)
    alert = AlertRepository.get_by_alert_id(db, alert_id)
    if alert is None:
        logger.warning("[Alerts API] Alert '%s' not found", alert_id)
        raise HTTPException(
            status_code=404,
            detail=f"Alert '{alert_id}' not found."
        )
    return alert


@router.post("/alerts/{alert_id}/ack", response_model=AlertResponse)
def acknowledge_alert(alert_id: str, db: Session = Depends(get_db)):
    """
    Acknowledge an alert (state transition: OPEN -> ACKNOWLEDGED).
    """
    logger.info("[Alerts API] POST /alerts/%s/ack requested", alert_id)
    try:
        updated_alert = AlertRepository.update_status(db, alert_id, "ACKNOWLEDGED")
        return updated_alert
    except ValueError as ve:
        logger.warning("[Alerts API] Acknowledge validation failure: %s", ve)
        raise HTTPException(
            status_code=400,
            detail=str(ve)
        )
    except Exception as e:
        logger.error("[Alerts API] Failed to acknowledge alert %s: %s", alert_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Acknowledgement failed: {str(e)}"
        )


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(alert_id: str, db: Session = Depends(get_db)):
    """
    Resolve an acknowledged or open alert (state transition: ACKNOWLEDGED -> RESOLVED).
    """
    logger.info("[Alerts API] POST /alerts/%s/resolve requested", alert_id)
    try:
        updated_alert = AlertRepository.update_status(db, alert_id, "RESOLVED")
        return updated_alert
    except ValueError as ve:
        logger.warning("[Alerts API] Resolve validation failure: %s", ve)
        raise HTTPException(
            status_code=400,
            detail=str(ve)
        )
    except Exception as e:
        logger.error("[Alerts API] Failed to resolve alert %s: %s", alert_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Resolution failed: {str(e)}"
        )


# ==========================================================
# WEBSOCKET SUBSCRIPTION ENDPOINT
# ==========================================================

@router.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """
    WebSocket channel for clients to subscribe and receive real-time push alerts.
    """
    manager = get_websocket_manager()
    await manager.connect(websocket)
    try:
        while True:
            # Maintain connection, handle keepalive or client incoming pings if any
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning("[WebSocket Endpoint] WebSocket connection ended with exception: %s", e)
        manager.disconnect(websocket)
