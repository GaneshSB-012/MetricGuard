"""
==========================================================
MetricGuard — Service Dependency Graph  (service_graph.py)
==========================================================

Phase 11: Service Impact Analysis & Dependency Graph

Maintains a directed dependency graph of HDFS/BGL-based
logical services.  The graph is represented as an adjacency
list where each key maps to the list of services it *depends
on* (downstream dependencies).

    client  -->  namenode  -->  datanode  -->  storage

The class supports:
  - Adding / removing services and edges
  - Querying direct dependencies
  - Finding all upstream dependents (who depends on me?)
  - BFS traversal with circular-dependency detection
"""

from __future__ import annotations

import logging
from collections import deque
from copy import deepcopy
from typing import Dict, List, Optional, Set

logger = logging.getLogger("metricguard.service_impact.graph")


# =========================================================
# DEFAULT HDFS / BGL SERVICE DEPENDENCY GRAPH
# =========================================================
# Direction: service  -->  [services it depends on]
#   client   depends on  namenode
#   namenode depends on  datanode
#   datanode depends on  storage
#   storage  has no downstream dependencies

DEFAULT_SERVICE_GRAPH: Dict[str, List[str]] = {
    "client":   ["namenode"],
    "namenode": ["datanode"],
    "datanode": ["storage"],
    "storage":  [],
}


class ServiceDependencyGraph:
    """
    Directed dependency graph for logical services.

    Internal representation (adjacency list):
        { service_name: [list of services it depends on] }

    The *reverse* graph is maintained automatically so that
    upstream lookups (who depends on me?) are O(1) per edge.
    """

    def __init__(self, graph: Optional[Dict[str, List[str]]] = None) -> None:
        """
        Initialise with an optional adjacency list.
        Falls back to the default HDFS graph when *graph* is ``None``.
        """
        self._graph: Dict[str, List[str]] = deepcopy(graph or DEFAULT_SERVICE_GRAPH)
        # Reverse graph: service -> list of services that depend on it
        self._reverse: Dict[str, List[str]] = self._build_reverse()
        logger.info(
            "[Service Graph] Initialised with %d services: %s",
            len(self._graph),
            list(self._graph.keys()),
        )

    # --------------------------------------------------
    # Internal helpers
    # --------------------------------------------------

    def _build_reverse(self) -> Dict[str, List[str]]:
        """Build the reverse adjacency list from scratch."""
        reverse: Dict[str, List[str]] = {svc: [] for svc in self._graph}
        for svc, deps in self._graph.items():
            for dep in deps:
                reverse.setdefault(dep, []).append(svc)
        return reverse

    # --------------------------------------------------
    # Graph mutation
    # --------------------------------------------------

    def add_service(self, service_name: str, dependencies: Optional[List[str]] = None) -> None:
        """
        Add a new service (node) to the graph.

        Parameters
        ----------
        service_name : str
            The logical name of the service.
        dependencies : list[str], optional
            Services that *service_name* depends on.
        """
        if service_name in self._graph:
            logger.warning("[Service Graph] Service '%s' already exists — skipping add.", service_name)
            return

        deps = dependencies or []
        self._graph[service_name] = deps
        self._reverse.setdefault(service_name, [])

        # Update reverse edges
        for dep in deps:
            self._reverse.setdefault(dep, []).append(service_name)

        logger.info("[Service Graph] Added service '%s' with dependencies %s", service_name, deps)

    def remove_service(self, service_name: str) -> bool:
        """
        Remove a service and all edges referencing it.

        Returns ``True`` if the service existed and was removed.
        """
        if service_name not in self._graph:
            logger.warning("[Service Graph] Cannot remove '%s' — not found.", service_name)
            return False

        # Remove forward edges from this service
        del self._graph[service_name]

        # Remove this service from all other adjacency lists
        for svc in self._graph:
            if service_name in self._graph[svc]:
                self._graph[svc].remove(service_name)

        # Rebuild reverse graph (simplest and safest after a deletion)
        self._reverse = self._build_reverse()

        logger.info("[Service Graph] Removed service '%s'", service_name)
        return True

    def add_dependency(self, service_name: str, depends_on: str) -> None:
        """
        Add a single dependency edge:  service_name --> depends_on.
        """
        if service_name not in self._graph:
            self._graph[service_name] = []
            self._reverse.setdefault(service_name, [])

        if depends_on not in self._graph[service_name]:
            self._graph[service_name].append(depends_on)
            self._reverse.setdefault(depends_on, []).append(service_name)
            logger.info("[Service Graph] Edge added: %s --> %s", service_name, depends_on)

    # --------------------------------------------------
    # Query helpers
    # --------------------------------------------------

    def get_all_services(self) -> List[str]:
        """Return a sorted list of all service names."""
        return sorted(self._graph.keys())

    def get_dependencies(self, service_name: str) -> List[str]:
        """Return the *direct* downstream dependencies of a service."""
        return list(self._graph.get(service_name, []))

    def get_dependents(self, service_name: str) -> List[str]:
        """Return services that directly depend on *service_name*."""
        return list(self._reverse.get(service_name, []))

    def service_exists(self, service_name: str) -> bool:
        """Check whether a service is present in the graph."""
        return service_name in self._graph

    def get_graph(self) -> Dict[str, List[str]]:
        """Return a deep copy of the current adjacency list."""
        return deepcopy(self._graph)

    # --------------------------------------------------
    # BFS traversal (upstream impact propagation)
    # --------------------------------------------------

    def bfs_impacted_services(self, affected_service: str) -> List[str]:
        """
        Perform a **BFS traversal** on the *reverse* graph starting
        from *affected_service* to discover every upstream service
        that transitively depends on it.

        Features
        --------
        * Prevents duplicate visits.
        * Detects circular dependencies gracefully (visited-set guard).
        * Returns the traversal path **excluding** the starting node.

        Returns
        -------
        list[str]
            Ordered list of impacted service names (breadth-first order).
        """
        if not self.service_exists(affected_service):
            logger.warning(
                "[Service Graph] BFS aborted — '%s' is not in the graph.", affected_service,
            )
            return []

        visited: Set[str] = set()
        queue: deque[str] = deque()
        impacted: List[str] = []

        visited.add(affected_service)
        queue.append(affected_service)

        while queue:
            current = queue.popleft()

            # All services that directly depend on `current`
            for dependent in self._reverse.get(current, []):
                if dependent in visited:
                    # Circular dependency detected — skip to prevent infinite loop
                    logger.debug(
                        "[Service Graph] Circular dependency detected: "
                        "'%s' already visited while processing '%s'.",
                        dependent,
                        current,
                    )
                    continue

                visited.add(dependent)
                impacted.append(dependent)
                queue.append(dependent)

        logger.info(
            "[Service Graph] BFS from '%s' found %d impacted service(s): %s",
            affected_service,
            len(impacted),
            impacted,
        )
        return impacted


# =========================================================
# SINGLETON ACCESSOR
# =========================================================

_graph_instance: Optional[ServiceDependencyGraph] = None


def get_service_graph() -> ServiceDependencyGraph:
    """Return (and lazily create) the singleton ``ServiceDependencyGraph``."""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = ServiceDependencyGraph()
    return _graph_instance
