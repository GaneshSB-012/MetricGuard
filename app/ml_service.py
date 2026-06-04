"""
==========================================================
MetricGuard — ML Service Module
==========================================================

Purpose:
    Encapsulates all machine-learning inference logic into a
    singleton service that the FastAPI application loads once
    at startup.  Provides:

    1. Model loading  (Isolation Forest + Multivariate AE)
    2. Point-anomaly  detection  (Isolation Forest)
    3. Trend-anomaly  detection  (Autoencoder + sequence buffer)
    4. Root Cause Analysis (feature-wise reconstruction error)
    5. Full pipeline   orchestration (run_full_pipeline)

Thread Safety:
    The sequence buffer is protected by a threading.Lock so
    multiple concurrent requests won't corrupt the deque.

Configuration:
    Model paths default to  devops/models/  relative to the
    project root.  Override with the  ML_MODELS_DIR  env var.
"""

import os
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import joblib
import psutil
import requests

logger = logging.getLogger("metricguard.ml_service")


# =========================================================
# DATA CLASSES
# =========================================================

@dataclass
class PipelineResult:
    """Result of the full ML pipeline run."""

    # Isolation Forest
    iso_prediction: int = 1            # 1 = normal, -1 = anomaly
    iso_score: float = 0.0

    # Autoencoder
    ae_mse: float = 0.0
    ae_anomaly: bool = False
    ae_buffer_fill: int = 0
    ae_buffer_ready: bool = False

    # Combined
    is_anomaly: bool = False

    # Root Cause Analysis (populated only when is_anomaly=True)
    root_cause: Optional[str] = None
    category_errors: dict = field(default_factory=dict)
    top_contributors: list = field(default_factory=list)

    # Severity derived from scores
    severity: str = "low"
    detected_by: str = ""


# =========================================================
# CONSTANTS — Feature Mapping
# =========================================================

# The 9 features expected by the Multivariate Autoencoder
# (trained on the BitBrains dataset):
#
# Index 0 : CPU capacity provisioned [MHZ]
# Index 1 : CPU usage [MHZ]
# Index 2 : CPU usage [%]
# Index 3 : Memory capacity provisioned [KB]
# Index 4 : Memory usage [KB]
# Index 5 : Disk read throughput [KB/s]
# Index 6 : Disk write throughput [KB/s]
# Index 7 : Network received throughput [KB/s]
# Index 8 : Network transmitted throughput [KB/s]

FEATURE_CATEGORIES = [
    "CPU Usage",
    "Memory Usage",
    "Disk Usage",
    "Network Usage",
]

FEATURE_INDEX_TO_CATEGORY = {
    0: "CPU Usage",
    1: "CPU Usage",
    2: "CPU Usage",
    3: "Memory Usage",
    4: "Memory Usage",
    5: "Disk Usage",
    6: "Disk Usage",
    7: "Network Usage",
    8: "Network Usage",
}

SEQUENCE_LENGTH = 30
FEATURE_COUNT = 9
AE_THRESHOLD = 0.01
COLLECTION_INTERVAL = 5


# =========================================================
# UTILITIES
# =========================================================

def parse_speed_string(speed_str) -> float:
    """
    Convert a formatted speed string (e.g. '4.39 MB', '200 KB')
    back to a numeric value in KB.
    """
    if not speed_str or not isinstance(speed_str, str):
        return 0.0

    try:
        parts = speed_str.strip().split()
        if len(parts) != 2:
            return float(speed_str) if speed_str.replace(".", "", 1).isdigit() else 0.0

        value = float(parts[0])
        unit = parts[1].upper()

        multipliers = {"B": 1 / 1024, "KB": 1, "MB": 1024, "GB": 1024 ** 2, "TB": 1024 ** 3}
        return value * multipliers.get(unit, 0.0)
    except (ValueError, IndexError):
        return 0.0


def _get_backend_response_time(backend_url: str = "http://localhost:5000/metrics") -> float:
    """
    Measure real-time HTTP response time of the backend in ms.
    Falls back to training mean if unreachable.
    """
    health_url = backend_url.replace("/metrics", "/health")
    try:
        start = time.time()
        resp = requests.get(health_url, timeout=1.0)
        if resp.ok:
            return (time.time() - start) * 1000.0
    except Exception:
        pass
    return 2357.75  # training mean fallback


