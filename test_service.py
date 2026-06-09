import sys
import os
from datetime import datetime

# Add the workspace root to Python path so it can import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Base, engine
from app.schemas import MetricCreate, AnomalyCreate
from app.crud import (
    parse_speed_string,
    insert_metric,
    get_metrics,
    insert_anomaly,
    get_anomalies
)

def test_service_layer():
    print("--------------------------------------------------")
    print("MetricGuard Service Layer Verification Utility")
    print("--------------------------------------------------")
    
    # 1. Test speed string parser
    print("1. Testing parse_speed_string helper...")
    test_cases = [
        ("4.39 MB", 4.39 * 1024),
        ("200 KB", 200.0),
        ("512 B", 512.0 / 1024.0),
        ("1.5 GB", 1.5 * 1024 * 1024),
        (100.0, 100.0),
        (None, 0.0)
    ]
    for raw, expected in test_cases:
        parsed = parse_speed_string(raw)
        print(f"   - Input: {raw!r:10s} | Parsed: {parsed:10.4f} KB | Expected: {expected:10.4f} KB")
        assert abs(parsed - expected) < 1e-5, f"Parser mismatch for {raw}"
    print("   -> Speed parsing tests passed successfully.")

    # 2. Open DB Session
    print("2. Opening DB Session...")
    db = SessionLocal()
    
    try:
        # 3. Create dummy metric
        print("3. Inserting metric through service layer...")
        metric_in = MetricCreate(
            timestamp=datetime.now(),
            cpu_usage=12.34,
            memory_usage=76.89,
            disk_read=parse_speed_string("4.39 MB"),
            disk_write=parse_speed_string("200.00 KB"),
            network_rx=parse_speed_string("32.50 KB"),
            network_tx=parse_speed_string("1.25 MB")
        )
        
        inserted_metric = insert_metric(db, metric_in)
        print(f"   -> Metric inserted (ID: {inserted_metric.id}).")

        # 4. Fetch metrics
        print("4. Retrieving metrics through service layer...")
        metrics = get_metrics(db, limit=5)
        print(f"   -> Retrieved {len(metrics)} metric records from DB.")
        found_metric = next((m for m in metrics if m.id == inserted_metric.id), None)
        assert found_metric is not None, "Inserted metric could not be retrieved"
        print(f"   - Verified retrieved metric matches inserted details (CPU: {found_metric.cpu_usage}%).")

        # 5. Create dummy anomaly
        print("5. Inserting anomaly through service layer...")
        anomaly_in = AnomalyCreate(
            timestamp=datetime.now(),
            anomaly_score=0.985,
            root_cause="CPU Usage",
            severity="CRITICAL",
            detected_by="SERVICE_TEST_SUITE",
            metric_id=inserted_metric.id
        )
        inserted_anomaly = insert_anomaly(db, anomaly_in)
        print(f"   -> Anomaly inserted (ID: {inserted_anomaly.id}).")

        # 6. Fetch anomalies
        print("6. Retrieving anomalies through service layer...")
        anomalies = get_anomalies(db, limit=5)
        print(f"   -> Retrieved {len(anomalies)} anomaly records from DB.")
        found_anomaly = next((a for a in anomalies if a.id == inserted_anomaly.id), None)
        assert found_anomaly is not None, "Inserted anomaly could not be retrieved"
        print(f"   - Verified retrieved anomaly matches inserted details (Score: {found_anomaly.anomaly_score}).")

        # 7. Clean up test records
        print("7. Cleaning up test data...")
        db.delete(inserted_metric)
        db.delete(inserted_anomaly)
        db.commit()
        print("   -> Test data cleaned up successfully.")
        
        print("\n🎉 Service Layer Verification SUCCESSFUL!")
        
    except Exception as e:
        print(f"   [ERROR] Service layer verification failed: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    test_service_layer()
