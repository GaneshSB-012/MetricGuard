"""
==========================================================
MetricGuard — Log Anomaly Service  (log_anomaly_service.py)
==========================================================

Phase 10: Metric-Log Correlation Engine
"""

from __future__ import annotations

import os
import logging
import joblib
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from sklearn.feature_extraction.text import TfidfVectorizer
from app.models import Log

logger = logging.getLogger("metricguard.correlation.log_anomaly_service")

# Predefined 29-word vocabulary matching simulated log keywords
VOCABULARY = [
    "database", "connection", "timeout", "refused", "memory",
    "disk", "full", "service", "unavailable", "network",
    "deadlock", "replication", "ssl", "certificate", "upstream",
    "rate", "limit", "pool", "failed", "error",
    "critical", "crash", "fatal", "slow", "latency",
    "gc", "cpu", "worker", "health"
]


class LogAnomalyService:
    """
    Service responsible for loading the log anomaly model, running inference,
    and retrieving predicted log anomalies.
    """

    def __init__(self, model_path: Optional[str] = None):
        if model_path is None:
            # Resolve model path relative to project root
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_path = os.path.join(
                base_dir, "devops", "models", "isolation_forest_log", "metricguard_log_model.pkl"
            )

        self.model_path = model_path
        self.model = None
        self.vectorizer = None

    def load_model(self) -> bool:
        """
        Load the pickled IsolationForest model and initialize the TF-IDF vectorizer.
        """
        try:
            logger.info("[Log Anomaly Service] Loading model from: %s", self.model_path)
            self.model = joblib.load(self.model_path)
            
            # Initialize TF-IDF Vectorizer with fixed 29-word vocabulary
            self.vectorizer = TfidfVectorizer(
                vocabulary=VOCABULARY,
                token_pattern=r"(?u)\b\w+\b",
                lowercase=True
            )
            # Dummy fit to initialize vectorizer internal state
            self.vectorizer.fit(VOCABULARY)
            
            logger.info("[Log Anomaly Service] Model and Vectorizer loaded successfully.")
            return True
        except Exception as e:
            logger.error("[Log Anomaly Service] Failed to load log anomaly model: %s", e, exc_info=True)
            return False

    def predict_log_anomaly(self, message: str) -> bool:
        """
        Run the IsolationForest model to predict if a log message is anomalous.
        Returns:
            True if anomaly (model output -1), False otherwise (model output 1).
        """
        if self.model is None or self.vectorizer is None:
            logger.warning("[Log Anomaly Service] Model not loaded. Returning False (normal).")
            return False

        try:
            # Transform message into 29-dimensional TF-IDF vector
            X = self.vectorizer.transform([message])
            # Construct DataFrame with columns E1..E29 to avoid feature name mismatch warning/error
            df = pd.DataFrame(X.toarray(), columns=[f"E{i}" for i in range(1, 30)])

            # Predict: 1 = normal, -1 = anomaly
            prediction = self.model.predict(df)[0]
            is_anomaly = (prediction == -1)

            logger.debug("[Log Anomaly Service] Prediction for message '%.50s': %d (anomaly=%s)", 
                         message, prediction, is_anomaly)
            return is_anomaly
        except Exception as e:
            logger.error("[Log Anomaly Service] Inference failed for message '%.50s': %s", message, e)
            return False

    def get_recent_log_anomalies(self, db: Session, minutes: int = 5) -> List[Log]:
        """
        Fetch logs from the database and filter for predicted anomalies.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        try:
            # Fetch all logs in time window
            logs = (
                db.query(Log)
                .filter(Log.timestamp >= cutoff)
                .order_by(desc(Log.timestamp))
                .all()
            )
            
            anomalous_logs = []
            for log in logs:
                if self.predict_log_anomaly(log.message):
                    anomalous_logs.append(log)

            logger.info("[Log Anomaly Service] Found %d anomalies out of %d logs (last %d min)",
                        len(anomalous_logs), len(logs), minutes)
            return anomalous_logs
        except Exception as e:
            logger.error("[Log Anomaly Service] Failed to retrieve recent log anomalies: %s", e, exc_info=True)
            return []


# Singleton accessor
_service_instance: Optional[LogAnomalyService] = None

def get_log_anomaly_service() -> LogAnomalyService:
    global _service_instance
    if _service_instance is None:
        _service_instance = LogAnomalyService()
        _service_instance.load_model()
    return _service_instance
