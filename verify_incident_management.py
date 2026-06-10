"""
==========================================================
MetricGuard — Phase 12 Incident Management Verification
==========================================================

Verify incident service functions without relying on pytest.
Run with:   python verify_incident_management.py
"""

import sys
import os
from datetime import datetime, timedelta

# Add workspace root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Base, engine
from backend.services.incident_service import get_incident_service


def test_rules():
    print("=" * 60)
    print("TEST 1: Priority & Severity Rules")
    print("=" * 60)

    service = get_incident_service()

    # Priority P1 rules
    p_p1_1 = service.assign_priority("Disk Failure", ["namenode", "datanode"])
    p_p1_2 = service.assign_priority("Memory Leak", ["namenode"])
    print(f"  P1 priority checks:   {p_p1_1} (expected P1), {p_p1_2} (expected P1)")
    assert p_p1_1 == "P1" and p_p1_2 == "P1"

    # Priority P2 rules (multiple services, no namenode, no P1 root causes)
    p_p2 = service.assign_priority("Network Congestion", ["datanode", "client"])
    print(f"  P2 priority check:    {p_p2} (expected P2)")
    assert p_p2 == "P2"

    # Priority P3 rules (one service, no namenode, no P1 root causes)
    p_p3 = service.assign_priority("High CPU", ["datanode"])
    print(f"  P3 priority check:    {p_p3} (expected P3)")
    assert p_p3 == "P3"

    # Priority P4 rules (zero services, no P1 root causes)
    p_p4 = service.assign_priority("High Memory", [])
    print(f"  P4 priority check:    {p_p4} (expected P4)")
    assert p_p4 == "P4"

    # Severity rules
    s_crit = service.assign_severity(["namenode", "datanode", "client"])
    s_high = service.assign_severity(["namenode", "datanode"])
    s_med = service.assign_severity(["datanode"])
    s_low = service.assign_severity([])
    print(f"  Severity checks:      {s_crit} (Critical), {s_high} (High), {s_med} (Medium), {s_low} (Low)")
    assert s_crit == "Critical"
    assert s_high == "High"
    assert s_med == "Medium"
    assert s_low == "Low"

    print("  ✅ Priority and Severity rules verified successfully.\n")


def test_service_flow():
    print("=" * 60)
    print("TEST 2: Incident Creation, Deduplication & Grouping")
    print("=" * 60)

    # Ensure tables are created
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    service = get_incident_service()

    try:
        # Create first incident
        inc1 = service.create_incident(
            db=db,
            root_cause="Node Failure",
            impacted_services=["datanode"],
        )
        print(f"  Created Incident:     {inc1.incident_id} | Alert count: {inc1.alert_count} | Status: {inc1.status}")
        assert inc1.incident_id.startswith("INC-")
        assert inc1.alert_count == 1
        assert inc1.status == "OPEN"

        # Duplicate check within 30 minutes
        inc2 = service.create_incident(
            db=db,
            root_cause="Node Failure",
            impacted_services=["datanode"],
        )
        print(f"  Duplicate Call:       {inc2.incident_id} | Alert count: {inc2.alert_count} (expected 2)")
        assert inc2.incident_id == inc1.incident_id
        assert inc2.alert_count == 2

        # Create distinct incident
        inc3 = service.create_incident(
            db=db,
            root_cause="OutOfMemoryError",
            impacted_services=["datanode", "client"],
        )
        print(f"  Distinct Incident:    {inc3.incident_id} | Alert count: {inc3.alert_count} | Priority: {inc3.priority}")
        assert inc3.incident_id != inc1.incident_id
        assert inc3.alert_count == 1
        assert inc3.priority == "P2"

        # Cleanup test data
        db.delete(inc1)
        db.delete(inc3)
        db.commit()
        print("  ✅ Creation, deduplication, and grouping flows verified successfully.\n")

    except Exception as e:
        db.rollback()
        print(f"  ❌ Flow test failed: {e}")
        raise e
    finally:
        db.close()


def test_lifecycle_validation():
    print("=" * 60)
    print("TEST 3: Lifecycle Transition & Validation")
    print("=" * 60)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    service = get_incident_service()

    try:
        # Create incident
        inc = service.create_incident(
            db=db,
            root_cause="Disk Failure",
            impacted_services=["namenode"],
        )
        iid = inc.incident_id
        print(f"  Created Incident:     {iid} (status={inc.status})")

        # Attempt invalid jump: OPEN -> RESOLVED
        try:
            service.update_status(db, iid, "RESOLVED")
            print("  ❌ Transition validation failed: expected ValueError for OPEN -> RESOLVED")
            assert False
        except ValueError as ve:
            print(f"  Caught expected error: {ve}")

        # Transition: OPEN -> INVESTIGATING
        service.update_status(db, iid, "INVESTIGATING")
        print(f"  Transition:           OPEN -> INVESTIGATING (current={inc.status})")
        assert inc.status == "INVESTIGATING"

        # Transition: INVESTIGATING -> MITIGATED
        service.update_status(db, iid, "MITIGATED")
        print(f"  Transition:           INVESTIGATING -> MITIGATED (current={inc.status})")
        assert inc.status == "MITIGATED"

        # Transition: MITIGATED -> RESOLVED
        service.update_status(db, iid, "RESOLVED")
        print(f"  Transition:           MITIGATED -> RESOLVED (current={inc.status})")
        assert inc.status == "RESOLVED"

        # Transition: RESOLVED -> CLOSED
        service.update_status(db, iid, "CLOSED")
        print(f"  Transition:           RESOLVED -> CLOSED (current={inc.status})")
        assert inc.status == "CLOSED"

        # Cleanup
        db.delete(inc)
        db.commit()
        print("  ✅ State transitions and invalid jump rejections verified successfully.\n")

    except Exception as e:
        db.rollback()
        print(f"  ❌ Lifecycle test failed: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    print("\n🚀 Starting MetricGuard Phase 12 Verification Script...\n")
    test_rules()
    test_service_flow()
    test_lifecycle_validation()
    print("=" * 60)
    print("🎉 ALL VERIFICATIONS PASSED SUCCESSFULLY")
    print("=" * 60)
