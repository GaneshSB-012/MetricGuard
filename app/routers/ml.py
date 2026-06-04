import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    MLPredictionRequest,
    MLPredictionResponse,
    RCAStatsResponse,
    AnomalyCreate,
)
from app.crud import insert_anomaly, get_anomaly_stats
from app.ml_service import get_ml_service, MLService

logger = logging.getLogger("metricguard.routers.ml")

router = APIRouter(prefix="/ml", tags=["ML Inference & RCA"])


@router.post("/predict", response_model=MLPredictionResponse)
def predict_metrics(
    payload: MLPredictionRequest,
    db: Session = Depends(get_db),
    ml_service: MLService = Depends(get_ml_service),
):
    """
    Run the full ML pipeline on a metrics payload, returning predictions and performing RCA if needed.
    If an anomaly is detected, it is automatically stored in the database.
    """
    if not ml_service.models_loaded:
        raise HTTPException(status_code=503, detail="ML models are not loaded.")

    try:
        # Convert payload to dict
        payload_dict = payload.model_dump()
        result = ml_service.run_full_pipeline(payload_dict)

        # Parse timestamp
        try:
            ts = datetime.strptime(payload.timestamp, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            ts = datetime.now()

        # If anomaly detected, store in database
        if result.is_anomaly:
            # Score can be ae_mse or iso_score
            score = result.ae_mse if result.ae_anomaly else result.iso_score
            anomaly_in = AnomalyCreate(
                timestamp=ts,
                anomaly_score=score,
                root_cause=result.root_cause,
                severity=result.severity,
                detected_by=result.detected_by,
                ml_model_version="1.0.0",
            )
            insert_anomaly(db, anomaly_in)

        return MLPredictionResponse(
            is_anomaly=result.is_anomaly,
            detected_by=result.detected_by,
            severity=result.severity,
            iso_prediction=result.iso_prediction,
            iso_score=result.iso_score,
            ae_mse=result.ae_mse,
            ae_anomaly=result.ae_anomaly,
            ae_buffer_fill=result.ae_buffer_fill,
            ae_buffer_ready=result.ae_buffer_ready,
            root_cause=result.root_cause,
            category_errors=result.category_errors,
            top_contributors=result.top_contributors,
        )
    except Exception as e:
        logger.error("Failed running prediction: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to run prediction: {str(e)}")


@router.get("/rca/stats", response_model=RCAStatsResponse)
def read_rca_stats(db: Session = Depends(get_db)):
    """
    Retrieve aggregated Root Cause Analysis statistics, counting anomalies by root cause and severity.
    """
    try:
        stats = get_anomaly_stats(db)
        return stats
    except Exception as e:
        logger.error("Failed to retrieve RCA stats: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve RCA stats: {str(e)}")


@router.get("/status")
def read_ml_status(ml_service: MLService = Depends(get_ml_service)):
    """
    Retrieve the current status of the ML service, including loaded models and buffer fill levels.
    """
    return ml_service.get_status()
