"""
==========================================================
MetricGuard - Configuration Module
==========================================================

Purpose:
    Centralizes all configuration values for the monitoring
    system. Uses environment variables with sensible defaults
    so the app works out-of-the-box but can be customized
    in production or Docker environments.

How it works:
    1. Loads a .env file (if present) for local overrides.
    2. Reads environment variables with os.getenv().
    3. Falls back to default values if nothing is set.

Usage:
    from config import Config
    print(Config.BACKEND_URL)
"""

import os
from dotenv import load_dotenv

# Load environment variables from a .env file (if it exists)
load_dotenv()


class Config:
    """
    All configuration constants for MetricGuard monitoring.

    Each value can be overridden by setting the corresponding
    environment variable. For example:
        export BACKEND_URL=http://myserver:5000/metrics
    """

    # --------------------------------------------------
    # Backend API Settings
    # --------------------------------------------------
    # The URL where collected metrics are POSTed
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000/metrics")

    # Timeout (seconds) for each HTTP request to the backend
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))

    # --------------------------------------------------
    # Collection Settings
    # --------------------------------------------------
    # How often (seconds) to collect and send metrics
    COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL", "5"))

    # --------------------------------------------------
    # Retry Settings
    # --------------------------------------------------
    # How many times to retry a failed HTTP request
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

    # Seconds to wait between retries (doubles each attempt)
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", "2"))

    # --------------------------------------------------
    # Logging Settings
    # --------------------------------------------------
    # Path to the log file
    LOG_FILE = os.getenv("LOG_FILE", "../logs/system.log")

    # Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # --------------------------------------------------
    # Disk path for psutil.disk_usage()
    # --------------------------------------------------
    # On Linux/Mac use '/', on Windows use 'C:\\'
    DISK_PATH = os.getenv("DISK_PATH", "/")
