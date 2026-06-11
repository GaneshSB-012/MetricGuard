"""
==========================================================
MetricGuard — Knowledge Base Service  (knowledge_base.py)
==========================================================

Phase 13: Recommendation Engine

Manages loading the structured remediation actions from JSON.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Any, Optional

logger = logging.getLogger("metricguard.recommendation.knowledge_base")

# Path to the JSON configuration file
_KB_DIR = os.path.dirname(os.path.abspath(__file__))
_KB_PATH = os.path.join(_KB_DIR, "knowledge_base", "recommendations.json")

# In-memory store of the loaded knowledge base mapping
_KB_DATA: Dict[str, Any] = {}

# Hardcoded fallback list if file loading completely fails or default is missing
_DEFAULT_FALLBACK = [
    "Investigate logs",
    "Review recent deployments",
    "Perform manual diagnosis"
]


def load_knowledge_base() -> Dict[str, Any]:
    """
    Dynamically loads the knowledge base from recommendations.json.
    Returns the raw loaded dictionary mapping.
    """
    global _KB_DATA
    try:
        if not os.path.exists(_KB_PATH):
            logger.error("[Knowledge Base] Configuration file not found at: %s", _KB_PATH)
            _KB_DATA = {}
            return _KB_DATA

        with open(_KB_PATH, "r", encoding="utf-8") as f:
            _KB_DATA = json.load(f)

        logger.info("[Knowledge Base] Loaded %d root causes successfully.", len(_KB_DATA))
        return _KB_DATA
    except Exception as e:
        logger.error("[Knowledge Base] Failed to load configuration: %s", e, exc_info=True)
        _KB_DATA = {}
        return _KB_DATA


def get_recommendations(root_cause: str) -> List[str]:
    """
    Retrieve recommendations list for a given root cause.
    
    Performs case-insensitive matching. If root cause is unknown or not mapped,
    returns fallback/default recommendations.
    """
    global _KB_DATA
    if not _KB_DATA:
        load_knowledge_base()

    if not root_cause:
        return _get_fallback_recommendations()

    # 1. Direct match
    if root_cause in _KB_DATA:
        return _KB_DATA[root_cause].get("recommendations", [])

    # 2. Case-insensitive match
    cleaned_cause = root_cause.strip().lower()
    for cause, data in _KB_DATA.items():
        if cause.strip().lower() == cleaned_cause:
            return data.get("recommendations", [])

    # 3. Fallback to default
    return _get_fallback_recommendations()


def _get_fallback_recommendations() -> List[str]:
    """
    Load fallback recommendations for unknown root causes.
    Attempts to read "Unknown" or "default" key from KB, otherwise falls back to hardcoded defaults.
    """
    global _KB_DATA
    # Check if a custom fallback is defined in the knowledge base JSON under "Unknown" or similar
    for key in ["Unknown", "default", "Default", "unknown"]:
        if key in _KB_DATA:
            return _KB_DATA[key].get("recommendations", [])
    
    return list(_DEFAULT_FALLBACK)
