"""Self-healing, single-project Dynatrace GCP metric + log onboarding on a new
GKE Autopilot cluster (Google ADK + Gemini + Dynatrace MCP).

This implements the official Dynatrace "Set up the Dynatrace GCP metric and log
integration on a *new* GKE Autopilot cluster" runbook as one agentic call:

  1. preflight  - confirm gcloud auth + project, and that kubectl/helm/jq/yq/unzip exist
  2. iam        - create the custom `dynatrace_monitor.helm_deployment` role + bind it
  3. pubsub     - download & run deploy-pubsub.sh (topic + log subscription)
  4. logsink    - route GCP logs into the Pub/Sub topic (log export sink)
  5. helm_pkg   - download the official helm-deployment-package.tar
  6. values     - write values.yaml (gcpProjectId, dynatraceUrl, access key, sub id)
  7. deploy     - ./deploy-helm.sh --create-autopilot-cluster   (creates the cluster)
  8. verify_pods- kubectl -n dynatrace get pods   (metric + log forwarder running)
  9. verify_dt  - via the Dynatrace MCP, confirm GCP data is actually queryable in Grail

The agent is **self-healing**: when a gcloud/kubectl/helm command fails, it matches the
error against a remediation library (disabled API, missing IAM role/binding, missing CLI
tool, missing cluster credentials, "already exists", ...), runs the fix, and retries the
original command. Anything it does not recognise (quota, billing, hard auth failures) is
reported rather than blindly retried.

Safe by default: **dry-run** prints the exact commands it *would* run. Pass `execute=True`
(CLI: `--execute`) to run them live against the authenticated gcloud project. Honest by
design: the final verify reports `has_data: false` instead of pretending success when the
tenant accepts data but is not yet retaining it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import shutil
import subprocess
import time
from textwrap import dedent
from typing import Any, Callable

from google.adk.apps import App
from google.adk.tools.function_tool import FunctionTool

try:
    from google.adk.agents import LlmAgent as BaseAgent
except ImportError:  # pragma: no cover
    from google.adk.agents import Agent as BaseAgent

from ..config import get_config
from ..dynatrace import query_dql
from ..events import event_bus

config = get_config()

# --- official Dynatrace artifacts (downloaded at runtime, never hardcoded/stale) ---
PUBSUB_SCRIPT_URL = (
    "https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-monitor/"
    "master/scripts/deploy-pubsub.sh"
)
HELM_PACKAGE_URL = (
    "https://github.com/dynatrace-oss/dynatrace-gcp-monitor/releases/latest/"
    "download/helm-deployment-package.tar"
)

REQUIRED_APIS = [
    "cloudresourcemanager.googleapis.com",
    "container.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "pubsub.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
]

# Custom deployment role. The canonical file ships with the runbook; this documented
# starter set is written only if the user has not provided their own role file.
DEPLOY_ROLE_ID = "dynatrace_monitor.helm_deployment"
DEPLOY_ROLE_YAML = dedent(
    """\
    title: Dynatrace GCP Monitor - Helm deployment
    description: Permissions required to deploy dynatrace-gcp-monitor via Helm.
    stage: GA
    includedPermissions:
      - resourcemanager.projects.get
      - serviceusage.services.enable
      - serviceusage.services.get
      - serviceusage.services.list
      - iam.roles.create
      - iam.roles.get
      - iam.roles.update
      - iam.roles.list
      - iam.serviceAccounts.create
      - iam.serviceAccounts.get
      - iam.serviceAccounts.list
      - resourcemanager.projects.getIamPolicy
      - resourcemanager.projects.setIamPolicy
      - pubsub.topics.create
      - pubsub.topics.get
      - pubsub.subscriptions.create
      - pubsub.subscriptions.get
      - logging.sinks.create
      - logging.sinks.get
      - container.clusters.create
      - container.clusters.get
      - container.clusters.getCredentials
      - container.clusters.list
      - container.deployments.create
      - secretmanager.secrets.create
      - secretmanager.versions.add
      - monitoring.timeSeries.list
    """
)

# CLI tools the runbook needs, and how to install each if missing.
TOOL_INSTALL = {
    "kubectl": ["gcloud", "components", "install", "kubectl", "--quiet"],
    "helm": ["bash", "-c", "curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"],
    "jq": ["bash", "-c", "sudo apt-get update -y && sudo apt-get install -y jq"],
    "yq": ["bash", "-c", "sudo wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && sudo chmod +x /usr/local/bin/yq"],
    "unzip": ["bash", "-c", "sudo apt-get update -y && sudo apt-get install -y unzip"],
    "curl": ["bash", "-c", "sudo apt-get update -y && sudo apt-get install -y curl"],
}


# --------------------------------------------------------------------------- #
# Event helpers                                                               #
# --------------------------------------------------------------------------- #
def _step(key: str, state: str, label: str = "", detail: str = "") -> None:
    event_bus.publish({"type": "onb_step", "key": key, "state": state, "label": label, "detail": detail})


def _log(text: str, level: str = "info") -> None:
    event_bus.publish({"type": "onb_log", "level": level, "text": text})


# --------------------------------------------------------------------------- #
# Inputs + result                                                             #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class OnboardInputs:
    project_id: str
    dynatrace_url: str
    dynatrace_access_key: str
    cluster_name: str = "dynatrace-gcp-monitor"
    region: str = "us-central1"
    topic_name: str = "dynatrace-gcp-logs"
    subscription_name: str = "dynatrace-gcp-logs-sub"
    deployment_type: str = "all"
    log_filter: str = ""  # optional GCP logging filter for the export sink
    execute: bool = False  # dry-run unless explicitly turned on


@dataclass(slots=True)
class CmdResult:
    ok: bool
    cmd: list[str]
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    dry_run: bool = False
    healed_by: list[str] = field(default_factory=list)

    @property
    def combined(self) -> str:
        return f"{self.stdout}\n{self.stderr}".strip()


# --------------------------------------------------------------------------- #
# Self-healing command runner                                                 #
# --------------------------------------------------------------------------- #
class HealingRunner:
    """Runs shell commands and auto-remediates a library of known failures.

    In dry-run mode commands are recorded and reported as planned, not executed;
    self-healing is described but not triggered (there is no live error to react to).
    """

    def __init__(self, inputs: OnboardInputs):
        self.inputs = inputs
        self.execute = inputs.execute
        self.planned: list[list[str]] = []
        self._remediations = self._build_remediations()

    # -- raw exec ---------------------------------------------------------- #
    def _exec(self, cmd: list[str], stdin: str | None = None, timeout: int = 1200) -> CmdResult:
        exe = shutil.which(cmd[0]) or (shutil.which(cmd[0] + ".cmd") if cmd else None) or cmd[0]
        try:
            proc = subprocess.run(
                [exe, *cmd[1:]], input=stdin, capture_output=True, text=True, timeout=timeout
            )
            return CmdResult(
                ok=proc.returncode == 0,
                cmd=cmd,
                exit_code=proc.returncode,
                stdout=(proc.stdout or "")[-4000:],
                stderr=(proc.stderr or "")[-4000:],
            )
        except FileNotFoundError:
            return CmdResult(ok=False, cmd=cmd, exit_code=127, stderr=f"{cmd[0]}: command not found")
        except subprocess.TimeoutExpired:
            return CmdResult(ok=False, cmd=cmd, exit_code=124, stderr=f"timed out after {timeout}s")
        except Exception as exc:  # pragma: no cover
            return CmdResult(ok=False, cmd=cmd, exit_code=1, stderr=str(exc)[:500])

    # -- public: run with healing ----------------------------------------- #
    def run(
        self,
        cmd: list[str],
        stdin: str | None = None,
        ok_if: Callable[[CmdResult], bool] | None = None,
        max_heal_attempts: int = 3,
    ) -> CmdResult:
        """Run a command; on failure, try to heal and retry up to N times."""
        self.planned.append(cmd)
        printable = " ".join(cmd)
        if not self.execute:
            _log(f"[dry-run] {printable}", "info")
            return CmdResult(ok=True, cmd=cmd, dry_run=True, stdout="(dry-run: not executed)")

        _log(f"$ {printable}", "info")
        result = self._exec(cmd, stdin=stdin)
        if ok_if and ok_if(result):
            result.ok = True
        healed: list[str] = []
        attempts = 0
        while not result.ok and attempts < max_heal_attempts:
            remedy = self._match_remedy(result)
            if remedy is None:
                _log(f"✗ no known fix for: {result.stderr[:300]}", "error")
                break
            attempts += 1
            _log(f"✻ self-heal: {remedy.name} — {remedy.why}", "fix")
            remedy.apply(self, result)
            healed.append(remedy.name)
            _log(f"↻ retrying: {printable}", "info")
            result = self._exec(cmd, stdin=stdin)
            if ok_if and ok_if(result):
                result.ok = True
        result.healed_by = healed
        _log(("✓ " if result.ok else "✗ ") + printable, "info" if result.ok else "error")
        return result

    # -- remediation library ---------------------------------------------- #
    def _match_remedy(self, result: CmdResult) -> "Remediation | None":
        blob = result.combined
        for rem in self._remediations:
            m = rem.pattern.search(blob)
            if m:
                rem.match = m
                return rem
        return None

    def _build_remediations(self) -> list["Remediation"]:
        proj = self.inputs.project_id

        def fix_enable_api(runner: "HealingRunner", res: CmdResult, m: re.Match) -> None:
            api = m.group("api") if m and "api" in m.groupdict() and m.group("api") else None
            apis = [api] if api else REQUIRED_APIS
            runner._exec(["gcloud", "services", "enable", *apis, "--project", proj])
            time.sleep(3)

        def fix_iam(runner: "HealingRunner", res: CmdResult, m: re.Match) -> None:
            ensure_deploy_role(runner, proj)
            account = current_account(runner)
            if account:
                runner._exec([
                    "gcloud", "projects", "add-iam-policy-binding", proj,
                    f"--member=user:{account}",
                    f"--role=projects/{proj}/roles/{DEPLOY_ROLE_ID}",
                ])

        def fix_install_tool(runner: "HealingRunner", res: CmdResult, m: re.Match) -> None:
            tool = res.cmd[0]
            install = TOOL_INSTALL.get(tool)
            if install:
                runner._exec(install)

        def fix_get_creds(runner: "HealingRunner", res: CmdResult, m: re.Match) -> None:
            runner._exec([
                "gcloud", "container", "clusters", "get-credentials", self.inputs.cluster_name,
                "--region", self.inputs.region, "--project", proj,
            ])

        return [
            Remediation(
                "enable-api",
                re.compile(
                    r"(?:SERVICE_DISABLED|has not been used in project|accessNotConfigured|"
                    r"API \[?(?P<api>[a-z][a-z0-9.\-]*\.googleapis\.com)\]? not enabled)",
                    re.I,
                ),
                "a required GCP API is disabled — enabling it",
                fix_enable_api,
            ),
            Remediation(
                "grant-iam",
                re.compile(r"PERMISSION_DENIED|caller does not have permission|"
                           r"does not have .*permission|Required '[^']+' permission", re.I),
                "missing deployment permission — creating/binding the custom role",
                fix_iam,
            ),
            Remediation(
                "install-tool",
                re.compile(r"command not found|not found in PATH|No such file or directory", re.I),
                "a required CLI tool is missing — installing it",
                fix_install_tool,
            ),
            Remediation(
                "cluster-credentials",
                re.compile(r"Unable to connect to the server|connection refused|"
                           r"no configuration has been provided|current-context.*not", re.I),
                "kubectl has no cluster credentials — fetching them",
                fix_get_creds,
            ),
        ]


@dataclass
class Remediation:
    name: str
    pattern: re.Pattern
    why: str
    _apply: Callable[["HealingRunner", CmdResult, re.Match], None]
    match: re.Match | None = None

    def apply(self, runner: "HealingRunner", result: CmdResult) -> None:
        self._apply(runner, result, self.match)


# --------------------------------------------------------------------------- #
# Small gcloud helpers                                                         #
# --------------------------------------------------------------------------- #
def current_account(runner: HealingRunner) -> str:
    if not runner.execute:
        return "you@example.com"
    res = runner._exec(["gcloud", "config", "get-value", "account"])
    acct = (res.stdout or "").strip()
    return acct if acct and "unset" not in acct.lower() else ""


def ensure_deploy_role(runner: HealingRunner, project_id: str) -> None:
    """Create the custom deployment role if it does not already exist."""
    exists = runner._exec([
        "gcloud", "iam", "roles", "describe", DEPLOY_ROLE_ID, "--project", project_id,
    ]).ok if runner.execute else False
    if exists:
        return
    import tempfile
    import os
    path = os.path.join(tempfile.gettempdir(), "dynatrace-gcp-monitor-helm-deployment-role.yaml")
    if runner.execute:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(DEPLOY_ROLE_YAML)
    runner.run([
        "gcloud", "iam", "roles", "create", DEPLOY_ROLE_ID,
        "--project", project_id, f"--file={path}",
    ], ok_if=lambda r: "already exists" in r.combined.lower())


# --------------------------------------------------------------------------- #
# Steps                                                                        #
# --------------------------------------------------------------------------- #
def step_preflight(runner: HealingRunner) -> dict[str, Any]:
    _step("preflight", "active", "Preflight")
    inp = runner.inputs
    runner.run(["gcloud", "config", "set", "project", inp.project_id])
    # Enable APIs up front so later steps don't trip on a disabled service.
    runner.run(["gcloud", "services", "enable", *REQUIRED_APIS, "--project", inp.project_id])
    # Ensure the runbook's CLI tools exist; self-heal installs any that are missing.
    for tool in ("kubectl", "helm", "jq", "yq", "unzip"):
        runner.run([tool, "version"], ok_if=lambda r: r.exit_code in (0, 1, 2))
    _step("preflight", "done", "Preflight")
    return {"step": "preflight", "apis": REQUIRED_APIS}


def step_iam(runner: HealingRunner) -> dict[str, Any]:
    _step("iam", "active", "Custom IAM role")
    inp = runner.inputs
    ensure_deploy_role(runner, inp.project_id)
    account = current_account(runner)
    if account:
        runner.run([
            "gcloud", "projects", "add-iam-policy-binding", inp.project_id,
            f"--member=user:{account}",
            f"--role=projects/{inp.project_id}/roles/{DEPLOY_ROLE_ID}",
        ])
    _step("iam", "done", "Custom IAM role")
    return {"step": "iam", "role": DEPLOY_ROLE_ID, "member": account}


def step_pubsub(runner: HealingRunner) -> dict[str, Any]:
    _step("pubsub", "active", "Pub/Sub for logs")
    inp = runner.inputs
    runner.run(["bash", "-c", f"wget -q {PUBSUB_SCRIPT_URL} -O deploy-pubsub.sh && chmod +x deploy-pubsub.sh"])
    runner.run([
        "bash", "-c",
        f"./deploy-pubsub.sh --topic-name {inp.topic_name} --subscription-name {inp.subscription_name}",
    ], ok_if=lambda r: "already exists" in r.combined.lower())
    _step("pubsub", "done", "Pub/Sub for logs")
    return {"step": "pubsub", "topic": inp.topic_name, "subscription": inp.subscription_name}


def step_logsink(runner: HealingRunner) -> dict[str, Any]:
    _step("logsink", "active", "Log export sink")
    inp = runner.inputs
    topic = f"pubsub.googleapis.com/projects/{inp.project_id}/topics/{inp.topic_name}"
    args = [
        "gcloud", "logging", "sinks", "create", "dynatrace-gcp-logs-sink", topic,
        "--project", inp.project_id,
    ]
    if inp.log_filter:
        args += [f"--log-filter={inp.log_filter}"]
    runner.run(args, ok_if=lambda r: "already exists" in r.combined.lower())
    _log("Grant the sink's writer identity Pub/Sub Publisher on the topic if logs don't flow.", "warn")
    _step("logsink", "done", "Log export sink")
    return {"step": "logsink", "sink": "dynatrace-gcp-logs-sink"}


def step_helm_package(runner: HealingRunner) -> dict[str, Any]:
    _step("helm_pkg", "active", "Helm package")
    runner.run([
        "bash", "-c",
        f'wget -q "{HELM_PACKAGE_URL}" -O helm-deployment-package.tar '
        f"&& tar -xf helm-deployment-package.tar "
        f"&& chmod +x helm-deployment-package/deploy-helm.sh",
    ])
    _step("helm_pkg", "done", "Helm package")
    return {"step": "helm_pkg", "package": "helm-deployment-package.tar"}


def step_values(runner: HealingRunner) -> dict[str, Any]:
    _step("values", "active", "values.yaml")
    inp = runner.inputs
    values = dedent(
        f"""\
        gcpProjectId: "{inp.project_id}"
        deploymentType: "{inp.deployment_type}"
        dynatraceAccessKey: "{inp.dynatrace_access_key}"
        dynatraceUrl: "{inp.dynatrace_url}"
        logsSubscriptionId: "{inp.subscription_name}"
        requireValidCertificate: true
        """
    )
    target = "helm-deployment-package/dynatrace-gcp-monitor/values.yaml"
    safe = values.replace(inp.dynatrace_access_key, "***REDACTED***") if inp.dynatrace_access_key else values
    _log("Writing values.yaml (access key redacted in logs):\n" + safe, "info")
    if runner.execute:
        runner.run(["bash", "-c", f"cat > {target} <<'EOF'\n{values}\nEOF"])
    else:
        runner.planned.append(["bash", "-c", f"cat > {target} <<'EOF' ... EOF"])
    _step("values", "done", "values.yaml")
    return {"step": "values", "path": target}


def step_deploy(runner: HealingRunner) -> dict[str, Any]:
    _step("deploy", "active", "Create Autopilot cluster + deploy")
    inp = runner.inputs
    cmd = (
        f"cd helm-deployment-package && ./deploy-helm.sh --create-autopilot-cluster "
        f"--autopilot-cluster-name {inp.cluster_name}"
    )
    res = runner.run(["bash", "-c", cmd], ok_if=lambda r: "already exists" in r.combined.lower())
    runner.run([
        "gcloud", "container", "clusters", "get-credentials", inp.cluster_name,
        "--region", inp.region, "--project", inp.project_id,
    ])
    _step("deploy", "done" if res.ok else "failed", "Create Autopilot cluster + deploy")
    return {"step": "deploy", "cluster": inp.cluster_name, "ok": res.ok, "healed_by": res.healed_by}


def step_verify_pods(runner: HealingRunner) -> dict[str, Any]:
    _step("verify_pods", "active", "Verify pods")
    res = runner.run(["kubectl", "-n", "dynatrace", "get", "pods"])
    running = "Running" in res.stdout or runner.execute is False
    _step("verify_pods", "done" if running else "failed", "Verify pods")
    return {"step": "verify_pods", "running": running, "output": res.stdout[:600]}


def step_verify_dynatrace(runner: HealingRunner) -> dict[str, Any]:
    """Confirm GCP data is landing in Grail via the Dynatrace MCP (honest signal)."""
    _step("verify_dt", "active", "Verify in Dynatrace (MCP)")
    inp = runner.inputs
    if not runner.execute:
        _log("[dry-run] would verify GCP data in Grail via the Dynatrace MCP "
             "(filter cloud.provider == \"gcp\").", "info")
        _step("verify_dt", "done", "Verify in Dynatrace (MCP)")
        return {"step": "verify_dt", "logs_30m": None, "metrics_seen": None, "has_data": None}
    cfg = get_config()
    cfg.dt_environment = inp.dynatrace_url or cfg.dt_environment
    log_count = metric_seen = None
    try:
        rows = query_dql(
            'fetch logs, from:now()-30m | filter cloud.provider == "gcp" | summarize c = count()', cfg
        )
        log_count = rows[0].get("c") if rows else 0
    except Exception as exc:
        _log(f"log verify query failed: {exc}", "warn")
    try:
        rows = query_dql(
            'timeseries c = count(), by:{dt.entity.cloud_application}, from:now()-30m', cfg
        )
        metric_seen = bool(rows)
    except Exception as exc:
        _log(f"metric verify query failed: {exc}", "warn")
    has_data = bool(log_count) or bool(metric_seen)
    _step("verify_dt", "done" if has_data else "failed", "Verify in Dynatrace (MCP)")
    if not has_data and runner.execute:
        _log(
            "Pods are up but Grail shows no GCP data yet. Ingest can lag a few minutes; "
            "if it persists, confirm the tenant retains OTel/GCP data and the access key "
            "has the 'GCP Services Monitoring' scopes. No code change needed afterward.",
            "warn",
        )
    return {"step": "verify_dt", "logs_30m": log_count, "metrics_seen": metric_seen, "has_data": has_data}


# --------------------------------------------------------------------------- #
# Orchestrator (the single ADK tool)                                          #
# --------------------------------------------------------------------------- #
def onboard_gke_autopilot(
    project_id: str,
    dynatrace_url: str,
    dynatrace_access_key: str,
    cluster_name: str = "dynatrace-gcp-monitor",
    region: str = "us-central1",
    topic_name: str = "dynatrace-gcp-logs",
    subscription_name: str = "dynatrace-gcp-logs-sub",
    deployment_type: str = "all",
    log_filter: str = "",
    execute: bool = False,
) -> dict[str, Any]:
    """Single-click, self-healing Dynatrace GCP onboarding on a NEW GKE Autopilot cluster.

    Dry-run by default (prints the exact commands). Set execute=True to run live.
    Returns a structured result with every step, any self-heals applied, and the
    Dynatrace verification outcome.
    """
    inputs = OnboardInputs(
        project_id=project_id,
        dynatrace_url=dynatrace_url,
        dynatrace_access_key=dynatrace_access_key,
        cluster_name=cluster_name,
        region=region,
        topic_name=topic_name,
        subscription_name=subscription_name,
        deployment_type=deployment_type,
        log_filter=log_filter,
        execute=execute,
    )
    runner = HealingRunner(inputs)
    mode = "LIVE" if execute else "DRY-RUN"
    _log(f"Starting Dynatrace→GCP onboarding on a new GKE Autopilot cluster [{mode}]", "info")

    steps: list[dict[str, Any]] = []
    for fn in (
        step_preflight, step_iam, step_pubsub, step_logsink,
        step_helm_package, step_values, step_deploy, step_verify_pods, step_verify_dynatrace,
    ):
        steps.append(fn(runner))

    healed = sorted({h for s in steps for h in s.get("healed_by", [])})
    verify = steps[-1]
    ok = all(s.get("ok", True) for s in steps) and (verify.get("has_data") or not execute)
    summary = {
        "status": ("completed" if ok else "completed_with_warnings") if execute else "dry-run",
        "mode": mode,
        "cluster": cluster_name,
        "region": region,
        "self_heals_applied": healed,
        "verification": verify,
        "commands_planned": [" ".join(c) for c in runner.planned],
        "steps": steps,
        "note": (
            "Dry-run: review commands_planned, then re-run with execute=True." if not execute
            else "Live run complete. If has_data is false, ingest may still be propagating."
        ),
    }
    event_bus.publish({"type": "onb_done", "status": summary["status"], "summary": summary})
    _log(f"Onboarding {summary['status']} — {len(runner.planned)} commands, "
         f"{len(healed)} self-heal(s): {', '.join(healed) or 'none'}", "info")
    return summary


# --------------------------------------------------------------------------- #
# Google ADK agent                                                            #
# --------------------------------------------------------------------------- #
INSTRUCTION = dedent(
    """
    You are the Dynatrace-on-GKE Onboarding agent. Given a GCP project id, a Dynatrace
    SaaS URL (https://<env>.live.dynatrace.com) and an access token with the
    'GCP Services Monitoring' scopes, call `onboard_gke_autopilot` exactly once to set up
    the Dynatrace GCP metric + log integration on a NEW GKE Autopilot cluster.

    Default to dry-run (execute=False) and show the user the planned commands first; only
    pass execute=True when the user explicitly asks to run it live. The tool self-heals
    common failures (disabled APIs, missing IAM role/bindings, missing CLI tools, missing
    cluster credentials) and retries. Report each step, every self-heal applied, and the
    final Dynatrace verification. If verification shows has_data=false, explain that GCP
    ingest may still be propagating or the tenant must retain the data — never invent
    success, and never print the access token.
    """
).strip()

root_agent = BaseAgent(
    name="aegis_gke_onboarding_agent",
    model=config.gemini_model,
    description="Self-healing single-click Dynatrace GCP metric+log onboarding on a new GKE Autopilot cluster, verified via the Dynatrace MCP.",
    instruction=INSTRUCTION,
    tools=[FunctionTool(onboard_gke_autopilot)],
)

app = App(root_agent=root_agent, name="aegis_gke_onboarding")


def _main() -> None:
    import argparse
    import json

    p = argparse.ArgumentParser(description="Self-healing Dynatrace GCP onboarding on a new GKE Autopilot cluster")
    p.add_argument("--project", required=True)
    p.add_argument("--dt-url", required=True, help="https://<env>.live.dynatrace.com")
    p.add_argument("--dt-access-key", required=True)
    p.add_argument("--cluster-name", default="dynatrace-gcp-monitor")
    p.add_argument("--region", default="us-central1")
    p.add_argument("--topic-name", default="dynatrace-gcp-logs")
    p.add_argument("--subscription-name", default="dynatrace-gcp-logs-sub")
    p.add_argument("--deployment-type", default="all", choices=["all", "metrics", "logs"])
    p.add_argument("--log-filter", default="")
    p.add_argument("--execute", action="store_true", help="run live (default is dry-run)")
    a = p.parse_args()
    result = onboard_gke_autopilot(
        project_id=a.project,
        dynatrace_url=a.dt_url,
        dynatrace_access_key=a.dt_access_key,
        cluster_name=a.cluster_name,
        region=a.region,
        topic_name=a.topic_name,
        subscription_name=a.subscription_name,
        deployment_type=a.deployment_type,
        log_filter=a.log_filter,
        execute=a.execute,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _main()
