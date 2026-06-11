"""
MetricGuard — Phase 12 Incident Management Test Suite

Tests:
 • Rule-based Priority Assignment (P1 – P4)
 • Rule-based Severity Classification (Critical, High, Medium, Low)
 • Alert Deduplication (30-minute window, same group key, open/investigating)
 • Alert Grouping (group_key calculation)
 • Lifecycle state validation (valid status changes and invalid state jump rejections)
 • REST API Endpoints (POST, GET, PATCH) using TestClient

Run with:
    python -m pytest test_incident_management.py -v
"""

import sys
import os
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.database import SessionLocal, Base, engine
from backend.services.incident_service import get_incident_service
from backend.models.incident import Incident


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def client():
    """
    Create a TestClient that lasts for the entire test module.
    Ensure tables are created before running tests.
    """
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db_session():
    """
    Provide a transaction-backed DB session that rolls back after each test.
    This guarantees test isolation in the database.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ============================================================
# Unit Tests: Priority & Severity Assignments & Grouping
# ============================================================

class TestIncidentRulesAndGrouping:
    """Verify rule-based priority, severity, and grouping logic."""

    def test_priority_assignment(self):
        service = get_incident_service()

        # P1 rules
        assert service.assign_priority("Disk Failure", ["namenode", "datanode"]) == "P1"
        assert service.assign_priority("Disk Failure", ["datanode"]) == "P1"
        assert service.assign_priority("Node Failure", []) == "P1"
        assert service.assign_priority("Cluster Failure", ["client"]) == "P1"

        # P2 rules (multiple services, no namenode, no P1 cause)
        assert service.assign_priority("JVM Garbage Collection", ["datanode", "client"]) == "P2"
        assert service.assign_priority("OutOfMemoryError", ["datanode", "client", "storage"]) == "P2"

        # P3 rules (one service, no namenode, no P1 cause)
        assert service.assign_priority("JVM Garbage Collection", ["datanode"]) == "P3"
        assert service.assign_priority("Slow Disk I/O", ["datanode"]) == "P3"

        # P4 rules (informational, 0 services, no P1 cause)
        assert service.assign_priority("Routine maintenance", []) == "P4"

    def test_severity_assignment(self):
        service = get_incident_service()

        # Critical: >= 3 services
        assert service.assign_severity(["namenode", "datanode", "client"]) == "Critical"
        assert service.assign_severity(["namenode", "datanode", "client", "storage"]) == "Critical"

        # High: 2 services
        assert service.assign_severity(["namenode", "datanode"]) == "High"

        # Medium: 1 service
        assert service.assign_severity(["datanode"]) == "Medium"

        # Low: 0 services
        assert service.assign_severity([]) == "Low"

    def test_group_key_generation(self):
        service = get_incident_service()

        # Group key should be lowercased and have services sorted alphabetically
        key1 = service.build_group_key("Disk Failure", ["datanode", "namenode"])
        key2 = service.build_group_key("  Disk Failure  ", ["namenode", "  datanode  "])

        assert key1 == "disk failure|datanode,namenode"
        assert key1 == key2


# ============================================================
# Unit Tests: Deduplication and Lifecycle
# ============================================================

class TestIncidentServiceFlows:
    """Verify deduplication and status state machine validation."""

    def test_incident_creation_and_deduplication(self, db_session):
        service = get_incident_service()

        # 1. Create initial incident
        inc1 = service.create_incident(
            db=db_session,
            root_cause="Disk Failure",
            impacted_services=["namenode", "datanode"],
        )

        assert inc1.id is not None
        assert inc1.incident_id.startswith("INC-")
        assert inc1.alert_count == 1
        assert inc1.status == "OPEN"
        assert inc1.priority == "P1"
        assert inc1.severity == "High"

        # 2. Trigger a duplicate within 30 minutes
        inc2 = service.create_incident(
            db=db_session,
            root_cause="Disk Failure",
            impacted_services=["datanode", "namenode"],  # swapped order, same services
        )

        # Should return existing incident and increment alert count
        assert inc1.id == inc2.id
        assert inc2.alert_count == 2

        # 3. Simulate another alert with a different root cause
        inc3 = service.create_incident(
            db=db_session,
            root_cause="JVM Garbage Collection",
            impacted_services=["datanode", "namenode"],
        )

        assert inc3.id != inc1.id
        assert inc3.alert_count == 1

    def test_deduplication_ignores_non_active_status(self, db_session):
        service = get_incident_service()

        # Create incident and transition to RESOLVED
        inc1 = service.create_incident(
            db=db_session,
            root_cause="Disk Failure",
            impacted_services=["namenode"],
        )
        service.update_status(db_session, inc1.incident_id, "INVESTIGATING")
        service.update_status(db_session, inc1.incident_id, "MITIGATED")
        service.update_status(db_session, inc1.incident_id, "RESOLVED")

        # Create another incident with same properties
        inc2 = service.create_incident(
            db=db_session,
            root_cause="Disk Failure",
            impacted_services=["namenode"],
        )

        # Since original is RESOLVED, it shouldn't dedup, a new incident must be created
        assert inc2.id != inc1.id
        assert inc2.alert_count == 1

    def test_deduplication_time_window(self, db_session):
        service = get_incident_service()

        # Create incident
        inc1 = service.create_incident(
            db=db_session,
            root_cause="Node Failure",
            impacted_services=["datanode"],
        )

        # Force-update created_at to 31 minutes ago
        inc1.created_at = datetime.utcnow() - timedelta(minutes=31)
        db_session.commit()

        # Create another alert with same properties
        inc2 = service.create_incident(
            db=db_session,
            root_cause="Node Failure",
            impacted_services=["datanode"],
        )

        # Outside 30 min window, should create new incident
        assert inc2.id != inc1.id

    def test_lifecycle_validation(self, db_session):
        service = get_incident_service()

        # Create new incident (defaults to OPEN)
        inc = service.create_incident(
            db=db_session,
            root_cause="Cluster Failure",
            impacted_services=["namenode", "datanode"],
        )
        iid = inc.incident_id

        # OPEN -> RESOLVED (invalid jump, should fail)
        with pytest.raises(ValueError) as excinfo:
            service.update_status(db_session, iid, "RESOLVED")
        assert "Invalid status transition: OPEN → RESOLVED" in str(excinfo.value)

        # OPEN -> INVESTIGATING (valid transition)
        service.update_status(db_session, iid, "INVESTIGATING")
        assert inc.status == "INVESTIGATING"

        # INVESTIGATING -> CLOSED (invalid jump, should fail)
        with pytest.raises(ValueError):
            service.update_status(db_session, iid, "CLOSED")

        # INVESTIGATING -> MITIGATED (valid transition)
        service.update_status(db_session, iid, "MITIGATED")
        assert inc.status == "MITIGATED"

        # MITIGATED -> RESOLVED (valid transition)
        service.update_status(db_session, iid, "RESOLVED")
        assert inc.status == "RESOLVED"

        # RESOLVED -> CLOSED (valid transition)
        service.update_status(db_session, iid, "CLOSED")
        assert inc.status == "CLOSED"


# ============================================================
# API Endpoint Integration Tests
# ============================================================

class TestIncidentAPI:
    """Verify REST API routes and payloads via fastapi TestClient."""

    def test_create_incident_api(self, client):
        payload = {
            "root_cause": "Disk Failure",
            "impacted_services": ["namenode", "datanode"]
        }
        resp = client.post("/incidents/", json=payload)
        assert resp.status_code == 201

        data = resp.json()
        assert "incident_id" in data
        assert data["priority"] == "P1"
        assert data["severity"] == "High"
        assert data["status"] == "OPEN"

    def test_list_incidents_api(self, client):
        # Create a couple of incidents to make sure list is populated
        client.post("/incidents/", json={"root_cause": "Node Failure", "impacted_services": ["datanode"]})
        client.post("/incidents/", json={"root_cause": "Memory Leak", "impacted_services": ["datanode", "client", "storage"]})

        resp = client.get("/incidents/")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert isinstance(data["incidents"], list)
        assert len(data["incidents"]) >= 2

        # Check filters
        resp_filtered = client.get("/incidents/?priority=P1")
        assert resp_filtered.status_code == 200
        filtered_data = resp_filtered.json()
        for inc in filtered_data["incidents"]:
            assert inc["priority"] == "P1"

    def test_get_incident_detail_api(self, client):
        # Create one incident
        create_resp = client.post(
            "/incidents/",
            json={"root_cause": "JVM Pause", "impacted_services": ["datanode"]}
        )
        iid = create_resp.json()["incident_id"]

        resp = client.get(f"/incidents/{iid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["incident_id"] == iid
        assert data["root_cause"] == "JVM Pause"
        assert data["impacted_services"] == ["datanode"]
        assert data["alert_count"] >= 1
        assert "created_at" in data

        # Non-existent incident detail
        resp_404 = client.get("/incidents/INC-999999")
        assert resp_404.status_code == 404

    def test_patch_incident_status_api(self, client):
        # Create one incident
        create_resp = client.post(
            "/incidents/",
            json={"root_cause": "Disk Failure", "impacted_services": ["client"]}
        )
        iid = create_resp.json()["incident_id"]

        # Valid transition OPEN -> INVESTIGATING
        patch_resp = client.patch(f"/incidents/{iid}", json={"status": "INVESTIGATING"})
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "INVESTIGATING"

        # Invalid transition INVESTIGATING -> RESOLVED (skipped MITIGATED)
        patch_bad = client.patch(f"/incidents/{iid}", json={"status": "RESOLVED"})
        assert patch_bad.status_code == 400
        assert "Invalid status transition" in patch_bad.json()["detail"]


class TestAutomaticIntegration:
    """Verify the end-to-end AIOps flow (RCA/Service Impact -> Incidents) is automated."""

    def test_manual_service_impact_creates_incident(self, client, db_session):
        # Trigger Service Impact manual API
        payload = {
            "root_cause": "Disk Failure",
            "affected_service": "storage",
            "confidence": 0.95
        }
        resp = client.post("/services/analyze", json=payload)
        assert resp.status_code == 200
        
        # Verify an incident was created automatically
        from backend.models.incident import Incident
        incident = (
            db_session.query(Incident)
            .filter(Incident.root_cause == "Disk Failure")
            .order_by(Incident.id.desc())
            .first()
        )
        assert incident is not None
        assert "datanode" in incident.group_key
        assert "datanode" in incident.impacted_services
        assert incident.priority == "P1"
        assert incident.severity == "Critical"

    def test_correlation_store_creates_incident(self, db_session):
        # Setup dummy metric anomaly & log anomaly in database
        from app.models import Metric, Anomaly, Log
        metric = Metric(timestamp=datetime.utcnow(), cpu_usage=50.0)
        db_session.add(metric)
        db_session.commit()

        m_anomaly = Anomaly(
            timestamp=datetime.utcnow(),
            anomaly_score=0.9,
            root_cause="Disk Failure",
            severity="critical",
            detected_by="test",
            metric_id=metric.id
        )
        db_session.add(m_anomaly)

        log = Log(
            timestamp=datetime.utcnow(),
            level="ERROR",
            service_name="storage",
            message="disk write failed on sector 5"
        )
        db_session.add(log)
        db_session.commit()

        # Call correlation service
        from backend.services.correlation_service import get_correlation_service
        corr_service = get_correlation_service()
        
        corr_data = {
            "metric_anomaly_id": m_anomaly.id,
            "log_anomaly_id": log.id,
            "correlation_score": 0.94,
            "inferred_cause": "Disk Failure",
            "confidence": 94.0,
            "service_name": "storage"
        }
        
        corr_service.store_correlation(db_session, corr_data)

        # Verify that storing correlation automatically generated an incident
        from backend.models.incident import Incident
        incident = (
            db_session.query(Incident)
            .filter(Incident.root_cause == "Disk Failure")
            .order_by(Incident.id.desc())
            .first()
        )
        assert incident is not None
        assert "datanode" in incident.group_key
        assert incident.priority == "P1"
        assert incident.severity == "Critical"

