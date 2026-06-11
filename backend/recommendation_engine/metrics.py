"""
==========================================================
MetricGuard — Prometheus Metrics  (metrics.py)
==========================================================

Phase 13: Recommendation Engine

Defines and tracks:
  - recommendation_requests_total (Counter)
  - recommendation_generation_time (Histogram)
  - recommendation_confidence_avg (Gauge)
"""

from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger("metricguard.recommendation.metrics")

try:
    from prometheus_client import Counter, Histogram, Gauge
    
    # Track the count of recommendation requests, labeled by root cause and severity
    recommendation_requests_total = Counter(
        "recommendation_requests_total",
        "Total number of recommendation requests processed.",
        ["root_cause", "severity"]
    )

    # Track recommendation generation time
    recommendation_generation_time = Histogram(
        "recommendation_generation_time",
        "Time taken to generate recommendations in seconds.",
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0)
    )

    # Track average confidence score of generated recommendations
    recommendation_confidence_avg = Gauge(
        "recommendation_confidence_avg",
        "Average confidence score of generated recommendations."
    )

    HAS_PROMETHEUS = True
    logger.info("[Metrics] Prometheus metrics exporter initialized successfully.")
except ImportError:
    logger.warning(
        "[Metrics] prometheus_client package is not installed. "
        "Metrics tracking will fall back to in-memory mocks."
    )
    
    # Mock metrics client classes to prevent import/runtime errors
    class MockMetric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs) -> MockMetric:
            return self

        def inc(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

    recommendation_requests_total = MockMetric()
    recommendation_generation_time = MockMetric()
    recommendation_confidence_avg = MockMetric()
    HAS_PROMETHEUS = False


def record_request(root_cause: str, severity: str) -> None:
    """Record a recommendation engine request."""
    try:
        recommendation_requests_total.labels(root_cause=root_cause, severity=severity).inc()
    except Exception as e:
        logger.error("[Metrics] Failed to increment request count: %s", e)


def record_generation_time(duration_seconds: float) -> None:
    """Record duration taken to generate recommendations."""
    try:
        recommendation_generation_time.observe(duration_seconds)
    except Exception as e:
        logger.error("[Metrics] Failed to observe generation duration: %s", e)


def record_confidence(confidence_scores: List[float]) -> None:
    """Record average recommendation confidence."""
    if not confidence_scores:
        return
    try:
        avg_conf = sum(confidence_scores) / len(confidence_scores)
        recommendation_confidence_avg.set(avg_conf)
    except Exception as e:
        logger.error("[Metrics] Failed to record average confidence: %s", e)
