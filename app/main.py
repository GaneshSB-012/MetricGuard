import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import engine, Base, SessionLocal, get_db, verify_db_connection
from app.routers import metrics, anomalies, ml, logs
from backend.routes.correlation_routes import router as correlation_router  # Phase 10
from app.ml_service import get_ml_service
from backend.jobs.correlation_scheduler import get_scheduler
from backend.services.log_anomaly_service import get_log_anomaly_service

# =========================================================
# LOGGING CONFIGURATION
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("metricguard")


# =========================================================
# APPLICATION LIFESPAN (startup / shutdown)
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    On startup: verify database connection, create tables, load ML models, and start background scheduler.
    On shutdown: stop scheduler and dispose engine connections.
    """
    logger.info("MetricGuard backend starting up...")
    
    # Verify database connection on startup
    logger.info("Verifying database connection...")
    db = SessionLocal()
    is_connected = verify_db_connection(db)
    
    if not is_connected:
        logger.critical("Database connection verification FAILED. Database is unavailable.")
        db.close()
        raise SystemExit("Database connection failed. Application startup aborted.")
    
    logger.info("Database connection verified successfully.")
    
    logger.info("Creating database tables if they do not exist...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready.")

    # Verify Correlation table existence
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if not inspector.has_table("correlations"):
        logger.critical("Database correlation table 'correlations' is missing!")
        db.close()
        raise SystemExit("Database validation failed: 'correlations' table does not exist.")
    logger.info("Database table 'correlations' existence verified.")
    db.close()
    
    # Load ML models
    logger.info("Initializing ML models...")
    ml_service = get_ml_service()
    success = ml_service.load_models()
    if success:
        logger.info("ML models loaded successfully at startup.")
    else:
        logger.critical("ML models failed to load at startup: %s", ml_service.model_load_error)
        raise SystemExit(f"ML models loading failed: {ml_service.model_load_error}")

    # Initialize and load Log Anomaly ML model
    import os
    logger.info("Verifying log anomaly detection model files and vectorizer...")
    log_service = get_log_anomaly_service()
    
    if not os.path.exists(log_service.model_path):
        logger.critical("Log anomaly model file NOT found at: %s", log_service.model_path)
        raise SystemExit(f"Log anomaly model file not found: {log_service.model_path}")
        
    if log_service.model is None:
        logger.critical("Log anomaly model failed to load at startup!")
        raise SystemExit("Log anomaly model load failed.")
        
    if log_service.vectorizer is None:
        logger.critical("TF-IDF Vectorizer is not initialized!")
        raise SystemExit("TF-IDF Vectorizer is missing/not initialized.")
        
    logger.info("Log anomaly detection model and vectorizer verified successfully.")

    # Start automated scheduler
    logger.info("Starting background correlation scheduler...")
    scheduler = get_scheduler()
    scheduler.start()
        
    yield
    logger.info("MetricGuard backend shutting down...")
    
    # Stop background scheduler
    logger.info("Stopping background correlation scheduler...")
    get_scheduler().shutdown()
    
    engine.dispose()


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="MetricGuard API",
    description="AIOps platform backend — stores system metrics and anomaly detection results in TiDB Cloud.",
    version="1.0.0",
    lifespan=lifespan,
)


# =========================================================
# CORS MIDDLEWARE
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# MOUNT ROUTERS
# =========================================================

app.include_router(metrics.router)
app.include_router(anomalies.router)
app.include_router(ml.router)
app.include_router(logs.router)
app.include_router(correlation_router)  # Phase 10: Metric-Log Correlation Engine


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """
    Exposes detailed status of API service health and database connectivity.
    """
    db_healthy = verify_db_connection(db)
    db_status = "healthy" if db_healthy else "unhealthy"
    
    return {
        "status": "healthy" if db_healthy else "degraded",
        "api": "healthy",
        "database": db_status,
        "timestamp": datetime.now().isoformat()
    }
