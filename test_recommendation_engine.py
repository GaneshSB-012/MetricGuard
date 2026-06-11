"""
MetricGuard — Phase 13 Recommendation Engine Test Suite

Tests:
 • Knowledge Base loading and retrieval
 • Rule-based recommendations matching
 • Severity-aware escalations
 • RCA-aware service-specific recommendations
 • Confidence calculations (influence of certainty, usage, and RCA score)
 • REST API Endpoints (POST /api/recommendations, GET /api/recommendations/metrics)
 • Incident integration (GET /incidents/{incident_id}/recommendations)

Run with:
    python -m pytest test_recommendation_engine.py -v
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.database import SessionLocal, Base, engine
from backend.recommendation_engine import (
    get_recommendation_service,
    load_knowledge_base,
    get_recommendations,
)
from backend.services.incident_service import get_incident_service
from backend.models.incident import Incident


@pytest.fixture(scope="module")
def client():
    """
    FastAPI TestClient fixture.
    """
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db_session():
    """
    Transaction-backed DB session.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ============================================================
# Unit Tests: Knowledge Base & Core Rules
# ============================================================

def test_kb_loading():
    """Verify KB file loads correctly and contains expected categories."""
    kb_data = load_knowledge_base()
    assert isinstance(kb_data, dict)
    assert len(kb_data) > 0
    assert "Database Timeout" in kb_data
    assert "High CPU Usage" in kb_data


def test_rule_based_matching():
    """Verify get_recommendations matches root cause strings case-insensitively."""
    # Direct case match
    recs_db = get_recommendations("Database Timeout")
    assert "Check database connectivity" in recs_db

    # Case insensitivity
    recs_lower = get_recommendations("database timeout")
    assert "Check database connectivity" in recs_lower

    # Space cleaning
    recs_spaces = get_recommendations("   Database Timeout   ")
    assert "Check database connectivity" in recs_spaces


def test_unknown_root_cause_fallback():
    """Verify fallback to defaults when root cause is unknown."""
    unknown_recs = get_recommendations("Extremely Rare Custom Failure Code 999")
    assert "Investigate logs" in unknown_recs
    assert "Review recent deployments" in unknown_recs
    assert "Perform manual diagnosis" in unknown_recs


# ============================================================
# Unit Tests: Engine Logic (Severity & Service Aware)
# ============================================================

def test_engine_severity_aware():
    """Verify recommendations are severity-aware."""
    service = get_recommendation_service()

    # Critical severity
    crit_recs = service.get_recommendations(
        root_cause="Database Timeout",
        severity="Critical",
        impacted_services=[]
    )
    actions = [r["action"] for r in crit_recs]
    assert "Escalate to on-call engineer" in actions
    assert "Notify operations team immediately" in actions
    assert "Initiate emergency response process" in actions

    # High severity
    high_recs = service.get_recommendations(
        root_cause="Database Timeout",
        severity="High",
        impacted_services=[]
    )
    actions_high = [r["action"] for r in high_recs]
    assert "Prioritize investigation" in actions_high
    assert "Assign incident owner" in actions_high


def test_engine_rca_aware():
    """Verify dynamic service-specific recommendations are generated."""
    service = get_recommendation_service()

    # Database issue + API service + Payment service
    recs = service.get_recommendations(
        root_cause="Database Timeout",
        severity="High",
        impacted_services=["api-service", "payment-service"]
    )
    actions = [r["action"] for r in recs]
    
    # Matches api-service rules
    assert "Inspect api-service database connections" in actions
    # Matches payment-service rules
    assert "Monitor payment-service retry traffic" in actions


# ============================================================
# Unit Tests: Recommendation Confidence
# ============================================================

