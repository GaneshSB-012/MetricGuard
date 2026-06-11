"""
==========================================================
MetricGuard — Incident Service  (incident_service.py)
==========================================================

Phase 12: Alert Prioritization & Incident Management

Core service layer implementing:
    - Incident generation from RCA + Service Impact outputs
    - Priority assignment (P1 – P4) via rule engine
    - Severity classification (Critical / High / Medium / Low)
    - Alert deduplication (30-minute window)
    - Alert grouping (group_key based correlation)
    - Incident lifecycle management (state transitions)
    - Sequential incident ID generation (INC-000001, …)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.models.incident import Incident, VALID_STATUSES

logger = logging.getLogger("metricguard.incident.service")


# =========================================================
# LIFECYCLE TRANSITION RULES
# =========================================================

_VALID_TRANSITIONS: Dict[str, List[str]] = {
    "OPEN":          ["INVESTIGATING"],
    "INVESTIGATING": ["MITIGATED"],
    "MITIGATED":     ["RESOLVED"],
    "RESOLVED":      ["CLOSED"],
    "CLOSED":        [],
}

# =========================================================
# P1 CRITICAL ROOT CAUSES
# =========================================================

_P1_ROOT_CAUSES = {
    "disk failure",
    "node failure",
    "cluster failure",
}

# =========================================================
# DEDUPLICATION WINDOW (minutes)
# =========================================================

_DEDUP_WINDOW_MINUTES = 30


# =========================================================
# INCIDENT SERVICE
# =========================================================

class IncidentService:
    """
    Service responsible for the full incident management lifecycle.
    """

    # --------------------------------------------------
    # GROUP KEY
    # --------------------------------------------------

    @staticmethod
    def build_group_key(root_cause: str, impacted_services: List[str]) -> str:
        """
        Build a deterministic group key for deduplication and
        alert grouping.

        Format: ``root_cause|service1,service2,...``
        Services are lowered and sorted for consistency.
        """
        normalised_cause = root_cause.strip().lower()
        sorted_services = ",".join(sorted(s.strip().lower() for s in impacted_services))
        return f"{normalised_cause}|{sorted_services}"

    # --------------------------------------------------
    # INCIDENT ID GENERATION
    # --------------------------------------------------

    @staticmethod
    def generate_incident_id(db: Session) -> str:
        """
        Generate the next sequential incident ID in format INC-XXXXXX.
        """
        max_id = db.query(func.max(Incident.id)).scalar()
        next_seq = (max_id or 0) + 1
        return f"INC-{next_seq:06d}"

    # --------------------------------------------------
    # PRIORITY ASSIGNMENT (Rule Engine)
    # --------------------------------------------------

    @staticmethod
    def assign_priority(root_cause: str, impacted_services: List[str]) -> str:
        """
        Rule-based priority assignment.

        P1: namenode impacted OR root cause is Disk/Node/Cluster Failure
        P2: Multiple services impacted
        P3: Exactly one service impacted
        P4: Informational (no services impacted)
        """
        normalised_cause = root_cause.strip().lower()
        normalised_services = [s.strip().lower() for s in impacted_services]

        # P1: Critical infrastructure
        if "namenode" in normalised_services:
            return "P1"
        if normalised_cause in _P1_ROOT_CAUSES:
            return "P1"

        # P2: Multiple services
        if len(normalised_services) >= 2:
            return "P2"

        # P3: Single service
        if len(normalised_services) == 1:
            return "P3"

        # P4: Informational
        return "P4"

    # --------------------------------------------------
    # SEVERITY CLASSIFICATION
    # --------------------------------------------------

    @staticmethod
    def assign_severity(impacted_services: List[str]) -> str:
        """
        Severity based on number of impacted services.

        Critical: >= 3 services
        High:     2 services
        Medium:   1 service
        Low:      0 services (informational)
        """
        count = len(impacted_services)

        if count >= 3:
            return "Critical"
        if count == 2:
            return "High"
        if count == 1:
            return "Medium"
        return "Low"

    # --------------------------------------------------
    # DEDUPLICATION
    # --------------------------------------------------

    def find_duplicate_incident(
        self,
        db: Session,
        group_key: str,
    ) -> Optional[Incident]:
        """
        Check for an existing OPEN or INVESTIGATING incident
        with the same group key created within the last 30 minutes.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=_DEDUP_WINDOW_MINUTES)

        try:
            existing = (
                db.query(Incident)
                .filter(
                    Incident.group_key == group_key,
                    Incident.status.in_(["OPEN", "INVESTIGATING"]),
                    Incident.created_at >= cutoff,
                )
                .order_by(desc(Incident.created_at))
                .first()
            )
            return existing
        except Exception as e:
            logger.error(
                "[Incident Service] Failed to check for duplicates: %s",
                e,
                exc_info=True,
            )
            return None

    # --------------------------------------------------
    # CREATE INCIDENT
    # --------------------------------------------------

    def create_incident(
        self,
        db: Session,
        root_cause: str,
        impacted_services: List[str],
    ) -> Incident:
        """
        Create a new incident from RCA + Service Impact outputs.

        Steps:
            1. Build group key
            2. Check for duplicates
            3. If duplicate → increment alert_count, return existing
            4. Calculate priority and severity
            5. Generate incident ID
            6. Create and persist new incident
        """
        # Normalise
        normalised_services = [s.strip().lower() for s in impacted_services if s.strip()]

        # 1. Build group key
        group_key = self.build_group_key(root_cause, normalised_services)
        logger.info("[Incident Service] Group key: %s", group_key)

        # 2. Check for duplicates
        existing = self.find_duplicate_incident(db, group_key)

        if existing is not None:
            # 3. Deduplicate: increment alert count
            existing.alert_count += 1
            existing.updated_at = datetime.utcnow()
            try:
                db.commit()
                db.refresh(existing)
            except Exception as e:
                db.rollback()
                logger.error(
                    "[Incident Service] Failed to update duplicate incident: %s",
                    e,
                    exc_info=True,
                )
                raise
            logger.info(
                "[Incident Service] Duplicate found — %s alert_count=%d",
                existing.incident_id,
                existing.alert_count,
            )
            return existing

        # 4. Calculate priority and severity
        priority = self.assign_priority(root_cause, normalised_services)
        severity = self.assign_severity(normalised_services)

        # 5. Generate incident ID
        incident_id = self.generate_incident_id(db)

        # 6. Persist
        services_csv = ",".join(normalised_services)

        incident = Incident(
            incident_id=incident_id,
            root_cause=root_cause.strip(),
            impacted_services=services_csv,
            priority=priority,
            severity=severity,
            status="OPEN",
            alert_count=1,
            group_key=group_key,
        )

        try:
            db.add(incident)
            db.commit()
            db.refresh(incident)

            # Phase 14: Automatically trigger Alert Manager
            try:
                from backend.alerting.alert_manager import get_alert_manager
                alert_mgr = get_alert_manager()
                alert_mgr.create_alert(db, incident)
            except Exception as ae:
                logger.error(
                    "[Incident Service] Failed to automatically create alert for incident %s: %s",
                    incident_id,
                    ae,
                    exc_info=True,
                )
        except Exception as e:
            db.rollback()
            logger.error(
                "[Incident Service] Failed to create incident: %s",
                e,
                exc_info=True,
            )
            raise

        logger.info(
            "[Incident Service] Created %s — priority=%s, severity=%s, services=%s",
            incident_id,
            priority,
            severity,
            services_csv,
        )
        return incident

    # --------------------------------------------------
    # GET INCIDENT
    # --------------------------------------------------

    def get_incident(self, db: Session, incident_id: str) -> Optional[Incident]:
        """Retrieve a single incident by its human-readable ID."""
        try:
            return (
                db.query(Incident)
                .filter(Incident.incident_id == incident_id)
                .first()
            )
        except Exception as e:
            logger.error(
                "[Incident Service] Failed to fetch incident %s: %s",
                incident_id,
                e,
                exc_info=True,
            )
            return None

    # --------------------------------------------------
    # LIST INCIDENTS (paginated + filtered)
    # --------------------------------------------------

    def list_incidents(
        self,
        db: Session,
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Tuple[List[Incident], int]:
        """
        Return a paginated, optionally filtered list of incidents.

        Returns:
            (list_of_incidents, total_count)
        """
        try:
            query = db.query(Incident)

            if status:
                query = query.filter(Incident.status == status.upper())

            if priority:
                query = query.filter(Incident.priority == priority.upper())

            total = query.count()

            offset = (page - 1) * limit
            incidents = (
                query
                .order_by(desc(Incident.created_at))
                .offset(offset)
                .limit(limit)
                .all()
            )
            return incidents, total

        except Exception as e:
            logger.error(
                "[Incident Service] Failed to list incidents: %s",
                e,
                exc_info=True,
            )
            return [], 0

    # --------------------------------------------------
    # UPDATE STATUS (Lifecycle Management)
    # --------------------------------------------------

    def update_status(
        self,
        db: Session,
        incident_id: str,
        new_status: str,
    ) -> Incident:
        """
        Transition an incident to a new lifecycle status.

        Validates the transition against the allowed state machine:
            OPEN → INVESTIGATING → MITIGATED → RESOLVED → CLOSED

        Raises:
            ValueError: If the incident is not found or the transition
                        is invalid.
        """
        new_status = new_status.strip().upper()

        incident = self.get_incident(db, incident_id)
        if incident is None:
            raise ValueError(f"Incident '{incident_id}' not found.")

        current_status = incident.status

        # Validate transition
        allowed = _VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Invalid status transition: {current_status} → {new_status}. "
                f"Allowed transitions from {current_status}: {allowed}"
            )

        incident.status = new_status
        incident.updated_at = datetime.utcnow()

        try:
            db.commit()
            db.refresh(incident)
        except Exception as e:
            db.rollback()
            logger.error(
                "[Incident Service] Failed to update status for %s: %s",
                incident_id,
                e,
                exc_info=True,
            )
            raise

        logger.info(
            "[Incident Service] %s status changed: %s → %s",
            incident_id,
            current_status,
            new_status,
        )
        return incident


# =========================================================
# SINGLETON ACCESSOR
# =========================================================

_service_instance: Optional[IncidentService] = None


def get_incident_service() -> IncidentService:
    """Return (and lazily create) the singleton ``IncidentService``."""
    global _service_instance
    if _service_instance is None:
        _service_instance = IncidentService()
    return _service_instance
