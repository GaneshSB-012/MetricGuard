"""
==========================================================
MetricGuard — Impact Analyzer  (impact_analyzer.py)
==========================================================

Phase 11: Service Impact Analysis & Dependency Graph

Accepts RCA output (root_cause, affected_service, confidence)
and uses the ``ServiceDependencyGraph`` to determine all
transitively impacted services via BFS traversal.

Severity is inferred from the confidence score:
    >= 0.90  →  Critical
    >= 0.70  →  High
    >= 0.50  →  Warning
    <  0.50  →  Low
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.service_impact.service_graph import ServiceDependencyGraph, get_service_graph

logger = logging.getLogger("metricguard.service_impact.analyzer")


# =========================================================
# SEVERITY MAPPING
# =========================================================

def _confidence_to_severity(confidence: float) -> str:
    """
    Map an RCA confidence score (0.0 – 1.0) to a human-readable
    severity level.

    Thresholds
    ----------
    >= 0.90  →  Critical
    >= 0.70  →  High
    >= 0.50  →  Warning
    <  0.50  →  Low
    """
    if confidence >= 0.90:
        return "Critical"
    if confidence >= 0.70:
        return "High"
    if confidence >= 0.50:
        return "Warning"
    return "Low"


# =========================================================
# IMPACT ANALYZER
# =========================================================

class ImpactAnalyzer:
    """
    Core analysis engine for Phase 11.

    Given RCA output, it queries the dependency graph to
    discover every upstream service affected by a failure
    and computes an overall severity rating.
    """

    def __init__(self, graph: Optional[ServiceDependencyGraph] = None) -> None:
        """
        Parameters
        ----------
        graph : ServiceDependencyGraph, optional
            Override the default singleton graph (useful for testing).
        """
        self._graph = graph or get_service_graph()
        self._last_analysis: Optional[Dict[str, Any]] = None
        logger.info("[Impact Analyzer] Initialised.")

    # --------------------------------------------------
    # Primary analysis method
    # --------------------------------------------------

    def analyze(
        self,
        root_cause: str,
        affected_service: str,
        confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Run a full impact analysis.

        Parameters
        ----------
        root_cause : str
            Description of the root cause (e.g. "Disk Failure").
        affected_service : str
            The service where the failure originated.
        confidence : float
            RCA confidence score (0.0 – 1.0).

        Returns
        -------
        dict
            {
                "root_cause":         str,
                "affected_service":   str,
                "confidence":         float,
                "impacted_services":  list[str],
                "severity":           str,
                "impact_chain":       list[str],   # full chain including root
                "total_affected":     int,
                "analysis_timestamp": str (ISO-8601),
            }

        Raises
        ------
        ValueError
            If *affected_service* is not present in the graph.
        """
        # Normalise service name to lower-case
        affected_service = affected_service.strip().lower()

        if not self._graph.service_exists(affected_service):
            logger.error(
                "[Impact Analyzer] Service '%s' not found in dependency graph.",
                affected_service,
            )
            raise ValueError(
                f"Service '{affected_service}' is not registered in the dependency graph. "
                f"Known services: {self._graph.get_all_services()}"
            )

        # BFS to discover all upstream impacted services
        impacted: List[str] = self._graph.bfs_impacted_services(affected_service)

        # Full impact chain: root service + impacted services
        impact_chain: List[str] = [affected_service] + impacted

        severity = _confidence_to_severity(confidence)

        result: Dict[str, Any] = {
            "root_cause":         root_cause,
            "affected_service":   affected_service,
            "confidence":         round(confidence, 4),
            "impacted_services":  impacted,
            "severity":           severity,
            "impact_chain":       impact_chain,
            "total_affected":     len(impacted),
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }

        # Cache for health engine / dashboard queries
        self._last_analysis = result

        logger.info(
            "[Impact Analyzer] Analysis complete — root_cause='%s', "
            "affected='%s', severity='%s', impacted=%d service(s)",
            root_cause,
            affected_service,
            severity,
            len(impacted),
        )
        return result

    # --------------------------------------------------
    # Accessors
    # --------------------------------------------------

    def get_last_analysis(self) -> Optional[Dict[str, Any]]:
        """Return the most recent analysis result (or ``None``)."""
        return self._last_analysis


# =========================================================
# SINGLETON ACCESSOR
# =========================================================

_analyzer_instance: Optional[ImpactAnalyzer] = None


def get_impact_analyzer() -> ImpactAnalyzer:
    """Return (and lazily create) the singleton ``ImpactAnalyzer``."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ImpactAnalyzer()
    return _analyzer_instance