def _extract_ae_features(metrics: dict) -> np.ndarray:
    """
    Extract the 9 features required by the Multivariate Autoencoder
    from a live metric dict.

    Returns:
        np.array of shape (9,) with raw feature values.
    """
    # CPU capacity provisioned [MHZ]
    try:
        freq = psutil.cpu_freq()
        cpu_max_mhz = freq.max if freq and freq.max > 0 else 2500.0
    except Exception:
        cpu_max_mhz = 2500.0

    cpu_count = psutil.cpu_count(logical=True)
    cpu_capacity_mhz = cpu_max_mhz * cpu_count

    # CPU usage [%]
    cpu_usage_pct = metrics.get("cpu_usage", 0.0) or 0.0

    # CPU usage [MHZ]
    cpu_usage_mhz = cpu_capacity_mhz * (cpu_usage_pct / 100.0)

    # Memory capacity provisioned [KB]
    mem = psutil.virtual_memory()
    memory_capacity_kb = mem.total / 1024.0
    memory_usage_kb = mem.used / 1024.0

    # Disk throughput [KB/s]
    disk_read_kb_s = parse_speed_string(metrics.get("disk_read_speed", "0.00 B")) / COLLECTION_INTERVAL
    disk_write_kb_s = parse_speed_string(metrics.get("disk_write_speed", "0.00 B")) / COLLECTION_INTERVAL

    # Network throughput [KB/s]
    net_recv_kb_s = parse_speed_string(metrics.get("network_download_speed", "0.00 B")) / COLLECTION_INTERVAL
    net_trans_kb_s = parse_speed_string(metrics.get("network_upload_speed", "0.00 B")) / COLLECTION_INTERVAL

    return np.array([
        cpu_capacity_mhz,
        cpu_usage_mhz,
        cpu_usage_pct,
        memory_capacity_kb,
        memory_usage_kb,
        disk_read_kb_s,
        disk_write_kb_s,
        net_recv_kb_s,
        net_trans_kb_s,
    ])


def _determine_severity(iso_prediction: int, ae_mse: float, ae_anomaly: bool) -> str:
    """
    Derive severity from model outputs.
    """
    if iso_prediction == -1 and ae_anomaly:
        return "critical"
    if ae_anomaly and ae_mse > AE_THRESHOLD * 5:
        return "critical"
    if ae_anomaly or iso_prediction == -1:
        return "warning"
    return "low"


# =========================================================
# ML SERVICE — Singleton
# =========================================================

