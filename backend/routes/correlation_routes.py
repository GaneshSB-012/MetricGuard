"""
==========================================================
MetricGuard — Correlation Routes  (correlation_routes.py)
==========================================================

Phase 10: Metric-Log Correlation Engine
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from backend.schemas import CorrelationResponse, CorrelationRunResponse
from backend.services.correlation_service import get_correlation_service
from backend.jobs.correlation_scheduler import get_scheduler
from backend.models.correlation import Correlation

logger = logging.getLogger("metricguard.routers.correlations")

router = APIRouter(prefix="/correlations", tags=["Correlations"])

# Singleton service instance
_service = get_correlation_service()


# ==========================================================
# GET /correlations/
# ==========================================================

@router.get("/", response_model=list[CorrelationResponse])
def get_correlations(db: Session = Depends(get_db)):
    """
    Retrieve all stored metric-log correlations.
    """
    try:
        correlations = _service.get_all_correlations(db)
        logger.info("Returning %d correlation records", len(correlations))
        return correlations
    except Exception as e:
        logger.error("Failed to retrieve correlations: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve correlations: {str(e)}",
        )


# ==========================================================
# GET /correlations/latest
# ==========================================================

@router.get("/latest", response_model=list[CorrelationResponse])
def get_latest_correlations(db: Session = Depends(get_db)):
    """
    Retrieve the latest 20 metric-log correlations.
    """
    try:
        correlations = _service.get_latest_correlations(db, limit=20)
        logger.info("Returning %d latest correlations", len(correlations))
        return correlations
    except Exception as e:
        logger.error("Failed to retrieve latest correlations: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve latest correlations: {str(e)}",
        )


# ==========================================================
# POST /correlations/run
# ==========================================================

@router.post("/run", response_model=CorrelationRunResponse)
def run_correlation_engine(db: Session = Depends(get_db)):
    """
    Manually trigger the correlation engine.
    """
    try:
        logger.info("Manual correlation engine trigger received.")
        count = _service.run_correlation_engine(db)

        return CorrelationRunResponse(
            status="success",
            correlations_created=count,
        )
    except Exception as e:
        logger.error("Correlation engine run failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Correlation engine run failed: {str(e)}",
        )


# ==========================================================
# GET /correlations/health
# ==========================================================

@router.get("/health")
def get_correlation_health(db: Session = Depends(get_db)):
    """
    Check the health of the correlation scheduler and database records.
    """
    db_healthy = True
    total_correlations = 0
    db_error = None
    try:
        # Count total correlations in database
        total_correlations = db.query(func.count(Correlation.id)).scalar() or 0
    except Exception as db_err:
        logger.error("Database query failed during correlation health check: %s", db_err)
        db_healthy = False
        db_error = str(db_err)

    scheduler_healthy = True
    scheduler_running = False
    last_run = None
    scheduler_error = None
    try:
        scheduler = get_scheduler()
        scheduler_status = scheduler.get_status()
        scheduler_running = scheduler_status["scheduler_running"]
        last_run = scheduler_status["last_run"]
    except Exception as sched_err:
        logger.error("Scheduler health check failed: %s", sched_err)
        scheduler_healthy = False
        scheduler_error = str(sched_err)

    # Determine overall status
    if not db_healthy:
        status = "unhealthy"
    elif not scheduler_running or not scheduler_healthy:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "scheduler_running": scheduler_running,
        "last_run": last_run,
        "total_correlations": total_correlations,
        "details": {
            "database": "healthy" if db_healthy else f"unhealthy: {db_error}",
            "scheduler": "healthy" if scheduler_healthy else f"unhealthy: {scheduler_error}",
        }
    }
