"""
==========================================================
MetricGuard — Recommendation Engine  (engine.py)
==========================================================

Phase 13: Recommendation Engine

Combines Rule-Based, Service-Aware, Severity-Aware actions,
and calculates the recommendation confidence.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Any, Optional

from backend.recommendation_engine.knowledge_base import get_recommendations, load_knowledge_base

logger = logging.getLogger("metricguard.recommendation.engine")


class RecommendationEngine:
    """
    Core engine responsible for generating remediation recommendations.
    """

    def __init__(self):
        # Pre-load knowledge base
        load_knowledge_base()

    def generate_recommendations(
        self,
        root_cause: str,
        severity: str,
        impacted_services: List[str],
        rca_confidence: Optional[float] = None,
        usage_history: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate a list of confidence-scored recommendations.
        
        Parameters
        ----------
        root_cause : str
            The diagnosed root cause category or message.
        severity : str
            The severity level (Critical, High, Medium, Low).
        impacted_services : List[str]
            List of services affected by the incident.
        rca_confidence : Optional[float]
            Optional RCA confidence score (0.0 to 1.0). Defaults to 1.0.
        usage_history : Optional[Dict[str, int]]
            Dictionary mapping recommendation action text to usage count.
            
        Returns
        -------
        List[Dict[str, Any]]
            A list of dicts: [{"action": str, "confidence": float}]
        """
        if rca_confidence is None:
            rca_confidence = 1.0

        if usage_history is None:
            usage_history = {}

        # 1. Determine Certainty Factor & Base KB Recommendations
        base_kb_actions = get_recommendations(root_cause)
        
        # Check if the root cause was actually in the KB or fallback was used
        from backend.recommendation_engine.knowledge_base import _KB_DATA
        # Cleaned root cause check
        rc_lower = root_cause.strip().lower()
        is_known = False
        if _KB_DATA:
            for cause in _KB_DATA.keys():
                if cause.strip().lower() == rc_lower:
                    is_known = True
                    break
                    
        certainty_factor = 1.0 if is_known else 0.6
        base_confidence_kb = 0.95 if is_known else 0.50

        recommendations_dict: Dict[str, float] = {}

        # Helper to add action and compute confidence
        def add_recommendation(action_text: str, base_conf: float):
            cleaned_action = action_text.strip()
            if not cleaned_action:
                return
            
            # Calculate confidence using the formula:
            # confidence = base_conf * rca_confidence * certainty_factor
            raw_conf = base_conf * rca_confidence * certainty_factor
            
            # Apply historical usage boost
            usage_count = usage_history.get(cleaned_action, 0)
            usage_boost = 0.05 * min(usage_count, 5)  # Max +0.25 boost
            
            final_conf = min(raw_conf + usage_boost, 1.0)
            final_conf = round(final_conf, 2)
            
            # If the action already exists, keep the higher confidence
            if cleaned_action in recommendations_dict:
                recommendations_dict[cleaned_action] = max(recommendations_dict[cleaned_action], final_conf)
            else:
                recommendations_dict[cleaned_action] = final_conf

        # 2. Add Base Recommendations
        for action in base_kb_actions:
            add_recommendation(action, base_confidence_kb)

        # 3. Add RCA-Aware Service-Specific Recommendations (Feature 2)
        # Avoid duplicate recommendation generation by applying rules
        rc_lower_search = root_cause.lower()
        is_db_issue = any(k in rc_lower_search for k in ["database", "db", "timeout", "deadlock", "connection", "replication", "pool"])
        is_cpu_issue = any(k in rc_lower_search for k in ["cpu", "throttling", "saturation"])
        is_mem_issue = any(k in rc_lower_search for k in ["memory", "leak", "jvm", "heap", "gc"])
        is_disk_issue = any(k in rc_lower_search for k in ["disk", "saturation", "quota", "failure"])
        is_net_issue = any(k in rc_lower_search for k in ["network", "latency", "congestion", "bandwidth"])

        for service in impacted_services:
            service_clean = service.strip()
            if not service_clean:
                continue
            service_lower = service_clean.lower()

            # 1. Base root-cause type specific suggestions for the service
            if is_db_issue:
                add_recommendation(f"Inspect {service_clean} database connections", 0.85)
            elif is_cpu_issue:
                add_recommendation(f"Monitor CPU utilization on {service_clean}", 0.85)
            elif is_mem_issue:
                add_recommendation(f"Inspect {service_clean} memory consumption", 0.85)
            elif is_disk_issue:
                add_recommendation(f"Check disk space and permissions on {service_clean}", 0.85)
            elif is_net_issue:
                add_recommendation(f"Check network latency for {service_clean}", 0.85)

            # 2. Service name keyword specific suggestions
            if "api" in service_lower or "db" in service_lower or "database" in service_lower:
                if is_db_issue:
                    add_recommendation(f"Inspect {service_clean} database connections", 0.85)
                # General database check only if no resource specific check was triggered
                elif not (is_cpu_issue or is_mem_issue or is_disk_issue or is_net_issue):
                    add_recommendation(f"Inspect {service_clean} database connections", 0.85)
            
            if "payment" in service_lower or "retry" in service_lower:
                add_recommendation(f"Monitor {service_clean} retry traffic", 0.85)
                
            if "namenode" in service_lower or "datanode" in service_lower:
                add_recommendation(f"Check HDFS service status for {service_clean}", 0.85)

            # 3. Safe fallback if no specific recommendation was added for this service yet
            has_service_rec = any(service_clean in act for act in recommendations_dict.keys())
            if not has_service_rec:
                add_recommendation(f"Monitor {service_clean} retry traffic", 0.80)
                add_recommendation(f"Inspect {service_clean} logs", 0.80)


        # 4. Add Severity-Aware Recommendations (Feature 3)
        severity_clean = severity.strip().upper()
        if severity_clean == "CRITICAL":
            add_recommendation("Escalate to on-call engineer", 0.75)
            add_recommendation("Notify operations team immediately", 0.75)
            add_recommendation("Initiate emergency response process", 0.75)
        elif severity_clean == "HIGH":
            add_recommendation("Prioritize investigation", 0.75)
            add_recommendation("Assign incident owner", 0.75)
        elif severity_clean == "MEDIUM":
            add_recommendation("Monitor affected services", 0.75)
            add_recommendation("Schedule troubleshooting", 0.75)
        elif severity_clean == "LOW":
            add_recommendation("Track issue for future analysis", 0.75)

        # Format output as requested
        result = [
            {"action": action, "confidence": conf}
            for action, conf in recommendations_dict.items()
        ]
        
        # Sort by confidence descending to prioritize highest-confidence actions
        result.sort(key=lambda x: x["confidence"], reverse=True)
        return result
