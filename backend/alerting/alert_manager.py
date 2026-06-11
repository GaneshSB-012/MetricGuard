"""
==========================================================
MetricGuard — Alert Manager  (alert_manager.py)
==========================================================

Phase 14: Real-Time Alerting System
"""

import logging
import asyncio
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.incident import Incident
from backend.alerting.models import Alert
from backend.alerting.repository import AlertRepository
from backend.alerting.email_notifier import EmailNotifier
from backend.alerting.websocket_notifier import get_websocket_manager

logger = logging.getLogger("metricguard.alerting.alert_manager")


class AlertManager:
    """
    Manager class responsible for converting incidents to alerts,
    applying rules, saving to DB, and driving notification delivery.
    """

    def __init__(self) -> None:
        self.email_notifier = EmailNotifier()
        self.websocket_notifier = get_websocket_manager()

    @staticmethod
    def generate_alert_id(db: Session) -> str:
        """
        Generate the next sequential alert ID in the format ALT-XXX.
        Parses the numeric suffix from the last persisted alert_id to avoid
        relying on the DB auto-increment counter (which doesn't reset on delete).
        """
        try:
            from sqlalchemy import desc
            last_alert = db.query(Alert).order_by(desc(Alert.id)).first()
            if last_alert and last_alert.alert_id:
                suffix = last_alert.alert_id.split("-")[-1]
                return f"ALT-{int(suffix) + 1:03d}"
            return "ALT-001"
        except Exception as e:
            logger.error("[Alert Manager] Failed to generate sequential alert ID: %s", e)
            # Safe fallback
            import uuid
            return f"ALT-{uuid.uuid4().hex[:6].upper()}"

    def create_alert(self, db: Session, incident: Incident) -> Alert:
        """
        Converts an Incident into an Alert, persists it, and dispatches notifications
        if severity rules match (HIGH/CRITICAL).
        """
        logger.info("[Alert Manager] Processing incident %s...", incident.incident_id)

        # 1. Generate alert ID
        alert_id = self.generate_alert_id(db)

        # 2. Extract and format affected services
        services = [s.strip() for s in incident.impacted_services.split(",") if s.strip()]
        display_services = []
        for s in services:
            if s.lower() == "namenode":
                display_services.append("NameNode")
            elif s.lower() == "datanode":
                display_services.append("DataNode")
            else:
                display_services.append(s.title())
        services_str = ", ".join(display_services) if display_services else "System"

        # 3. Construct descriptive message
        message = f"{incident.root_cause} detected on {services_str} causing service degradation."

        # 4. Standardise severity to uppercase
        severity_upper = incident.severity.upper()

        # 5. Persist alert
        db_alert = AlertRepository.create(
            db=db,
            alert_id=alert_id,
            severity=severity_upper,
            title=incident.root_cause,
            message=message,
            affected_services=services,
        )
        logger.info("[Alert Manager] Alert %s created and persisted. Severity: %s", alert_id, severity_upper)

        # 6. Apply rules: Only notify for HIGH and CRITICAL
        if severity_upper in {"HIGH", "CRITICAL"}:
            logger.info("[Alert Manager] Rules matched. Dispatching notifications for %s...", alert_id)
            
            # Send Email
            self.email_notifier.send_alert_email(
                alert_id=alert_id,
                severity=severity_upper,
                title=incident.root_cause,
                message=message,
                affected_services=display_services,
            )

            # Send WebSocket Broadcast
            ws_payload = {
                "alert_id": alert_id,
                "severity": severity_upper,
                "title": incident.root_cause,
            }
            self._broadcast_websocket(ws_payload)
        else:
            logger.info("[Alert Manager] Alert %s severity is %s. Skipping notifications (email/websocket).", alert_id, severity_upper)

        return db_alert

    def _broadcast_websocket(self, ws_payload: dict) -> None:
        """
        Safe async helper to broadcast websocket payload to clients.
        Uses get_running_loop() which does not create a new event loop (avoids DeprecationWarning).
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.websocket_notifier.broadcast(ws_payload))
        except RuntimeError:
            # No running event loop in the current thread — fire-and-forget via asyncio.run
            try:
                asyncio.run(self.websocket_notifier.broadcast(ws_payload))
            except Exception as e:
                logger.error("[Alert Manager] Error in asyncio.run websocket broadcast: %s", e)
        except Exception as e:
            logger.error("[Alert Manager] Error during websocket broadcast dispatch: %s", e, exc_info=True)


# Singleton manager instance
_manager_instance: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """
    Access the singleton AlertManager.
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = AlertManager()
    return _manager_instance
