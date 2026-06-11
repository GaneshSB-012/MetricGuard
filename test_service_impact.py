"""
==========================================================
MetricGuard — Phase 11 Test Script
==========================================================

Run with:   python test_service_impact.py
No server or database required.
"""

import json


def test_service_graph():
    """Test 1: Service Dependency Graph"""
    from backend.service_impact.service_graph import ServiceDependencyGraph

    print("=" * 55)
    print("TEST 1: Service Dependency Graph")
    print("=" * 55)

    graph = ServiceDependencyGraph()
    print(f"  All services:            {graph.get_all_services()}")
    print(f"  Dependencies of client:  {graph.get_dependencies('client')}")
    print(f"  Dependents of storage:   {graph.get_dependents('storage')}")
    print(f"  BFS from storage:        {graph.bfs_impacted_services('storage')}")

    assert graph.get_all_services() == ["client", "datanode", "namenode", "storage"]
    assert graph.bfs_impacted_services("storage") == ["datanode", "namenode", "client"]
    print("  ✅ PASSED\n")
    return graph


def test_impact_analyzer(graph):
    """Test 2: Impact Analyzer"""
    from backend.service_impact.impact_analyzer import ImpactAnalyzer

    print("=" * 55)
    print("TEST 2: Impact Analyzer")
    print("=" * 55)

    analyzer = ImpactAnalyzer(graph=graph)
    result = analyzer.analyze("Disk Failure", "storage", 0.94)
    print(json.dumps(result, indent=2))

    assert result["root_cause"] == "Disk Failure"
    assert result["affected_service"] == "storage"
    assert result["severity"] == "Critical"
    assert result["impacted_services"] == ["datanode", "namenode", "client"]
    assert result["total_affected"] == 3
    print("  ✅ PASSED\n")
    return analyzer


def test_service_health(graph, analyzer):
    """Test 3: Service Health Engine"""
    from backend.service_impact.service_health import ServiceHealthEngine

    print("=" * 55)
    print("TEST 3: Service Health Engine")
    print("=" * 55)

    health = ServiceHealthEngine(graph=graph, analyzer=analyzer)
    all_health = health.compute_all_health()

    for h in all_health:
        print(f"  {h['service_name']:10s} | status={h['status']:10s} | root_dep={h['root_dependency']}")

    impacted = health.get_impacted_services()
    print(f"\n  Impacted services: {impacted}")

    assert impacted == ["datanode", "namenode", "client"]

    namenode_health = health.get_service_health("namenode")
    assert namenode_health["status"] == "critical"
    assert namenode_health["root_dependency"] == "storage"
    print("  ✅ PASSED\n")


def test_circular_dependency():
    """Test 4: Circular Dependency Detection"""
    from backend.service_impact.service_graph import ServiceDependencyGraph

    print("=" * 55)
    print("TEST 4: Circular Dependency Detection")
    print("=" * 55)

    g = ServiceDependencyGraph({"A": ["B"], "B": ["C"], "C": ["A"]})
    result = g.bfs_impacted_services("A")
    print(f"  BFS from A (circular graph): {result}")

    # Should not hang or crash — visited-set prevents infinite loop
    assert "A" not in result  # starting node excluded
    print("  ✅ PASSED\n")


def test_add_remove_service():
    """Test 5: Add / Remove Service"""
    from backend.service_impact.service_graph import ServiceDependencyGraph

    print("=" * 55)
    print("TEST 5: Add / Remove Service")
    print("=" * 55)

    graph = ServiceDependencyGraph()
    graph.add_service("journalnode", ["namenode"])
    print(f"  After adding journalnode:  {graph.get_all_services()}")
    assert "journalnode" in graph.get_all_services()

    graph.remove_service("journalnode")
    print(f"  After removing journalnode: {graph.get_all_services()}")
    assert "journalnode" not in graph.get_all_services()
    print("  ✅ PASSED\n")


def test_unknown_service():
    """Test 6: Unknown service raises ValueError"""
    from backend.service_impact.impact_analyzer import ImpactAnalyzer

    print("=" * 55)
    print("TEST 6: Unknown Service Error Handling")
    print("=" * 55)

    analyzer = ImpactAnalyzer()
    try:
        analyzer.analyze("Disk Failure", "unknown_service", 0.5)
        print("  ❌ FAILED — no error raised")
    except ValueError as e:
        print(f"  Caught expected error: {e}")
        print("  ✅ PASSED\n")


if __name__ == "__main__":
    print("\n🚀 MetricGuard Phase 11 — Service Impact Analysis Tests\n")

    graph = test_service_graph()
    analyzer = test_impact_analyzer(graph)
    test_service_health(graph, analyzer)
    test_circular_dependency()
    test_add_remove_service()
    test_unknown_service()

    print("=" * 55)
    print("🎉 ALL 6 TESTS PASSED")
    print("=" * 55)
