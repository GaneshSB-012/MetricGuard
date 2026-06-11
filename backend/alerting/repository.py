"""
==========================================================
MetricGuard — Alert Repository  (repository.py)
==========================================================

Phase 14: Real-Time Alerting System
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.alerting.models import Alert

logger = logging.getLogger("metricguard.alerting.repository")


class AlertRepository:
    """
    CRUD repository for database persistence of Alerts.
    """

    @staticmethod
    def create(
        db: Session,
        alert_id: str,
        severity: str,
        title: str,
        message: str,
        affected_services: List[str],
    ) -> Alert:
        """
        Persist a new alert record to the database.
        """
        services_csv = ",".join(affected_services)
        db_alert = Alert(
            alert_id=alert_id,
            severity=severity.upper(),
            title=title,
            message=message,
            affected_services=services_csv,
            status="OPEN",
        )
        try:
            db.add(db_alert)
            db.commit()
            db.refresh(db_alert)
            logger.info("[Repository] Persisted alert %s", alert_id)
            return db_alert
        except Exception as e:
            db.rollback()
            logger.error("[Repository] Failed to save alert %s: %s", alert_id, e, exc_info=True)
            raise

    @staticmethod
    def get_by_alert_id(db: Session, alert_id: str) -> Optional[Alert]:
        """
        Fetch an alert by its unique business alert_id.
        """
        try:
            return db.query(Alert).filter(Alert.alert_id == alert_id).first()
        except Exception as e:
            logger.error("[Repository] Failed to fetch alert %s: %s", alert_id, e, exc_info=True)
            return None

    @staticmethod
    def get_all(db: Session) -> List[Alert]:
        """
        Retrieve all alerts sorted by timestamp descending.
        """
        try:
            return db.query(Alert).order_by(Alert.timestamp.desc()).all()
        except Exception as e:
            logger.error("[Repository] Failed to list alerts: %s", e, exc_info=True)
            return []

    @staticmethod
    def update_status(db: Session, alert_id: str, status: str) -> Alert:
        """
        Update the status of an alert with validation.
        """
        status_upper = status.upper().strip()
        if status_upper not in {"OPEN", "ACKNOWLEDGED", "RESOLVED"}:
            raise ValueError(f"Invalid status: '{status}'. Must be OPEN, ACKNOWLEDGED, or RESOLVED.")

        db_alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
        if not db_alert:
            raise ValueError(f"Alert '{alert_id}' not found.")

        current_status = db_alert.status
        if current_status == "RESOLVED":
            raise ValueError(f"Cannot update resolved alert {alert_id}.")

        if status_upper == "ACKNOWLEDGED":
            if current_status != "OPEN":
                raise ValueError(f"Can only acknowledge alerts in OPEN status (current: {current_status}).")
        elif status_upper == "RESOLVED":
            if current_status not in {"OPEN", "ACKNOWLEDGED"}:
                raise ValueError(f"Can only resolve alerts in OPEN or ACKNOWLEDGED status (current: {current_status}).")

        db_alert.status = status_upper
        try:
            db.commit()
            db.refresh(db_alert)
            logger.info("[Repository] Updated status of %s from %s to %s", alert_id, current_status, status_upper)
            return db_alert
        except Exception as e:
            db.rollback()
            logger.error("[Repository] Failed to update status of alert %s: %s", alert_id, e, exc_info=True)
            raise
