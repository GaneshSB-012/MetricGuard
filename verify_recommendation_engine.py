"""
==========================================================
MetricGuard — Phase 13 Recommendation Engine Verification
==========================================================

Verify recommendation service functions and API endpoints.
Run with:   python verify_recommendation_engine.py
"""

import os
import sys
import logging

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("metricguard.verification.recommendation")

# Add workspace root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Base, engine
from backend.recommendation_engine import (
    load_knowledge_base,
    get_recommendations,
    get_recommendation_service,
)
from backend.services.incident_service import get_incident_service
from fastapi.testclient import TestClient
from app.main import app


def test_kb_loading():
    print("=" * 60)
    print("TEST 1: Knowledge Base Loading & Default Rules")
    print("=" * 60)
    
    # 1. Load Knowledge Base
    kb = load_knowledge_base()
    print(f"  Loaded knowledge base file successfully. Count = {len(kb)}")
    assert len(kb) > 0, "KB data should not be empty"

    # 2. Test known root cause retrieval
    recs_db = get_recommendations("Database Timeout")
    print(f"  DB timeout recommendations: {recs_db}")
    assert "Check database connectivity" in recs_db, "Expected DB suggestions not found"

    # 3. Test unknown cause fallback
    recs_unknown = get_recommendations("Rare Random Bug")
    print(f"  Unknown cause fallback: {recs_unknown}")
    assert "Investigate logs" in recs_unknown, "Expected fallback recommendations not found"
    
    print("  ✅ Knowledge base loading & fallback verified successfully.\n")


def test_engine_rules():
    print("=" * 60)
    print("TEST 2: Severity-Aware and Service-Aware Rules")
    print("=" * 60)

    service = get_recommendation_service()

    # 1. Severity check (Critical gets escalation suggestions)
    crit_recs = service.get_recommendations(
        root_cause="Database Timeout",
        severity="Critical",
        impacted_services=[]
    )
    actions = [r["action"] for r in crit_recs]
    print(f"  Critical severity recommendations count: {len(actions)}")
    assert "Escalate to on-call engineer" in actions
    assert "Notify operations team immediately" in actions

    # 2. Service check (RCA-aware database timeouts)
    service_recs = service.get_recommendations(
        root_cause="Database Timeout",
        severity="High",
        impacted_services=["api-service", "payment-service"]
    )
    srv_actions = [r["action"] for r in service_recs]
    print(f"  RCA + Service actions: {srv_actions}")
    assert "Inspect api-service database connections" in srv_actions
    assert "Monitor payment-service retry traffic" in srv_actions

    print("  ✅ Severity and RCA service-aware engine rules verified.\n")


def test_recommendation_confidence():
    print("=" * 60)
    print("TEST 3: Recommendation Confidence Calculation")
    print("=" * 60)

    service = get_recommendation_service()
    service.usage_history = {}  # Reset usage

    # 1. Normal known cause with high confidence
    recs_high = service.get_recommendations(
        root_cause="Database Timeout",
        severity="Medium",
        impacted_services=[],
        confidence=1.0
    )
    conf_high = next(r["confidence"] for r in recs_high if r["action"] == "Check database connectivity")
    print(f"  Known root cause high confidence: {conf_high}")

    # 2. Normal known cause with low confidence
    recs_low = service.get_recommendations(
        root_cause="Database Timeout",
        severity="Medium",
        impacted_services=[],
        confidence=0.4
    )
    conf_low = next(r["confidence"] for r in recs_low if r["action"] == "Check database connectivity")
    print(f"  Known root cause low confidence: {conf_low}")
    assert conf_low < conf_high, "Confidence score should scale with RCA confidence input"

    # 3. Unknown cause with high confidence
    recs_unk = service.get_recommendations(
        root_cause="Totally Random Root Cause",
        severity="Medium",
        impacted_services=[],
        confidence=1.0
    )
    conf_unk = next(r["confidence"] for r in recs_unk if r["action"] == "Investigate logs")
    print(f"  Unknown root cause confidence: {conf_unk}")
    assert conf_unk < conf_high, "Confidence should be lower for unknown root cause certainty"

    # 4. Usage history tracking and boost check
    # Generate database timeout recommendations 5 times to increment usage
    for _ in range(5):
        service.get_recommendations(
            root_cause="Database Timeout",
            severity="Medium",
            impacted_services=[],
            confidence=0.8
        )
    
    recs_boosted = service.get_recommendations(
        root_cause="Database Timeout",
        severity="Medium",
        impacted_services=[],
        confidence=0.8
    )
    conf_boosted = next(r["confidence"] for r in recs_boosted if r["action"] == "Check database connectivity")
    print(f"  Usage-boosted confidence: {conf_boosted}")
    
    # Baseline confidence for 0.8 conf would be: 0.95 * 0.8 * 1.0 = 0.76.
    # Boosted should have usage_boost = 0.05 * 5 = 0.25 added, resulting in 1.0.
    assert conf_boosted > 0.76 or conf_boosted == 1.0, "Historical usage should boost confidence"

    print("  ✅ Recommendation confidence calculations verified.\n")


