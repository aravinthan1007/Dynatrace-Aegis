from __future__ import annotations

from aegis_agent.dynatrace_skills import build_post_onboarding_queries, get_dynatrace_skill_context


def test_skill_context_infers_gke_skills():
    ctx = get_dynatrace_skill_context(task="gke onboarding verification")

    names = {skill["name"] for skill in ctx["skills"]}

    assert "dt-obs-gcp" in names
    assert "dt-obs-kubernetes" in names
    assert "dt-dql-essentials" in names
    assert ctx["mode"] == "curated-local-subset"


def test_post_onboarding_queries_include_cloud_run_and_gke_checks():
    checks = build_post_onboarding_queries(
        project_id="aegis-project",
        cloud_run_service="aegis-demo-app",
        cluster_name="dynatrace-gcp-monitor",
    )

    queries = {query["name"]: query["dql"] for query in checks["queries"]}

    assert "gcp_resource_inventory" in queries
    assert "cloud_run_service_inventory" in queries
    assert "gke_dynatrace_pods" in queries
    assert "gke_warning_events" in queries
    assert 'gcp.project.id == "aegis-project"' in queries["gcp_resource_inventory"]
    assert 'k8s.cluster.name == "dynatrace-gcp-monitor"' in queries["gke_dynatrace_pods"]
