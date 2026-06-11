"""
==========================================================
MetricGuard — Service Health Engine  (service_health.py)
==========================================================

Phase 11: Service Impact Analysis & Dependency Graph

Computes per-service health status derived from the latest
impact analysis.  Health states are:

    Healthy   – not impacted at all
    Warning   – impacted, but root-cause confidence < 0.50
    Degraded  – impacted, confidence 0.50 – 0.89
    Critical  – impacted, confidence >= 0.90
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.service_impact.service_graph import get_service_graph, ServiceDependencyGraph
from backend.service_impact.impact_analyzer import get_impact_analyzer, ImpactAnalyzer

logger = logging.getLogger("metricguard.service_impact.health")


# =========================================================
# HEALTH STATUS CONSTANTS
# =========================================================

HEALTH_HEALTHY  = "healthy"
HEALTH_WARNING  = "warning"
HEALTH_DEGRADED = "degraded"
HEALTH_CRITICAL = "critical"


def _confidence_to_health(confidence: float) -> str:
    """
    Map RCA confidence to a service health status.

    Thresholds
    ----------
    >= 0.90  →  critical
    >= 0.50  →  degraded
    >= 0.01  →  warning
    == 0.00  →  healthy
    """
    if confidence >= 0.90:
        return HEALTH_CRITICAL
    if confidence >= 0.50:
        return HEALTH_DEGRADED
    if confidence > 0.0:
        return HEALTH_WARNING
    return HEALTH_HEALTHY


def _health_to_severity(health: str) -> str:
    """
    Map a health status to a severity label for reporting.
    """
    return {
        HEALTH_CRITICAL: "critical",
        HEALTH_DEGRADED: "high",
        HEALTH_WARNING:  "medium",
        HEALTH_HEALTHY:  "none",
    }.get(health, "unknown")


# =========================================================
# SERVICE HEALTH ENGINE
# =========================================================

class ServiceHealthEngine:
    """
    Derives per-service health snapshots from impact analysis results
    and the dependency graph.
    """

    def __init__(
        self,
        graph: Optional[ServiceDependencyGraph] = None,
        analyzer: Optional[ImpactAnalyzer] = None,
    ) -> None:
        self._graph = graph or get_service_graph()
        self._analyzer = analyzer or get_impact_analyzer()
        logger.info("[Service Health] Engine initialised.")

    # --------------------------------------------------
    # Compute health for all services
    # --------------------------------------------------

    def compute_all_health(self) -> List[Dict[str, Any]]:
        """
        Return a health snapshot for every registered service.

        Uses the last impact analysis (if any) to mark affected
        and impacted services.  Services that have not been
        analysed are considered *healthy*.
        """
        analysis = self._analyzer.get_last_analysis()
        services = self._graph.get_all_services()
        result: List[Dict[str, Any]] = []

        for svc in services:
            result.append(self._health_for_service(svc, analysis))

        return result

    # --------------------------------------------------
    # Compute health for a single service
    # --------------------------------------------------

    def get_service_health(self, service_name: str) -> Dict[str, Any]:
        """
        Return the health snapshot for one service.

        Raises ``ValueError`` if the service is not in the graph.
        """
        service_name = service_name.strip().lower()
        if not self._graph.service_exists(service_name):
            raise ValueError(
                f"Service '{service_name}' not found. "
                f"Known services: {self._graph.get_all_services()}"
            )
        analysis = self._analyzer.get_last_analysis()
        return self._health_for_service(service_name, analysis)

    # --------------------------------------------------
    # List currently impacted services
    # --------------------------------------------------

    def get_impacted_services(self) -> List[str]:
        """
        Return the list of impacted services from the last analysis,
        or an empty list if no analysis has been performed yet.
        """
        analysis = self._analyzer.get_last_analysis()
        if analysis is None:
            return []
        return list(analysis.get("impacted_services", []))

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _health_for_service(
        self,
        service_name: str,
        analysis: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build a health dict for *service_name* using *analysis*.
        """
        dependencies = self._graph.get_dependencies(service_name)

        if analysis is None:
            # No analysis performed yet — everything healthy
            return {
                "service_name":    service_name,
                "status":          HEALTH_HEALTHY,
                "severity":        _health_to_severity(HEALTH_HEALTHY),
                "root_dependency": None,
                "dependencies":    dependencies,
            }

        affected = analysis.get("affected_service", "")
        impacted = analysis.get("impacted_services", [])
        confidence = analysis.get("confidence", 0.0)

        if service_name == affected:
            # This is the root-cause service itself
            health = _confidence_to_health(confidence)
            return {
                "service_name":    service_name,
                "status":          health,
                "severity":        _health_to_severity(health),
                "root_dependency": None,
                "dependencies":    dependencies,
            }

        if service_name in impacted:
            # This service is transitively impacted
            health = _confidence_to_health(confidence)
            return {
                "service_name":    service_name,
                "status":          health,
                "severity":        _health_to_severity(health),
                "root_dependency": affected,
                "dependencies":    dependencies,
            }

        # Not impacted
        return {
            "service_name":    service_name,
            "status":          HEALTH_HEALTHY,
            "severity":        _health_to_severity(HEALTH_HEALTHY),
            "root_dependency": None,
            "dependencies":    dependencies,
        }


# =========================================================
# SINGLETON ACCESSOR
# =========================================================

_health_instance: Optional[ServiceHealthEngine] = None


def get_service_health_engine() -> ServiceHealthEngine:
    """Return (and lazily create) the singleton ``ServiceHealthEngine``."""
    global _health_instance
    if _health_instance is None:
        _health_instance = ServiceHealthEngine()
    return _health_instance
