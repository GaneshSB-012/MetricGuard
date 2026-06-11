"""
==========================================================
MetricGuard — Recommendation Service  (recommendation_service.py)
==========================================================

Phase 13: Recommendation Engine

Singleton service managing recommendation execution and tracking usage history.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Any, Optional

from backend.recommendation_engine.engine import RecommendationEngine

logger = logging.getLogger("metricguard.recommendation.service")


class RecommendationService:
    """
    Service layer for MetricGuard recommendation operations.
    """

    def __init__(self):
        self.engine = RecommendationEngine()
        # In-memory dictionary tracking usage of recommendation actions: action_text -> generation_count
        self.usage_history: Dict[str, int] = {}

    def get_recommendations(
        self,
        root_cause: str,
        severity: str,
        impacted_services: List[str],
        confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate recommendations and update usage tracking.
        """
        logger.info(
            "[Recommendation Service] Generating recommendations for cause=%s, severity=%s, services=%s",
            root_cause, severity, impacted_services
        )
        
        # Calculate recommendations based on current state and historical usage
        recs = self.engine.generate_recommendations(
            root_cause=root_cause,
            severity=severity,
            impacted_services=impacted_services,
            rca_confidence=confidence,
            usage_history=self.usage_history
        )

        # Update historical usage counts for the actions generated
        for item in recs:
            action = item["action"]
            self.usage_history[action] = self.usage_history.get(action, 0) + 1

        logger.debug("[Recommendation Service] History updated: %s", self.usage_history)
        return recs


# =========================================================
# SINGLETON ACCESSOR
# =========================================================

_service_instance: Optional[RecommendationService] = None


def get_recommendation_service() -> RecommendationService:
    """Return (and lazily create) the singleton ``RecommendationService``."""
    global _service_instance
    if _service_instance is None:
        _service_instance = RecommendationService()
    return _service_instance
