"""
==========================================================
MetricGuard — Correlation Engine Tests (test_correlation.py)
==========================================================

Phase 10: Metric-Log Correlation Engine
"""

import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

# Add workspace root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load dotenv first so real config takes precedence
from dotenv import load_dotenv
load_dotenv()

# Set fallback env vars so app.database module-level validation passes
# (tests use in-memory SQLite, these are never used for real connections)
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")

from app.database import Base
from app.models import Anomaly, Log
from backend.models.correlation import Correlation
from backend.services.correlation_service import CorrelationService
from backend.services.log_anomaly_service import LogAnomalyService
from backend.jobs.correlation_scheduler import CorrelationScheduler


# ==========================================================
# SQLITE IN-MEMORY TEST DATABASE SETUP
# ==========================================================

@pytest.fixture(name="db_session")
def fixture_db_session():
    """Provides a clean in-memory SQLite database session for testing ORM constraints."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # Create all tables (metrics, anomalies, logs, correlations) in memory
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ==========================================================
# TEST 1: Cause Mapper
# ==========================================================

class TestCauseMapper:
    """Tests for backend.utils.cause_mapper.infer_root_cause()"""

    def test_database_timeout_match(self):
        from backend.utils.cause_mapper import infer_root_cause
        result = infer_root_cause("Database timeout while processing payment")
        assert result["cause"] == "Database Bottleneck"
        assert result["confidence"] == 0.9  # multi-word → high confidence

    def test_connection_refused_match(self):
        from backend.utils.cause_mapper import infer_root_cause
        result = infer_root_cause("Connection refused from 192.168.1.100:3306")
        assert result["cause"] == "Database Connectivity Issue"
        assert result["confidence"] == 0.9

    def test_out_of_memory_match(self):
        from backend.utils.cause_mapper import infer_root_cause
        result = infer_root_cause("Out of memory: Java heap space exceeded 2048MB limit")
        assert result["cause"] == "Memory Exhaustion"
        assert result["confidence"] == 0.9

    def test_disk_full_match(self):
        from backend.utils.cause_mapper import infer_root_cause
        result = infer_root_cause("Data directory full: cannot write to /var/lib/mysql/")
        assert result["cause"] == "Disk Saturation"
        assert result["confidence"] == 0.9

    def test_single_keyword_deadlock(self):
        from backend.utils.cause_mapper import infer_root_cause
        result = infer_root_cause("Deadlock found when trying to get lock")
        assert result["cause"] == "Database Deadlock"
        assert result["confidence"] == 0.7  # single-word → medium confidence

    def test_no_match_returns_unknown(self):
        from backend.utils.cause_mapper import infer_root_cause
        result = infer_root_cause("Application started successfully on port 8080")
        assert result["cause"] == "Unknown"
        assert result["confidence"] == 0.0


# ==========================================================
# TEST 2: Correlation Service — Scoring Algorithm
# ==========================================================

class TestCorrelationScoring:
    """Tests for CorrelationService.calculate_correlation_score() with the updated weights."""

    class MockAnomaly:
        def __init__(self, timestamp, severity, root_cause="CPU Usage", host_name=None, service_name=None):
            self.timestamp = timestamp
            self.severity = severity
            self.root_cause = root_cause
            self.host_name = host_name
            self.service_name = service_name

    class MockLog:
        def __init__(self, timestamp, level, message, host_name=None, service_name=None):
            self.timestamp = timestamp
            self.level = level
            self.message = message
            self.host_name = host_name
            self.service_name = service_name

    def test_perfect_score(self):
        """All 5 factors match → score = 1.0"""
        service = CorrelationService()
        now = datetime.utcnow()
        metric = self.MockAnomaly(now, "warning", root_cause="CPU Usage", host_name="node-01", service_name="app-service")
        log = self.MockLog(now - timedelta(seconds=10), "ERROR", "Database timeout", host_name="node-01", service_name="app-service")
        
        # Time: within 60s -> 0.30
        # Severity: warning == warning (mapped ERROR) -> 0.20
        # Host: 'node-01' == 'node-01' -> 0.20
        # Service: 'app-service' == 'app-service' -> 0.20
        # Keyword Match: 'Database timeout' -> 'database timeout' in CAUSE_MAP -> 0.10
        score_info = service.calculate_correlation_score(metric, log, inferred_cause="Database Bottleneck")
        assert score_info["correlation_score"] == 1.0
        assert score_info["confidence"] == 100.0

    def test_contextual_service_matching(self):
        """Service Match logic should recognize database causes for database log service."""
        service = CorrelationService()
        now = datetime.utcnow()
        metric = self.MockAnomaly(now, "critical", root_cause="database bottleneck", host_name="node-01", service_name=None)
        log = self.MockLog(now, "CRITICAL", "Database deadlock", host_name="node-01", service_name="database-service")
        
        # Time: matches -> 0.30
        # Severity: critical == critical (mapped CRITICAL) -> 0.20
        # Host: matches -> 0.20
        # Service: log_service is database-service and root_cause has database -> 0.20
        # Keyword: matches -> 0.10
        score_info = service.calculate_correlation_score(metric, log, inferred_cause="Database Deadlock")
        assert score_info["correlation_score"] == 1.0

    def test_time_only_and_null_defaults(self):
        """Ensure default scores apply correctly when host/service are null (they are equal)."""
        service = CorrelationService()
        now = datetime.utcnow()
        metric = self.MockAnomaly(now, "low", root_cause="Unknown", host_name=None, service_name=None)
        log = self.MockLog(now, "INFO", "Random message", host_name=None, service_name=None)
        
        # Time: matches -> 0.30
        # Severity: low != low (mapped INFO is empty) -> 0.0
        # Host: both None -> 0.20
        # Service: both None -> 0.20
        # Keyword: no match -> 0.0
        score_info = service.calculate_correlation_score(metric, log, inferred_cause="Unknown")
        assert score_info["correlation_score"] == 0.70


# ==========================================================
# TEST 3: ORM Model & Constraints (In-Memory Database)
# ==========================================================

class TestCorrelationORM:
    """Verifies SQLAlchemy model constraints and duplicate prevention."""

    def test_unique_constraint_enforced(self, db_session):
        # Insert raw anomalies and logs first to satisfy Foreign Key constraints
        anomaly = Anomaly(timestamp=datetime.utcnow(), anomaly_score=0.85, severity="warning", detected_by="test", metric_id=1)
        log = Log(timestamp=datetime.utcnow(), level="ERROR", message="Timeout occurred", service_name="test")
        db_session.add_all([anomaly, log])
        db_session.commit()

        # Create first correlation record
        c1 = Correlation(
            metric_anomaly_id=anomaly.id,
            log_anomaly_id=log.id,
            correlation_score=0.95,
            confidence=95.0,
            service_name="test-service",
            host_name="node-01",
            container_id="c-123"
        )
        db_session.add(c1)
        db_session.commit()

        # Attempt to insert identical correlation pair -> should raise IntegrityError
        c2 = Correlation(
            metric_anomaly_id=anomaly.id,
            log_anomaly_id=log.id,
            correlation_score=0.90,
            confidence=90.0
        )
        db_session.add(c2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_duplicate_check_service(self, db_session):
        service = CorrelationService()
        
        anomaly = Anomaly(timestamp=datetime.utcnow(), anomaly_score=0.85, severity="warning", detected_by="test", metric_id=1)
        log = Log(timestamp=datetime.utcnow(), level="ERROR", message="Timeout occurred", service_name="test")
        db_session.add_all([anomaly, log])
        db_session.commit()

        # Check before insertion -> false
        assert not service.check_duplicate(db_session, anomaly.id, log.id)

        # Insert record
        corr_data = service.create_correlation(
            anomaly, log, {"correlation_score": 0.85, "confidence": 85.0}, "Database Bottleneck"
        )
        service.store_correlation(db_session, corr_data)

        # Check after insertion -> true
        assert service.check_duplicate(db_session, anomaly.id, log.id)

        # Verify duplicate skipping in pipeline
        result = service.run_correlation_engine(db_session, minutes=10)
        assert result == 0  # no new correlations created since duplicate skipped


# ==========================================================
# TEST 4: ML Log Anomaly Service
# ==========================================================

class TestLogAnomalyService:
    """Verifies that the LogAnomalyService runs TF-IDF vectorization and calls sklearn IsolationForest."""

    @patch("joblib.load")
    def test_prediction_flow(self, mock_load):
        # Mock the Isolation Forest classifier
        mock_model = MagicMock()
        mock_model.predict.return_value = [-1]  # mock prediction of anomaly
        mock_load.return_value = mock_model

        service = LogAnomalyService(model_path="dummy_path.pkl")
        assert service.load_model()
        
        # Test predicted anomaly message
        assert service.predict_log_anomaly("OutOfMemoryError Java heap space exceeded")
        mock_model.predict.assert_called_once()

    def test_get_recent_log_anomalies(self, db_session):
        with patch("joblib.load") as mock_load:
            mock_model = MagicMock()
            # Make it predict anomaly (-1) for the first call and normal (1) for the second call
            mock_model.predict.side_effect = [[-1], [1]]
            mock_load.return_value = mock_model

            # Setup service
            service = LogAnomalyService(model_path="dummy_path.pkl")
            service.load_model()

            # Add mock logs with distinct timestamps to ensure deterministic desc order
            now = datetime.utcnow()
            log1 = Log(timestamp=now, level="ERROR", message="Database crashed", service_name="test")
            log2 = Log(timestamp=now - timedelta(seconds=10), level="INFO", message="Healthy heartbeat", service_name="test")
            db_session.add_all([log1, log2])
            db_session.commit()

            # Call service method
            anomalies = service.get_recent_log_anomalies(db_session, minutes=5)
            # Should only return the log that scored as an anomaly
            assert len(anomalies) == 1
            assert anomalies[0].message == "Database crashed"


# ==========================================================
# TEST 5: Scheduler Execution
# ==========================================================

class TestCorrelationScheduler:
    """Verifies start, shutdown, and job execution of the scheduler."""

    @patch("apscheduler.schedulers.background.BackgroundScheduler.start")
    @patch("apscheduler.schedulers.background.BackgroundScheduler.add_job")
    def test_scheduler_lifecycle(self, mock_add_job, mock_start):
        scheduler = CorrelationScheduler()
        scheduler.start()
        
        assert scheduler.get_status()["scheduler_running"]
        mock_add_job.assert_called_once()
        mock_start.assert_called_once()

        with patch("apscheduler.schedulers.background.BackgroundScheduler.shutdown") as mock_shutdown:
            scheduler.shutdown()
            assert not scheduler.get_status()["scheduler_running"]
            mock_shutdown.assert_called_once()


# ==========================================================
# TEST 6: Health Check & Schema Validation
# ==========================================================

class TestHealthAndSchemas:
    """Tests Pydantic validation and API structures."""

    def test_schemas_phase11_fields(self):
        from backend.schemas import CorrelationResponse
        data = {
            "id": 1,
            "metric_anomaly_id": 10,
            "log_anomaly_id": 5,
            "correlation_score": 0.85,
            "inferred_cause": "Memory Exhaustion",
            "confidence": 85.0,
            "created_at": datetime.now(),
            "service_name": "app-service",
            "host_name": "host-node-01",
            "container_id": "container-xyz"
        }
        resp = CorrelationResponse(**data)
        assert resp.service_name == "app-service"
        assert resp.host_name == "host-node-01"
        assert resp.container_id == "container-xyz"
