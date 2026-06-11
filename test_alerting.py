"""
MetricGuard — Phase 14 Alerting System Test Suite

Tests:
 • Alert database persistence and schemas
 • Alert ID sequential generation  (relative increment checks, not hardcoded IDs)
 • Alerting rules — HIGH/CRITICAL triggers email + ws; LOW/MEDIUM stores only
 • SMTP Email Notifier — graceful handling of missing configuration
 • WebSocket Notifier — client tracking and real-time push broadcasts
 • REST API Endpoints (client-only, uses real committed DB):
     POST /alerts/send
     GET  /alerts
     GET  /alerts/{alert_id}
     POST /alerts/{alert_id}/ack
     POST /alerts/{alert_id}/resolve
 • WebSocket endpoint subscription (ws://host/ws/alerts)
 • Automated integration: creating an Incident automatically triggers Alert creation

Run with:
    python -m pytest test_alerting.py -v --tb=short
"""

import sys
import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Ensure project root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.database import SessionLocal, Base, engine
from backend.models.incident import Incident
from backend.alerting.models import Alert
from backend.alerting.repository import AlertRepository
from backend.alerting.alert_manager import get_alert_manager
from backend.alerting.websocket_notifier import get_websocket_manager
from backend.alerting.email_notifier import EmailNotifier


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def client():
    """
    Provide a module-scoped TestClient backed by the real DB.
    All tables are created before tests run.
    """
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db_session():
    """
    Transaction-backed DB session (mirrors the existing project test pattern).
    Each test gets a fresh transaction that is rolled back at the end,
    providing clean isolation without touching the real DB state.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ============================================================
# Unit Tests: Alert persistence & rules
# ============================================================

class TestAlertCoreAndRules:
    """Verify repository CRUD, ID generation, and notification rules."""

    def test_alert_persistence(self, db_session):
        manager = get_alert_manager()
        generated_id = manager.generate_alert_id(db_session)

        # Create alert
        alert = AlertRepository.create(
            db=db_session,
            alert_id=generated_id,
            severity="CRITICAL",
            title="Disk Failure",
            message="Disk error on DataNode.",
            affected_services=["datanode"],
        )

        assert alert.id is not None
        assert alert.alert_id == generated_id
        assert alert.alert_id.startswith("ALT-")
        assert alert.severity == "CRITICAL"
        assert alert.status == "OPEN"
        assert alert.affected_services == "datanode"

        # Fetch by ID
        fetched = AlertRepository.get_by_alert_id(db_session, generated_id)
        assert fetched is not None
        assert fetched.title == "Disk Failure"

        # List all — at least our alert must be in it
        all_alerts = AlertRepository.get_all(db_session)
        assert any(a.alert_id == generated_id for a in all_alerts)

    def test_alert_sequential_id_generation(self, db_session):
        manager = get_alert_manager()

        # Generate first ID
        id1 = manager.generate_alert_id(db_session)
        assert id1.startswith("ALT-")
        num1 = int(id1.split("-")[1])

        # Persist it
        AlertRepository.create(
            db=db_session,
            alert_id=id1,
            severity="HIGH",
            title="Seq Test",
            message="Msg",
            affected_services=[],
        )

        # Generate second ID — must be exactly num1 + 1
        id2 = manager.generate_alert_id(db_session)
        assert id2.startswith("ALT-")
        num2 = int(id2.split("-")[1])
        assert num2 == num1 + 1

    @patch("backend.alerting.email_notifier.EmailNotifier.send_alert_email")
    @patch("backend.alerting.websocket_notifier.ConnectionManager.broadcast")
    def test_alerting_rules_triggered(self, mock_ws_broadcast, mock_send_email, db_session):
        manager = get_alert_manager()

        critical_incident = Incident(
            incident_id="INC-RULE-01",
            root_cause="Database Outage",
            impacted_services="namenode,datanode",
            priority="P1",
            severity="Critical",   # CRITICAL → should notify
            status="OPEN",
            alert_count=1,
            group_key="key-rule-01",
        )

        low_incident = Incident(
            incident_id="INC-RULE-02",
            root_cause="Minor GC warning",
            impacted_services="client",
            priority="P3",
            severity="Low",        # LOW → store only, no notifications
            status="OPEN",
            alert_count=1,
            group_key="key-rule-02",
        )

        # CRITICAL → email + websocket both triggered
        alert1 = manager.create_alert(db_session, critical_incident)
        assert alert1.alert_id.startswith("ALT-")
        assert mock_send_email.call_count == 1
        assert mock_ws_broadcast.call_count == 1

        mock_send_email.reset_mock()
        mock_ws_broadcast.reset_mock()

        # LOW → stored but no notifications
        alert2 = manager.create_alert(db_session, low_incident)
        assert alert2.alert_id.startswith("ALT-")
        assert alert1.alert_id != alert2.alert_id   # different IDs
        assert mock_send_email.call_count == 0
        assert mock_ws_broadcast.call_count == 0

    @patch("backend.alerting.email_notifier.EmailNotifier.send_alert_email")
    @patch("backend.alerting.websocket_notifier.ConnectionManager.broadcast")
    def test_alerting_rules_high_severity(self, mock_ws_broadcast, mock_send_email, db_session):
        manager = get_alert_manager()

        high_incident = Incident(
            incident_id="INC-RULE-03",
            root_cause="Network Partition",
            impacted_services="namenode,datanode",
            priority="P2",
            severity="High",       # HIGH → should notify
            status="OPEN",
            alert_count=1,
            group_key="key-rule-03",
        )

        medium_incident = Incident(
            incident_id="INC-RULE-04",
            root_cause="Slow Disk IO",
            impacted_services="datanode",
            priority="P3",
            severity="Medium",     # MEDIUM → store only
            status="OPEN",
            alert_count=1,
            group_key="key-rule-04",
        )

        alert_h = manager.create_alert(db_session, high_incident)
        assert mock_send_email.call_count == 1
        assert mock_ws_broadcast.call_count == 1

        mock_send_email.reset_mock()
        mock_ws_broadcast.reset_mock()

        alert_m = manager.create_alert(db_session, medium_incident)
        assert alert_h.alert_id != alert_m.alert_id
        assert mock_send_email.call_count == 0
        assert mock_ws_broadcast.call_count == 0

    def test_email_notifier_missing_config_graceful(self):
        """Ensure EmailNotifier returns False without raising if config is missing."""
        notifier = EmailNotifier()
        notifier.server = None  # Force missing config

        success = notifier.send_alert_email(
            alert_id="ALT-999",
            severity="CRITICAL",
            title="Unconfigured Server",
            message="Should handle gracefully",
            affected_services=["namenode"],
        )
        assert success is False

    def test_status_lifecycle_via_repository(self, db_session):
        manager = get_alert_manager()
        alert_id = manager.generate_alert_id(db_session)

        AlertRepository.create(
            db=db_session,
            alert_id=alert_id,
            severity="HIGH",
            title="Lifecycle Test",
            message="Testing status transitions",
            affected_services=["datanode"],
        )

        # OPEN → ACKNOWLEDGED
        updated = AlertRepository.update_status(db_session, alert_id, "ACKNOWLEDGED")
        assert updated.status == "ACKNOWLEDGED"

        # ACKNOWLEDGED → Cannot ACK again
        with pytest.raises(ValueError, match="OPEN"):
            AlertRepository.update_status(db_session, alert_id, "ACKNOWLEDGED")

        # ACKNOWLEDGED → RESOLVED
        resolved = AlertRepository.update_status(db_session, alert_id, "RESOLVED")
        assert resolved.status == "RESOLVED"

        # RESOLVED → Cannot transition further
        with pytest.raises(ValueError):
            AlertRepository.update_status(db_session, alert_id, "ACKNOWLEDGED")


# ============================================================
# REST & WebSocket API Endpoint Tests
# (Client-only: creates real data via API so the client can see it)
# ============================================================

class TestAlertingAPIs:
    """
    Verify HTTP and WebSocket endpoints using the real TestClient.
    All setup data is created via REST API calls so it's committed to the
    shared DB and visible to subsequent client requests.
    Uses unique root_cause strings per test to avoid 30-minute deduplication.
    """

    def test_send_alert_endpoint_api(self, client):
        # 1. Create an incident (alert auto-created by hook)
        create_resp = client.post("/incidents/", json={
            "root_cause": "Disk Outage API Test",
            "impacted_services": ["datanode", "namenode"],
        })
        assert create_resp.status_code == 201
        incident_id = create_resp.json()["incident_id"]

        # 2. Manually request an additional alert via the endpoint
        resp = client.post("/alerts/send", json={"incident_id": incident_id})
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        assert data["alert_id"].startswith("ALT-")

        # 3. Non-existent incident → 404
        resp_404 = client.post("/alerts/send", json={"incident_id": "INC-999999"})
        assert resp_404.status_code == 404

    def test_get_alerts_list_api(self, client):
        # Create an incident so alerts exist
        client.post("/incidents/", json={
            "root_cause": "GC Pause List API Test",
            "impacted_services": ["datanode"],
        })

        resp = client.get("/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Validate response schema
        first = data[0]
        assert "alert_id" in first
        assert "severity" in first
        assert "title" in first
        assert "message" in first
        assert "status" in first
        assert "timestamp" in first
        assert isinstance(first["affected_services"], list)

    def test_get_single_alert_api(self, client):
        # Create incident → auto-creates alert
        client.post("/incidents/", json={
            "root_cause": "JVM Pause Single API Test",
            "impacted_services": ["datanode"],
        })

        # Find the alert by its title
        alerts_resp = client.get("/alerts")
        assert alerts_resp.status_code == 200
        alerts = alerts_resp.json()
        matching = [a for a in alerts if a["title"] == "JVM Pause Single API Test"]
        assert len(matching) >= 1, "Expected auto-created alert not found"
        alert_id = matching[0]["alert_id"]

        # Fetch by alert_id
        resp = client.get(f"/alerts/{alert_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["alert_id"] == alert_id
        assert isinstance(body["affected_services"], list)

        # Non-existent alert → 404
        resp_404 = client.get("/alerts/ALT-999999")
        assert resp_404.status_code == 404

    def test_ack_and_resolve_lifecycle_api(self, client):
        # Create incident with unique root cause → auto-created alert in OPEN state
        client.post("/incidents/", json={
            "root_cause": "ACK Resolve Lifecycle API Test",
            "impacted_services": ["namenode", "datanode"],
        })

        # Find the OPEN alert
        alerts_resp = client.get("/alerts")
        alerts = alerts_resp.json()
        open_alerts = [
            a for a in alerts
            if a["title"] == "ACK Resolve Lifecycle API Test" and a["status"] == "OPEN"
        ]
        assert len(open_alerts) >= 1, "Expected OPEN alert not found"
        alert_id = open_alerts[0]["alert_id"]

        # ACK: OPEN → ACKNOWLEDGED
        resp_ack = client.post(f"/alerts/{alert_id}/ack")
        assert resp_ack.status_code == 200
        assert resp_ack.json()["status"] == "ACKNOWLEDGED"

        # Double ACK should fail (400)
        resp_ack2 = client.post(f"/alerts/{alert_id}/ack")
        assert resp_ack2.status_code == 400

        # RESOLVE: ACKNOWLEDGED → RESOLVED
        resp_res = client.post(f"/alerts/{alert_id}/resolve")
        assert resp_res.status_code == 200
        assert resp_res.json()["status"] == "RESOLVED"

        # ACK after RESOLVED should fail (400)
        resp_ack3 = client.post(f"/alerts/{alert_id}/ack")
        assert resp_ack3.status_code == 400

    def test_websocket_broadcast_integration(self, client):
        """
        Verify clients can subscribe and receive pushed alerts via WebSocket.
        """
        manager = get_websocket_manager()

        with client.websocket_connect("/ws/alerts") as websocket:
            ws_payload = {
                "alert_id": "ALT-WS-TEST",
                "severity": "CRITICAL",
                "title": "Disk Failure",
            }

            import asyncio
            asyncio.run(manager.broadcast(ws_payload))

            received = websocket.receive_json()
            assert received["alert_id"] == "ALT-WS-TEST"
            assert received["severity"] == "CRITICAL"
            assert received["title"] == "Disk Failure"


# ============================================================
# Incident Service Automated Hook Integration Test
# ============================================================

class TestIncidentManagerIntegration:
    """Verify that Incident creation automatically calls AlertManager.create_alert."""

    @patch("backend.alerting.alert_manager.AlertManager.create_alert")
    def test_incident_creation_triggers_alert(self, mock_create_alert, db_session):
        from backend.services.incident_service import get_incident_service
        incident_service = get_incident_service()

        inc = incident_service.create_incident(
            db=db_session,
            root_cause="Node Disconnected Hook Test",
            impacted_services=["datanode"],
        )

        assert inc.incident_id is not None
        # Alert Manager hook must have been called exactly once
        assert mock_create_alert.call_count == 1

        # Verify call arguments: first arg = db session, second = the new incident
        args, _ = mock_create_alert.call_args
        assert args[0] is db_session
        assert args[1].incident_id == inc.incident_id