def test_rest_api():
    print("=" * 60)
    print("TEST 4: FastAPI Endpoint Operations")
    print("=" * 60)

    client = TestClient(app)

    # 1. POST /api/recommendations
    payload = {
        "root_cause": "Database Timeout",
        "severity": "High",
        "impacted_services": ["api-service"],
        "confidence": 0.9
    }
    response = client.post("/api/recommendations", json=payload)
    print(f"  POST /api/recommendations Status Code: {response.status_code}")
    assert response.status_code == 200, "API request failed"

    data = response.json()
    print(f"  API response root_cause: {data['root_cause']}")
    assert data["root_cause"] == "Database Timeout"
    assert len(data["recommendations"]) > 0, "No recommendations returned in JSON payload"
    print(f"  First recommendation action: {data['recommendations'][0]['action']} (Confidence: {data['recommendations'][0]['confidence']})")

    # 2. GET /api/recommendations/metrics
    metrics_resp = client.get("/api/recommendations/metrics")
    print(f"  GET /api/recommendations/metrics Status Code: {metrics_resp.status_code}")
    assert metrics_resp.status_code == 200, "Metrics endpoint failed"
    print(f"  Metrics payload preview:\n{metrics_resp.text[:200]}")

    print("  ✅ REST API endpoints verified.\n")


def test_incident_integration():
    print("=" * 60)
    print("TEST 5: Incident Recommendations GET Endpoint Integration")
    print("=" * 60)

    # Ensure tables are created
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    incident_service = get_incident_service()

    try:
        # Create a sample incident
        incident = incident_service.create_incident(
            db=db,
            root_cause="Memory Leak",
            impacted_services=["api-service"]
        )
        print(f"  Created Incident in DB: {incident.incident_id} | Root Cause: {incident.root_cause}")

        # Retrieve recommendations via Incident Integration endpoint
        client = TestClient(app)
        response = client.get(f"/incidents/{incident.incident_id}/recommendations")
        print(f"  GET /incidents/{incident.incident_id}/recommendations Status Code: {response.status_code}")
        assert response.status_code == 200

        data = response.json()
        print(f"  Linked root cause from incident: {data['root_cause']}")
        assert data["root_cause"] == "Memory Leak"
        
        actions = [r["action"] for r in data["recommendations"]]
        print(f"  Recommendations suggestions: {actions[:3]} (total {len(actions)})")
        assert "Inspect api-service memory consumption" in actions, "Expected service troubleshooting step missing"

        print("  ✅ Incident recommendations endpoints integration verified.\n")

    finally:
        db.close()


if __name__ == "__main__":
    print("🚀 Starting MetricGuard Phase 13 Verification Script...\n")
    try:
        test_kb_loading()
        test_engine_rules()
        test_recommendation_confidence()
        test_rest_api()
        test_incident_integration()
        print("🎉 All Phase 13 Recommendation Engine verifications completed successfully!")
    except AssertionError as ae:
        print(f"❌ Verification FAILED: {ae}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Verification encountered an unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
