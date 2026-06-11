"""
==========================================================
MetricGuard — Recommendation Engine package init
==========================================================
"""

from backend.recommendation_engine.api import router as recommendation_router
from backend.recommendation_engine.engine import RecommendationEngine
from backend.recommendation_engine.recommendation_service import (
    RecommendationService,
    get_recommendation_service,
)
from backend.recommendation_engine.knowledge_base import (
    load_knowledge_base,
    get_recommendations,
)