class MLService:
    """
    Singleton service that holds loaded ML models and exposes
    inference methods.  Initialised once at FastAPI startup.
    """

    _instance: Optional["MLService"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    # --------------------------------------------------
    # Initialisation
    # --------------------------------------------------

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.isolation_forest = None
        self.iso_scaler = None
        self.ae_model = None
        self.ae_scaler = None

        self.models_loaded = False
        self.model_load_error: Optional[str] = None

        self._sequence_buffer: deque = deque(maxlen=SEQUENCE_LENGTH)
        self._buffer_lock = threading.Lock()

        logger.info("MLService singleton created (models not yet loaded)")

    # --------------------------------------------------
    # Model Loading
    # --------------------------------------------------

    def load_models(self, models_dir: Optional[str] = None) -> bool:
        """
        Load all ML model artefacts from disk.

        Args:
            models_dir: Path to the models root directory.
                        Defaults to ``devops/models`` relative
                        to the project root, or the value of
                        the ``ML_MODELS_DIR`` environment variable.

        Returns:
            True if all models loaded successfully.
        """
        if models_dir is None:
            models_dir = os.getenv(
                "ML_MODELS_DIR",
                os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "devops", "models",
                ),
            )

        logger.info("Loading ML models from: %s", models_dir)

        iso_model_path = os.path.join(models_dir, "isolation_forest", "isolation_forest_model.pkl")
        iso_scaler_path = os.path.join(models_dir, "isolation_forest", "scaler.pkl")
        ae_model_path = os.path.join(models_dir, "encoder", "metricguard_phase4.h5")
        ae_scaler_path = os.path.join(models_dir, "encoder", "bitbrains_scaler.pkl")

        try:
            # --- Isolation Forest ---
            logger.info("Loading Isolation Forest …")
            self.isolation_forest = joblib.load(iso_model_path)
            self.iso_scaler = joblib.load(iso_scaler_path)
            logger.info("Isolation Forest loaded ✓")

            # --- Multivariate Autoencoder ---
            logger.info("Loading Multivariate Autoencoder …")
            import tensorflow as tf
            self.ae_scaler = joblib.load(ae_scaler_path)
            self.ae_model = tf.keras.models.load_model(ae_model_path, compile=False)
            logger.info(
                "Autoencoder loaded ✓ — Input: %s, Output: %s",
                self.ae_model.input_shape,
                self.ae_model.output_shape,
            )

            self.models_loaded = True
            self.model_load_error = None
            logger.info("All ML models loaded successfully")
            return True

        except FileNotFoundError as e:
            self.model_load_error = f"Model file not found: {e}"
            logger.error(self.model_load_error)
        except Exception as e:
            self.model_load_error = f"Failed to load models: {e}"
            logger.error(self.model_load_error, exc_info=True)

        self.models_loaded = False
        return False

    # --------------------------------------------------
    # Isolation Forest Inference
    # --------------------------------------------------

    def predict_isolation_forest(
        self,
        cpu_usage_pct: float,
        memory_usage_mb: float,
        response_time_ms: float,
    ) -> tuple[int, float]:
        """
        Run Isolation Forest point-anomaly detection.

        Args:
            cpu_usage_pct:    CPU usage percentage (0-100).
            memory_usage_mb:  Virtual memory used in MB.
            response_time_ms: Backend response time in ms.

        Returns:
            (prediction, anomaly_score)
            prediction = 1 (normal) or -1 (anomaly).
        """
        if not self.models_loaded:
            logger.warning("Models not loaded — returning default normal prediction")
            return (1, 0.0)

        features = np.array([[response_time_ms, cpu_usage_pct, memory_usage_mb]])
        scaled = self.iso_scaler.transform(features)

        prediction = int(self.isolation_forest.predict(scaled)[0])
        score = float(abs(self.isolation_forest.score_samples(scaled)[0]))

        logger.debug("Isolation Forest: prediction=%d, score=%.4f", prediction, score)
        return (prediction, score)

    # --------------------------------------------------
    # Autoencoder Inference
    # --------------------------------------------------

    def predict_autoencoder(
        self, feature_vector_9d: np.ndarray
    ) -> tuple[float, bool, int]:
        """
        Buffer a 9-feature vector and, when the sequence buffer is full,
        run the autoencoder for trend-anomaly detection.

        Args:
            feature_vector_9d: np.array of shape (9,).

        Returns:
            (mse, is_anomaly, buffer_fill)
        """
        if not self.models_loaded:
            logger.warning("Models not loaded — skipping autoencoder")
            return (0.0, False, 0)

        # Scale with the BitBrains MinMaxScaler
        scaled = self.ae_scaler.transform(feature_vector_9d.reshape(1, -1))[0]

        with self._buffer_lock:
            self._sequence_buffer.append(scaled)
            buffer_fill = len(self._sequence_buffer)

        if buffer_fill < SEQUENCE_LENGTH:
            logger.debug("Autoencoder buffer: %d/%d (waiting)", buffer_fill, SEQUENCE_LENGTH)
            return (0.0, False, buffer_fill)

        # Build the sequence tensor
        with self._buffer_lock:
            sequence = np.array(self._sequence_buffer)

        sequence = sequence.reshape(1, SEQUENCE_LENGTH, FEATURE_COUNT)
        reconstructed = self.ae_model.predict(sequence, verbose=0)

        mse = float(np.mean(np.square(sequence - reconstructed)))
        is_anomaly = mse > AE_THRESHOLD

        logger.debug("Autoencoder MSE: %.6f | anomaly=%s", mse, is_anomaly)
        return (mse, is_anomaly, buffer_fill)

    # --------------------------------------------------
    # Root Cause Analysis
    # --------------------------------------------------

    def perform_rca(
        self,
        actual_scaled: np.ndarray,
        reconstructed_scaled: np.ndarray,
    ) -> tuple[str, dict, list]:
        """
        Compute feature-wise reconstruction errors and map them
        to metric categories.

        Args:
            actual_scaled:        np.array (1, SEQUENCE_LENGTH, 9)
            reconstructed_scaled: np.array (1, SEQUENCE_LENGTH, 9)

        Returns:
            (root_cause, category_errors, top_contributors)
        """
        feature_error = np.mean(np.square(actual_scaled - reconstructed_scaled), axis=(0, 1))

        category_errors = {}
        for cat in FEATURE_CATEGORIES:
            indices = [i for i, c in FEATURE_INDEX_TO_CATEGORY.items() if c == cat]
            category_errors[cat] = float(np.mean(feature_error[indices]))

        root_cause = max(category_errors, key=category_errors.get)

        top_contributors = sorted(
            [{"metric": cat, "error": round(err, 6)} for cat, err in category_errors.items()],
            key=lambda x: x["error"],
            reverse=True,
        )

        return (root_cause, category_errors, top_contributors)

    # --------------------------------------------------
    # Full Pipeline Orchestration
    # --------------------------------------------------

    def run_full_pipeline(self, metrics_dict: dict) -> PipelineResult:
        """
        Run the complete ML pipeline for a single metrics snapshot.

        Steps:
            1. Isolation Forest point-anomaly detection
            2. Extract 9-D AE features and buffer
            3. Autoencoder trend detection (if buffer full)
            4. RCA (if anomaly detected)

        Args:
            metrics_dict: Raw metric dict with keys matching the
                          collector output (cpu_usage, ram_usage,
                          disk_read_speed, etc.).

        Returns:
            PipelineResult dataclass.
        """
        if not self.models_loaded:
            logger.warning("ML models not loaded — pipeline skipped")
            return PipelineResult()

        result = PipelineResult()

        # ----- Step 1: Isolation Forest -----
        cpu_pct = metrics_dict.get("cpu_usage", 0.0) or 0.0
        memory_mb = psutil.virtual_memory().used / (1024 * 1024)
        response_ms = _get_backend_response_time()

        iso_pred, iso_score = self.predict_isolation_forest(cpu_pct, memory_mb, response_ms)
        result.iso_prediction = iso_pred
        result.iso_score = iso_score

        # ----- Step 2: Extract AE features & buffer -----
        ae_features = _extract_ae_features(metrics_dict)
        ae_mse, ae_anomaly, buf_fill = self.predict_autoencoder(ae_features)

        result.ae_mse = ae_mse
        result.ae_anomaly = ae_anomaly
        result.ae_buffer_fill = buf_fill
        result.ae_buffer_ready = buf_fill >= SEQUENCE_LENGTH

        # ----- Step 3: Combined decision -----
        result.is_anomaly = (iso_pred == -1) or ae_anomaly
        result.severity = _determine_severity(iso_pred, ae_mse, ae_anomaly)

        # Determine who detected it
        detectors = []
        if iso_pred == -1:
            detectors.append("isolation_forest")
        if ae_anomaly:
            detectors.append("autoencoder")
        result.detected_by = "+".join(detectors) if detectors else "none"

        # ----- Step 4: RCA (only when anomaly + buffer ready) -----
        if result.is_anomaly and result.ae_buffer_ready:
            with self._buffer_lock:
                sequence = np.array(self._sequence_buffer)

            sequence_3d = sequence.reshape(1, SEQUENCE_LENGTH, FEATURE_COUNT)
            reconstructed = self.ae_model.predict(sequence_3d, verbose=0)

            root_cause, cat_errors, top_contribs = self.perform_rca(sequence_3d, reconstructed)
            result.root_cause = root_cause
            result.category_errors = cat_errors
            result.top_contributors = top_contribs
        elif result.is_anomaly:
            # Buffer not ready yet — provide partial info
            result.root_cause = "pending_buffer_fill"

        logger.info(
            "Pipeline result: anomaly=%s severity=%s detected_by=%s root_cause=%s",
            result.is_anomaly, result.severity, result.detected_by, result.root_cause,
        )

        return result

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    def get_status(self) -> dict:
        """Return current status of the ML service."""
        with self._buffer_lock:
            buf_fill = len(self._sequence_buffer)

        return {
            "models_loaded": self.models_loaded,
            "model_load_error": self.model_load_error,
            "sequence_buffer_fill": buf_fill,
            "sequence_buffer_capacity": SEQUENCE_LENGTH,
            "buffer_ready": buf_fill >= SEQUENCE_LENGTH,
            "ae_threshold": AE_THRESHOLD,
        }


# =========================================================
# MODULE-LEVEL ACCESSOR
# =========================================================

def get_ml_service() -> MLService:
    """Return the MLService singleton instance."""
    return MLService()
