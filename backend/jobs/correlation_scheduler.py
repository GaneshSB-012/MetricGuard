"""
==========================================================
MetricGuard — Correlation Scheduler  (correlation_scheduler.py)
==========================================================

Phase 10: Metric-Log Correlation Engine
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal

logger = logging.getLogger("metricguard.correlation.scheduler")


class CorrelationScheduler:
    """
    Background scheduler wrapper to run the correlation engine job
    automatically every 1 minute.
    """

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.last_run: Optional[datetime] = None
        self._running = False
        self._lock = threading.Lock()

    def run_job(self):
        """
        The task executed periodically by the scheduler.
        """
        logger.info("[Correlation Engine] Correlation started (Automated Scheduler)")
        
        with self._lock:
            # Record last run timestamp in local time
            self.last_run = datetime.now()

        db = SessionLocal()
        try:
            from backend.services.correlation_service import get_correlation_service
            service = get_correlation_service()
            correlations_created = service.run_correlation_engine(db, minutes=2)
            
            logger.info(
                "[Correlation Engine] Correlation completed (Automated Scheduler) — "
                "%d correlations created.",
                correlations_created,
            )
        except Exception as e:
            logger.error(
                "[Correlation Engine] Scheduler job failed: %s",
                e,
                exc_info=True,
            )
        finally:
            db.close()

    def start(self):
        """
        Start the background scheduler and add the 1-minute interval job.
        """
        with self._lock:
            if self._running:
                logger.warning("[Correlation Scheduler] Already running.")
                return
            self._running = True

        logger.info("[Correlation Scheduler] Starting background scheduler...")
        self.scheduler.add_job(
            self.run_job,
            "interval",
            minutes=1,
            id="correlation_engine_job",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("[Correlation Scheduler] Scheduler started successfully.")

    def shutdown(self):
        """
        Stop the background scheduler and shutdown cleanly.
        """
        with self._lock:
            if not self._running:
                logger.warning("[Correlation Scheduler] Not running.")
                return
            self._running = False

        logger.info("[Correlation Scheduler] Shutting down scheduler...")
        try:
            self.scheduler.shutdown(wait=False)
            logger.info("[Correlation Scheduler] Scheduler stopped successfully.")
        except Exception as e:
            logger.error("[Correlation Scheduler] Error stopping scheduler: %s", e)

    def get_status(self) -> dict:
        """
        Get thread-safe status of the scheduler.
        """
        with self._lock:
            return {
                "scheduler_running": self._running,
                "last_run": self.last_run.isoformat() if self.last_run else None,
            }


# Singleton instance
_scheduler_instance: Optional[CorrelationScheduler] = None

def get_scheduler() -> CorrelationScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = CorrelationScheduler()
    return _scheduler_instance
