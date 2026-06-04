import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import metrics, anomalies, ml
from app.ml_service import get_ml_service

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
    On startup: create database tables if they do not exist, and load ML models.
    On shutdown: dispose engine connections.
    """
    logger.info("MetricGuard backend starting up...")
    logger.info("Creating database tables if they do not exist...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready.")
    
    # Load ML models
    logger.info("Initializing ML models...")
    ml_service = get_ml_service()
    success = ml_service.load_models()
    if success:
        logger.info("ML models loaded successfully at startup.")
    else:
        logger.error("ML models failed to load at startup: %s", ml_service.model_load_error)
        
    yield
    logger.info("MetricGuard backend shutting down...")
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


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health", tags=["Health"])
def health_check():
    """
    Simple health check endpoint for backend visibility.
    """
    return {"status": "healthy", "service": "MetricGuard API"}
