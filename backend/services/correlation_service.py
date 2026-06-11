"""
==========================================================
MetricGuard — Correlation Service  (correlation_service.py)
==========================================================

Phase 10: Metric-Log Correlation Engine
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Anomaly, Log
from backend.models.correlation import Correlation
from backend.utils.cause_mapper import infer_root_cause
from backend.services.log_anomaly_service import get_log_anomaly_service

logger = logging.getLogger("metricguard.correlation.service")

# Severity mapping for scoring comparison
_LOG_LEVEL_TO_SEVERITY = {
    "ERROR":    "warning",
    "CRITICAL": "critical",
    "WARNING":  "low",
}

_TIME_WINDOW_SECONDS = 60


class CorrelationService:
    """
    Service that correlates metric anomalies with predicted log anomalies.
    """

    def get_recent_metric_anomalies(
        self,
        db: Session,
        minutes: int = 5,
    ) -> List[Anomaly]:
        """
        Fetch metric anomalies from the last *minutes* minutes.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        try:
            anomalies = (
                db.query(Anomaly)
                .filter(Anomaly.timestamp >= cutoff)
                .order_by(desc(Anomaly.timestamp))
                .all()
            )
            return anomalies
        except Exception as e:
            logger.error("[Correlation Engine] Failed to fetch metric anomalies: %s", e, exc_info=True)
            return []

    def get_recent_log_anomalies(
        self,
        db: Session,
        minutes: int = 5,
    ) -> List[Log]:
        """
        Fetch predicted log anomalies from the last *minutes* minutes using LogAnomalyService.
        """
        try:
            log_service = get_log_anomaly_service()
            return log_service.get_recent_log_anomalies(db, minutes)
        except Exception as e:
            logger.error("[Correlation Engine] Failed to fetch log anomalies: %s", e, exc_info=True)
            return []

    def calculate_correlation_score(
        self,
        metric_anomaly: Anomaly,
        log_anomaly: Log,
        inferred_cause: str = "Unknown",
    ) -> Dict[str, float]:
        """
        Calculate correlation score based on Task 6 requirements:
        - Time Match = 0.30 (if time_diff <= 60s)
        - Severity Match = 0.20 (if severity matches mapped level)
        - Host Match = 0.20 (if host_name matches)
        - Service Match = 0.20 (if service context matches)
        - Keyword Match = 0.10 (if inferred cause is not Unknown)

        Returns:
            {"correlation_score": float, "confidence": float}
        """
        score = 0.0

        # 1. Time Match (0.30)
        time_diff = abs((metric_anomaly.timestamp - log_anomaly.timestamp).total_seconds())
        if time_diff <= _TIME_WINDOW_SECONDS:
            score += 0.30

        # 2. Severity Match (0.20)
        mapped_severity = _LOG_LEVEL_TO_SEVERITY.get(log_anomaly.level, "")
        if (
            metric_anomaly.severity
            and mapped_severity
            and metric_anomaly.severity.lower() == mapped_severity.lower()
        ):
            score += 0.20

        # 3. Host Match (0.20)
        log_host = getattr(log_anomaly, "host_name", None)
        metric_host = getattr(metric_anomaly, "host_name", None)
        if log_host == metric_host:
            # Both None or matching hosts
            score += 0.20

        # 4. Service Match (0.20)
        log_service = getattr(log_anomaly, "service_name", None)
        metric_service = getattr(metric_anomaly, "service_name", None)
        if log_service and metric_service and log_service == metric_service:
            score += 0.20
        elif not log_service and not metric_service:
            # Default fallback when service contexts are absent/identical
            score += 0.20
        elif log_service:
            # Contextual service parsing (e.g. database-service matches database causes)
            root_cause_str = (metric_anomaly.root_cause or "").lower()
            if "database" in log_service.lower() and any(k in root_cause_str for k in ["database", "deadlock", "sql"]):
                score += 0.20
            elif "application" in log_service.lower() and any(k in root_cause_str for k in ["cpu", "memory", "jvm"]):
                score += 0.20

        # 5. Keyword Match (0.10)
        if inferred_cause != "Unknown":
            score += 0.10

        score = round(score, 2)
        confidence = round(score * 100, 2)

        return {
            "correlation_score": score,
            "confidence": confidence,
        }

    def check_duplicate(self, db: Session, metric_id: int, log_id: int) -> bool:
        """
        Verify if a correlation record already exists.
        """
        try:
            return (
                db.query(Correlation)
                .filter(
                    Correlation.metric_anomaly_id == metric_id,
                    Correlation.log_anomaly_id == log_id,
                )
                .first()
                is not None
            )
        except Exception as e:
            logger.error("[Correlation Engine] Error checking duplicate: %s", e)
            return False

    def create_correlation(
        self,
        metric_anomaly: Anomaly,
        log_anomaly: Log,
        score_info: Dict[str, float],
        inferred_cause: str,
    ) -> Dict[str, Any]:
        """
        Build correlation data dictionary.
        """
        # Phase 11 Preparation columns
        service_name = getattr(log_anomaly, "service_name", None) or getattr(metric_anomaly, "service_name", None)
        host_name = getattr(log_anomaly, "host_name", None) or getattr(metric_anomaly, "host_name", None)
        container_id = getattr(log_anomaly, "container_id", None) or getattr(metric_anomaly, "container_id", None)

        return {
            "metric_anomaly_id": metric_anomaly.id,
            "log_anomaly_id":    log_anomaly.id,
            "correlation_score": score_info["correlation_score"],
            "inferred_cause":    inferred_cause,
            "confidence":        score_info["confidence"],
            "service_name":      service_name,
            "host_name":         host_name,
            "container_id":      container_id,
        }

    def store_correlation(
        self,
        db: Session,
        correlation_data: Dict[str, Any],
    ) -> Correlation:
        """
        Store correlation record.
        """
        try:
            db_corr = Correlation(
                metric_anomaly_id=correlation_data["metric_anomaly_id"],
                log_anomaly_id=correlation_data["log_anomaly_id"],
                correlation_score=correlation_data["correlation_score"],
                inferred_cause=correlation_data["inferred_cause"],
                confidence=correlation_data["confidence"],
                service_name=correlation_data.get("service_name"),
                host_name=correlation_data.get("host_name"),
                container_id=correlation_data.get("container_id"),
            )
            db.add(db_corr)
            db.commit()
            db.refresh(db_corr)

            # Automatically run Service Impact & Incident Creation for the new correlation
            try:
                from backend.service_impact.impact_analyzer import get_impact_analyzer
                from backend.services.incident_service import get_incident_service
                
                analyzer = get_impact_analyzer()
                incident_service = get_incident_service()
                
                affected = db_corr.service_name
                if not affected or not analyzer._graph.service_exists(affected.strip().lower()):
                    # Fallback to a default known registered service (e.g. namenode)
                    affected = "namenode"
                
                impact_res = analyzer.analyze(
                    root_cause=db_corr.inferred_cause or "Unknown",
                    affected_service=affected,
                    confidence=db_corr.correlation_score,
                )
                
                incident_service.create_incident(
                    db=db,
                    root_cause=impact_res["root_cause"],
                    impacted_services=impact_res["impacted_services"],
                )
            except Exception as auto_err:
                logger.error(
                    "[Correlation Engine] Automatic Service Impact/Incident generation failed: %s",
                    auto_err,
                    exc_info=True,
                )

            return db_corr
        except Exception as e:
            db.rollback()
            logger.error("[Correlation Engine] Failed to store correlation: %s", e, exc_info=True)
            raise

    def run_correlation_engine(
        self,
        db: Session,
        minutes: int = 5,
    ) -> int:
        """
        Execute the complete correlation pipeline with structured observability logs.
        """
        logger.info("[Correlation Engine] Correlation started")

        metric_anomalies = self.get_recent_metric_anomalies(db, minutes)
        log_anomalies = self.get_recent_log_anomalies(db, minutes)

        if not metric_anomalies:
            logger.info("[Correlation Engine] No metric anomalies found.")
            logger.info("[Correlation Engine] Correlation completed")
            return 0

        if not log_anomalies:
            logger.info("[Correlation Engine] No log anomalies found.")
            logger.info("[Correlation Engine] Correlation completed")
            return 0

        correlations_created = 0

        for metric_anomaly in metric_anomalies:
            logger.info("[Correlation Engine] Metric anomaly loaded")
            
            for log_anomaly in log_anomalies:
                logger.info("[Correlation Engine] Log anomaly loaded")

                # Time window filtering
                time_diff = abs((metric_anomaly.timestamp - log_anomaly.timestamp).total_seconds())
                if time_diff > _TIME_WINDOW_SECONDS:
                    continue

                # Infer cause
                cause_info = infer_root_cause(log_anomaly.message)
                inferred_cause = cause_info.get("cause", "Unknown")
                logger.info("[Correlation Engine] Cause inferred")

                # Calculate score
                score_info = self.calculate_correlation_score(
                    metric_anomaly, log_anomaly, inferred_cause
                )
                logger.info("[Correlation Engine] Score calculated")

                # Reject score <= 0
                if score_info["correlation_score"] <= 0:
                    continue

                # Duplicate check
                if self.check_duplicate(db, metric_anomaly.id, log_anomaly.id):
                    logger.info("[Correlation Engine] Duplicate skipped")
                    continue

                # Build & store
                corr_data = self.create_correlation(
                    metric_anomaly, log_anomaly, score_info, inferred_cause
                )
                try:
                    self.store_correlation(db, corr_data)
                    logger.info("[Correlation Engine] Correlation stored")
                    correlations_created += 1
                except Exception:
                    continue

        logger.info("[Correlation Engine] Correlation completed")
        return correlations_created

    def get_all_correlations(self, db: Session) -> List[Correlation]:
        """
        Get all correlations.
        """
        try:
            return db.query(Correlation).order_by(desc(Correlation.created_at)).all()
        except Exception as e:
            logger.error("[Correlation Engine] Failed to query correlations: %s", e, exc_info=True)
            return []

    def get_latest_correlations(
        self,
        db: Session,
        limit: int = 20,
    ) -> List[Correlation]:
        """
        Get latest correlations.
        """
        try:
            return (
                db.query(Correlation)
                .order_by(desc(Correlation.created_at))
                .limit(limit)
                .all()
            )
        except Exception as e:
            logger.error("[Correlation Engine] Failed to query latest correlations: %s", e, exc_info=True)
            return []


# Singleton instance
_service_instance: Optional[CorrelationService] = None

def get_correlation_service() -> CorrelationService:
    global _service_instance
    if _service_instance is None:
        _service_instance = CorrelationService()
    return _service_instance
