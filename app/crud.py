import logging
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models import Metric, Anomaly
from app.schemas import MetricCreate, AnomalyCreate

# Configure service-level logging
logger = logging.getLogger("metricguard.crud")

def parse_speed_string(speed_str: str) -> float:
    """
    Converts a formatted speed string (e.g. '4.39 MB', '200 KB', '5.00 B')
    back to a numeric value in KB. If a float/int is passed directly,
    it returns it as a float.

    Args:
        speed_str: String formatted value, or float/int numeric value.

    Returns:
        float: Value in KB.
    """
    if speed_str is None:
        return 0.0
        
    if isinstance(speed_str, (int, float)):
        return float(speed_str)

    try:
        parts = speed_str.strip().split()
        if len(parts) != 2:
            # Fallback in case of raw number string
            return float(speed_str)

        value = float(parts[0])
        unit = parts[1].upper()

        if unit == "B":
            return value / 1024.0
        elif unit == "KB":
            return value
        elif unit == "MB":
            return value * 1024.0
        elif unit == "GB":
            return value * 1024.0 * 1024.0
        elif unit == "TB":
            return value * 1024.0 * 1024.0 * 1024.0
        else:
            return 0.0
    except (ValueError, IndexError) as e:
        logger.warning("Failed to parse speed string '%s': %s", speed_str, e)
        return 0.0


def insert_metric(db: Session, metric_in: MetricCreate) -> Metric:
    """
    Insert a system metric record into the database.
    """
    try:
        db_metric = Metric(
            timestamp=metric_in.timestamp,
            cpu_usage=metric_in.cpu_usage,
            memory_usage=metric_in.memory_usage,
            disk_read=metric_in.disk_read,
            disk_write=metric_in.disk_write,
            network_rx=metric_in.network_rx,
            network_tx=metric_in.network_tx
        )
        db.add(db_metric)
        db.commit()
        db.refresh(db_metric)
        logger.info("Successfully inserted metric record with ID %d", db_metric.id)
        return db_metric
    except Exception as e:
        db.rollback()
        logger.error("Failed to insert metric record: %s", e, exc_info=True)
        raise e


def get_metrics(db: Session, limit: int = 100) -> list[Metric]:
    """
    Retrieve metrics from the database, ordered by timestamp descending.
    """
    try:
        return db.query(Metric).order_by(desc(Metric.timestamp)).limit(limit).all()
    except Exception as e:
        logger.error("Failed to query metrics from database: %s", e, exc_info=True)
        raise e


def insert_anomaly(db: Session, anomaly_in: AnomalyCreate) -> Anomaly:
    """
    Insert an anomaly result into the database.
    """
    try:
        db_anomaly = Anomaly(
            timestamp=anomaly_in.timestamp,
            anomaly_score=anomaly_in.anomaly_score,
            root_cause=anomaly_in.root_cause,
            severity=anomaly_in.severity,
            detected_by=anomaly_in.detected_by,
            ml_model_version=anomaly_in.ml_model_version,
        )
        db.add(db_anomaly)
        db.commit()
        db.refresh(db_anomaly)
        logger.info("Successfully inserted anomaly record with ID %d", db_anomaly.id)
        return db_anomaly
    except Exception as e:
        db.rollback()
        logger.error("Failed to insert anomaly record: %s", e, exc_info=True)
        raise e


def get_anomalies(db: Session, limit: int = 100) -> list[Anomaly]:
    """
    Retrieve anomaly history from the database, ordered by timestamp descending.
    """
    try:
        return db.query(Anomaly).order_by(desc(Anomaly.timestamp)).limit(limit).all()
    except Exception as e:
        logger.error("Failed to query anomalies from database: %s", e, exc_info=True)
        raise e


def get_anomaly_stats(db: Session) -> dict:
    """
    Aggregate anomaly counts by root_cause and severity.
    """
    try:
        from sqlalchemy import func
        total = db.query(func.count(Anomaly.id)).scalar() or 0
        
        # Get counts by root cause
        rc_results = db.query(Anomaly.root_cause, func.count(Anomaly.id)).group_by(Anomaly.root_cause).all()
        by_root_cause = {rc or "unknown": count for rc, count in rc_results}
        
        # Get counts by severity
        sev_results = db.query(Anomaly.severity, func.count(Anomaly.id)).group_by(Anomaly.severity).all()
        by_severity = {sev: count for sev, count in sev_results}
        
        return {
            "total_anomalies": total,
            "by_root_cause": by_root_cause,
            "by_severity": by_severity
        }
    except Exception as e:
        logger.error("Failed to calculate anomaly stats: %s", e, exc_info=True)
        raise e


def get_recent_anomalies_by_type(db: Session, detected_by: str, limit: int = 100) -> list[Anomaly]:
    """
    Retrieve recent anomalies filtered by the detection method (e.g. isolation_forest, autoencoder).
    """
    try:
        return db.query(Anomaly).filter(Anomaly.detected_by.like(f"%{detected_by}%")).order_by(desc(Anomaly.timestamp)).limit(limit).all()
    except Exception as e:
        logger.error("Failed to query anomalies by type: %s", e, exc_info=True)
        raise e