def test_engine_confidence_influences():
    """Verify confidence score is correctly computed."""
    service = get_recommendation_service()
    # Reset usage history for clean test
    service.usage_history = {}

    # Case A: High RCA confidence + Known Root cause
    recs_a = service.get_recommendations(
        root_cause="Database Timeout",
        severity="Low",
        impacted_services=[],
        confidence=1.0
    )
    conf_a = next(r["confidence"] for r in recs_a if r["action"] == "Check database connectivity")

    # Case B: Low RCA confidence + Known Root cause
    recs_b = service.get_recommendations(
        root_cause="Database Timeout",
        severity="Low",
        impacted_services=[],
        confidence=0.5
    )
    conf_b = next(r["confidence"] for r in recs_b if r["action"] == "Check database connectivity")

    # Case C: High RCA confidence + Unknown Root cause
    recs_c = service.get_recommendations(
        root_cause="Unknown Weird Issue",
        severity="Low",
        impacted_services=[],
        confidence=1.0
    )
    conf_c = next(r["confidence"] for r in recs_c if r["action"] == "Investigate logs")

    # B should be lower than A because of lower RCA score
    assert conf_b < conf_a
    # C should be lower than A because of certainty factor (unknown root cause)
    assert conf_c < conf_a

    # Test historical usage boost
    # Trigger generation multiple times to build history count
    for _ in range(5):
        service.get_recommendations(
            root_cause="Database Timeout",
            severity="Low",
            impacted_services=[],
            confidence=1.0
        )
    
    recs_boosted = service.get_recommendations(
        root_cause="Database Timeout",
        severity="Low",
        impacted_services=[],
        confidence=1.0
    )
    conf_boosted = next(r["confidence"] for r in recs_boosted if r["action"] == "Check database connectivity")
    
    # Confidence should be boosted (closer or equal to 1.0)
    assert conf_boosted > conf_a or conf_boosted == 1.0


# ============================================================
# API Endpoint Tests
# ============================================================

def test_api_generate_recommendations(client):
    """Verify POST /api/recommendations responds correctly."""
    payload = {
        "root_cause": "Database Timeout",
        "severity": "High",
        "impacted_services": ["api-service", "payment-service"],
        "confidence": 0.95
    }
    response = client.post("/api/recommendations", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["root_cause"] == "Database Timeout"
    assert "recommendations" in data
    assert len(data["recommendations"]) > 0
    
    # Check that recommendation items contain action and confidence fields
    first_item = data["recommendations"][0]
    assert "action" in first_item
    assert "confidence" in first_item
    assert isinstance(first_item["action"], str)
    assert isinstance(first_item["confidence"], float)


def test_api_invalid_severity(client):
    """Verify POST /api/recommendations rejects invalid severity values."""
    payload = {
        "root_cause": "Database Timeout",
        "severity": "SuperCriticalAlert",  # Invalid severity name
        "impacted_services": []
    }
    response = client.post("/api/recommendations", json=payload)
    assert response.status_code == 422  # Pydantic validation error


def test_api_metrics_endpoint(client):
    """Verify GET /api/recommendations/metrics responds correctly."""
    response = client.get("/api/recommendations/metrics")
    assert response.status_code == 200
    # Must be plain text formats
    assert response.headers["content-type"].startswith("text/plain")


# ============================================================
# Incident Integration Test
# ============================================================

def test_incident_recommendations_integration(client):
    """Verify GET /incidents/{incident_id}/recommendations returns recommendations from DB incident."""
    payload = {
        "root_cause": "Database Timeout",
        "impacted_services": ["api-service"]
    }
    create_resp = client.post("/incidents/", json=payload)
    assert create_resp.status_code == 201
    incident_id = create_resp.json()["incident_id"]
    
    # Hit recommendations API endpoint for this incident
    response = client.get(f"/incidents/{incident_id}/recommendations")
    assert response.status_code == 200
    
    data = response.json()
    assert data["root_cause"] == "Database Timeout"
    assert "recommendations" in data
    
    # Find service-specific action
    actions = [r["action"] for r in data["recommendations"]]
    assert "Inspect api-service database connections" in actions

