import os

from dotenv import load_dotenv

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker


# ==========================================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

# Project root
PROJECT_ROOT = os.path.abspath(
    os.path.join(BASE_DIR, "..")
)

def find_and_load_dotenv():
    """
    Search for .env file in multiple possible locations:
    1. backend/.env (project structure fallback)
    2. Project root .env (MetricGuard/.env)
    3. Current working directory .env (os.getcwd()/.env)
    4. Recursively searching upwards from BASE_DIR
    """
    candidates = [
        os.path.join(PROJECT_ROOT, "backend", ".env"),
        os.path.join(PROJECT_ROOT, ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    
    # Add upward search paths
    current_dir = BASE_DIR
    while True:
        candidates.append(os.path.join(current_dir, ".env"))
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir
        
    for path in candidates:
        if os.path.exists(path):
            load_dotenv(path)
            # Check if required variables are loaded
            if os.getenv("DB_HOST") and (os.getenv("DB_USER") or os.getenv("DB_USERNAME")) and os.getenv("DB_PASSWORD"):
                return path
                
    # Fallback to standard dotenv loading
    load_dotenv()
    return None

find_and_load_dotenv()



# ==========================================================
# DATABASE CONFIGURATION
# ==========================================================

DB_HOST = os.getenv("DB_HOST")

DB_PORT = os.getenv("DB_PORT", "4000")

DB_USER = (
    os.getenv("DB_USER")
    or
    os.getenv("DB_USERNAME")
)

DB_PASSWORD = os.getenv("DB_PASSWORD")

DB_NAME = (
    os.getenv("DB_NAME")
    or
    os.getenv("DB_DATABASE")
    or
    "metricguard"
)


# ==========================================================
# VALIDATE REQUIRED VARIABLES
# ==========================================================

if not all([DB_HOST, DB_USER, DB_PASSWORD]):

    raise ValueError(
        "Missing database configuration. "
        "Please check backend/.env "
        "(DB_HOST, DB_USER/DB_USERNAME, DB_PASSWORD)"
    )


# ==========================================================
# DATABASE URL (TiDB / MySQL Compatible)
# ==========================================================

DATABASE_URL = (
    f"mysql+pymysql://"
    f"{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# ==========================================================
# SQLALCHEMY ENGINE
# ==========================================================

connect_args = {
    "ssl": {
        "ssl_verify_cert": False,
        "ssl_verify_identity": False,
    }
}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)


# ==========================================================
# SESSION FACTORY
# ==========================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ==========================================================
# DECLARATIVE BASE
# ==========================================================

Base = declarative_base()


# ==========================================================
# DATABASE SESSION DEPENDENCY
# ==========================================================

def get_db():
    """
    FastAPI dependency that provides
    a database session per request.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# ==========================================================
# DATABASE HEALTH CHECK
# ==========================================================

def verify_db_connection(db) -> bool:
    """
    Verify database connectivity.
    """

    try:

        db.execute(text("SELECT 1"))

        return True

    except Exception:

        return False