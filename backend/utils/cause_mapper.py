"""
==========================================================
MetricGuard — Cause Mapper  (cause_mapper.py)
==========================================================

Phase 10: Metric-Log Correlation Engine

Purpose
-------
Maps log message keywords to human-readable root cause
labels. Used by the Correlation Engine to infer *why* a
metric anomaly and a log anomaly are related.

The mapper performs case-insensitive substring matching
against a curated dictionary of failure patterns commonly
seen in production systems.

Usage
-----
    from backend.utils.cause_mapper import infer_root_cause

    result = infer_root_cause("Database timeout while processing payment")
    # result == {"cause": "Database Bottleneck", "confidence": 0.9}
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger("metricguard.correlation.cause_mapper")


# ==========================================================
# CAUSE MAP — keyword → human-readable root cause
# ==========================================================
# Each key is a lowercase substring that may appear in log
# messages.  The value is the inferred root cause label.
#
# Ordered from most specific to least specific so that the
# first match wins when multiple patterns could apply.
# ==========================================================

CAUSE_MAP: Dict[str, str] = {
    "database timeout":     "Database Bottleneck",
    "connection refused":   "Database Connectivity Issue",
    "out of memory":        "Memory Exhaustion",
    "disk full":            "Disk Saturation",
    "directory full":       "Disk Saturation",
    "gc overhead":          "JVM Memory Pressure",
    "cpu throttling":       "CPU Saturation",
    "service unavailable":  "Service Failure",
    "network timeout":      "Network Latency Issue",
    "connection pool":      "Connection Pool Exhaustion",
    "deadlock":             "Database Deadlock",
    "replication":          "Database Replication Issue",
    "ssl certificate":      "SSL/TLS Certificate Issue",
    "upstream":             "Upstream Service Failure",
    "rate limit":           "Rate Limiting Active",
    "heap space":           "Memory Exhaustion",
    "disk quota":           "Disk Saturation",
    "socket timeout":       "Network Latency Issue",
    "circuit breaker":      "Service Failure",
}

# Confidence tiers: exact multi-word match gets higher
# confidence than a short single-keyword match.
_HIGH_CONFIDENCE = 0.9
_MEDIUM_CONFIDENCE = 0.7


# ==========================================================
# PUBLIC API
# ==========================================================

def infer_root_cause(log_message: str) -> Dict[str, object]:
    """
    Scan a log message for known failure patterns and return
    the most likely root cause.

    Parameters
    ----------
    log_message : str
        The raw log message text to analyse.

    Returns
    -------
    dict
        ``{"cause": "<label>", "confidence": <float>}``

        If no pattern matches, returns:
        ``{"cause": "Unknown", "confidence": 0.0}``
    """
    if not log_message:
        return {"cause": "Unknown", "confidence": 0.0}

    message_lower = log_message.lower()

    for keyword, cause in CAUSE_MAP.items():
        if keyword in message_lower:
            # Multi-word keywords are more specific → higher confidence
            confidence = (
                _HIGH_CONFIDENCE
                if " " in keyword
                else _MEDIUM_CONFIDENCE
            )

            logger.debug(
                "[Cause Mapper] Matched keyword '%s' → cause '%s' (confidence=%.2f)",
                keyword, cause, confidence,
            )
            return {"cause": cause, "confidence": confidence}

    logger.debug(
        "[Cause Mapper] No keyword match for message: %.100s",
        log_message,
    )
    return {"cause": "Unknown", "confidence": 0.0}
