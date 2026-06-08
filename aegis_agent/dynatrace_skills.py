"""Curated Dynatrace skill context for Aegis agents.

The upstream Dynatrace skill repository is documentation for assistants, not
runtime code. Keep a small pinned subset here so onboarding can stay
deterministic while agents still have good post-onboarding verification and
test-case guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


UPSTREAM_SKILLS_URL = "https://github.com/Dynatrace/dynatrace-for-ai/tree/main/skills"


@dataclass(frozen=True, slots=True)
class DynatraceSkill:
    name: str
    when_to_use: str
    guidance: tuple[str, ...]
    verification_focus: tuple[str, ...]


SKILLS: dict[str, DynatraceSkill] = {
    "dt-dql-essentials": DynatraceSkill(
        name="dt-dql-essentials",
        when_to_use="Build or review DQL used by Aegis reports, evals, and verification checks.",
        guidance=(
            "Use fetch for logs, spans, events, and DAVIS objects; use timeseries for metrics.",
            "Filter early by project, service, cluster, namespace, and time range.",
            "Use curly braces for static lists, for example in(field, {\"a\", \"b\"}).",
            "For logs, severity is loglevel, not log.level.",
            "Use dt.smartscape.* for new topology queries instead of deprecated dt.entity.* fields.",
        ),
        verification_focus=(
            "Queries parse successfully.",
            "Queries include a bounded time range for live data checks.",
            "Grounding evals fail honestly when Grail has no data.",
        ),
    ),
    "dt-obs-gcp": DynatraceSkill(
        name="dt-obs-gcp",
        when_to_use="Analyze GCP resources discovered in Dynatrace Smartscape after onboarding.",
        guidance=(
            "GCP entities use GCP_* Smartscape types and common fields like gcp.project.id, gcp.region, and gcp.resource.name.",
            "Scope checks by gcp.project.id before summarizing resource counts.",
            "Parse gcp.object as JSON only when detailed resource configuration is needed.",
            "Use specific entity types when possible, such as GCP_RUN_GOOGLEAPIS_COM_SERVICE.",
            "Treat missing Smartscape resources as an onboarding visibility problem, not an automatic deployment failure.",
        ),
        verification_focus=(
            "GCP project resources are discoverable.",
            "Cloud Run services appear for Helm-free onboarding.",
            "Pub/Sub and logging resources appear for GKE log onboarding.",
        ),
    ),
    "dt-obs-kubernetes": DynatraceSkill(
        name="dt-obs-kubernetes",
        when_to_use="Validate GKE cluster, pod, node, workload, and Kubernetes event health.",
        guidance=(
            "Use K8S_CLUSTER, K8S_NODE, K8S_NAMESPACE, K8S_POD, and workload Smartscape types.",
            "Combine metrics with Kubernetes events for pod restarts, OOMKills, evictions, and scheduling failures.",
            "For operational events, filter fetch events where event.kind == \"K8S_EVENT\".",
            "Use k8s.object JSON only for configuration inspection such as limits, securityContext, and pod phase.",
            "Do not confuse K8S_POD with host-level CONTAINER entities.",
        ),
        verification_focus=(
            "Cluster and pods are visible in Dynatrace.",
            "Dynatrace namespace pods are running after GKE onboarding.",
            "Recent warning events are surfaced for failed tests.",
        ),
    ),
    "dt-obs-logs": DynatraceSkill(
        name="dt-obs-logs",
        when_to_use="Verify logs are landing and troubleshoot log-derived signals.",
        guidance=(
            "Use fetch logs with explicit time windows.",
            "Use loglevel for severity filtering.",
            "For GCP logs, prefer cloud.provider and gcp.project.id filters when available.",
            "Report zero rows as has_data false rather than success.",
        ),
        verification_focus=(
            "Logs arrive for the project or service under test.",
            "Error and warning logs can be queried for test cases.",
        ),
    ),
    "dt-obs-services": DynatraceSkill(
        name="dt-obs-services",
        when_to_use="Analyze service health, dependencies, latency, and error behavior.",
        guidance=(
            "Use spans for service-level request behavior when service metrics are not available.",
            "Scope by service.name and summarize count, latency, and error indicators.",
            "Keep service checks separate from Kubernetes pod checks.",
        ),
        verification_focus=(
            "The demo service emits spans.",
            "Service dependency risk checks are grounded in live data when available.",
        ),
    ),
    "dt-obs-problems": DynatraceSkill(
        name="dt-obs-problems",
        when_to_use="Check DAVIS problems connected to GCP, Kubernetes, or service entities.",
        guidance=(
            "Use fetch dt.davis.problems for active problem checks.",
            "Filter duplicates before reporting active problems.",
            "Use affected Smartscape entity metadata to connect problems to cloud or Kubernetes resources.",
        ),
        verification_focus=(
            "Active DAVIS problems are included in post-onboarding and game-day reports.",
            "Problem checks are warnings unless the test explicitly requires a clean environment.",
        ),
    ),
}


TASK_SKILL_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gke", ("dt-dql-essentials", "dt-obs-gcp", "dt-obs-kubernetes", "dt-obs-logs", "dt-obs-problems")),
    ("kubernetes", ("dt-dql-essentials", "dt-obs-kubernetes", "dt-obs-logs", "dt-obs-problems")),
    ("cloud run", ("dt-dql-essentials", "dt-obs-gcp", "dt-obs-services", "dt-obs-logs")),
    ("onboard", ("dt-dql-essentials", "dt-obs-gcp", "dt-obs-logs", "dt-obs-services")),
    ("test", ("dt-dql-essentials", "dt-obs-gcp", "dt-obs-kubernetes", "dt-obs-logs", "dt-obs-services")),
)


def _split_names(skill_names: str) -> list[str]:
    return [name.strip() for name in skill_names.replace(";", ",").split(",") if name.strip()]


def skill_names_for_task(task: str) -> list[str]:
    """Return a small relevant skill set for a task description."""
    lowered = task.lower()
    names: list[str] = []
    for marker, skill_names in TASK_SKILL_HINTS:
        if marker in lowered:
            for name in skill_names:
                if name not in names:
                    names.append(name)
    return names or ["dt-dql-essentials", "dt-obs-gcp"]


def get_dynatrace_skill_context(skill_names: str = "", task: str = "") -> dict[str, Any]:
    """Return curated Dynatrace skill guidance for agents and test generation.

    Args:
        skill_names: Comma-separated names. Leave empty to infer from task.
        task: Short task description such as "gke onboarding verification".
    """
    names = _split_names(skill_names) if skill_names else skill_names_for_task(task)
    selected = [SKILLS[name] for name in names if name in SKILLS]
    missing = [name for name in names if name not in SKILLS]
    return {
        "source": UPSTREAM_SKILLS_URL,
        "mode": "curated-local-subset",
        "skills": [
            {
                "name": skill.name,
                "when_to_use": skill.when_to_use,
                "guidance": list(skill.guidance),
                "verification_focus": list(skill.verification_focus),
            }
            for skill in selected
        ],
        "missing": missing,
        "rule": "Use these skills for verification, investigation, and eval prompts; keep live GCP changes in deterministic tools.",
    }


def build_post_onboarding_queries(
    project_id: str,
    cloud_run_service: str = "",
    cluster_name: str = "",
    namespace: str = "dynatrace",
    service_name: str = "aegis-demo-app",
) -> dict[str, Any]:
    """Build DQL checks for post-onboarding validation and eval test cases."""
    queries: list[dict[str, str]] = [
        {
            "name": "gcp_resource_inventory",
            "skill": "dt-obs-gcp",
            "dql": (
                'smartscapeNodes "GCP_*"\n'
                f'| filter gcp.project.id == "{project_id}"\n'
                "| summarize resources = count(), by: {type}\n"
                "| sort resources desc"
            ),
        },
        {
            "name": "gcp_logs_recent",
            "skill": "dt-obs-logs",
            "dql": (
                "fetch logs, from:now()-30m\n"
                f'| filter cloud.provider == "gcp" or gcp.project.id == "{project_id}"\n'
                "| summarize logs = count(), errors = countIf(loglevel == \"ERROR\")"
            ),
        },
        {
            "name": "service_spans_recent",
            "skill": "dt-obs-services",
            "dql": (
                "fetch spans, from:now()-30m\n"
                f'| filter service.name == "{service_name}"\n'
                "| summarize spans = count()"
            ),
        },
        {
            "name": "active_davis_problems",
            "skill": "dt-obs-problems",
            "dql": (
                "fetch dt.davis.problems, from:now()-2h\n"
                "| filter not(dt.davis.is_duplicate) and event.status == \"ACTIVE\"\n"
                "| fields display_id, event.name, event.category, smartscape.affected_entity.ids\n"
                "| limit 20"
            ),
        },
    ]
    if cloud_run_service:
        queries.append(
            {
                "name": "cloud_run_service_inventory",
                "skill": "dt-obs-gcp",
                "dql": (
                    'smartscapeNodes "GCP_RUN_GOOGLEAPIS_COM_SERVICE"\n'
                    f'| filter gcp.project.id == "{project_id}"\n'
                    f'| filter contains(gcp.resource.name, "{cloud_run_service}", false) or contains(name, "{cloud_run_service}", false)\n'
                    "| fields name, gcp.project.id, gcp.region, gcp.resource.name"
                ),
            }
        )
    if cluster_name:
        queries.extend(
            [
                {
                    "name": "gke_cluster_inventory",
                    "skill": "dt-obs-kubernetes",
                    "dql": (
                        "smartscapeNodes K8S_CLUSTER\n"
                        f'| filter k8s.cluster.name == "{cluster_name}"\n'
                        "| fields k8s.cluster.name, k8s.cluster.version, k8s.cluster.distribution"
                    ),
                },
                {
                    "name": "gke_dynatrace_pods",
                    "skill": "dt-obs-kubernetes",
                    "dql": (
                        "smartscapeNodes K8S_POD\n"
                        f'| filter k8s.cluster.name == "{cluster_name}" and k8s.namespace.name == "{namespace}"\n'
                        "| parse k8s.object, \"JSON:config\"\n"
                        "| fieldsAdd phase = config[status][phase]\n"
                        "| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, phase"
                    ),
                },
                {
                    "name": "gke_warning_events",
                    "skill": "dt-obs-kubernetes",
                    "dql": (
                        "fetch events, from:now()-2h\n"
                        "| filter event.kind == \"K8S_EVENT\" and event.type == \"Warning\"\n"
                        f'| filter k8s.cluster.name == "{cluster_name}"\n'
                        "| fields timestamp, k8s.namespace.name, k8s.pod.name, event.reason, event.message\n"
                        "| sort timestamp desc\n"
                        "| limit 50"
                    ),
                },
            ]
        )
    return {
        "source": UPSTREAM_SKILLS_URL,
        "queries": queries,
        "use": "Run these through the Dynatrace MCP after onboarding or convert them into grounding eval cases.",
    }
