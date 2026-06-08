# Google Cloud Rapid Agent Hackathon Submission

## Devpost Fields

### Project name

Aegis - Autonomous Resilience Game-Day Agent

### Tagline

Gemini plans the resilience game day; deterministic Python safely injects, aborts, hardens, and verifies with Dynatrace MCP.

### Track

Dynatrace

### Hosted project URL

https://aegis-dashboard-948868496451.us-central1.run.app

### Source code URL

https://github.com/aravinthan1007/Dynatrace-Aegis

### Demo video URL

TBD after recording and upload.

## Short Description

Aegis is an autonomous SRE agent for production-style resilience game days. It uses Gemini on Google Cloud to reason over live service dependency risk, asks for human approval, injects a controlled fault, and lets a deterministic Python safety loop auto-abort the experiment when error-budget burn crosses the threshold. After proving the weakness, Aegis opens a GitHub hardening PR, applies the fix in the running demo, re-runs the same experiment, and publishes a Dynatrace-backed report.

## Full Description

Modern SRE teams need more than alerting. They need safe, auditable agents that can find risk, act under human oversight, and prove remediation worked. Aegis solves that workflow.

The agent ranks live dependency candidates from the demo service, asks the operator to approve a game day, injects latency on the riskiest path, and watches burn rate in real time. The safety-critical abort is deliberately not left to the LLM: it is deterministic Python code with a numeric threshold. Gemini drives the tool workflow and writes the narrative, while Dynatrace MCP provides the live observability superpower through DQL, service data, and report generation.

The closed loop is the key: Aegis does not stop at "something is wrong." It proves the vulnerability, rolls the fault back, opens a real GitHub hardening PR, applies timeout/retry hardening, and re-runs the test to verify the fix holds.

## How It Uses Google Cloud

- Cloud Run hosts the dashboard and demo application.
- Gemini runs through Google ADK/Vertex AI configuration to drive the agent workflow.
- Cloud Build builds and deploys the services.
- Secret Manager stores sensitive tokens used by the deployed service.
- Cloud Monitoring data can be bridged into Dynatrace for infrastructure signals.

## How It Uses Dynatrace

- Dynatrace MCP is used for live DQL verification and observability enrichment.
- The demo app emits OpenTelemetry telemetry into Dynatrace.
- Aegis generates Dynatrace-backed notebook/report output.
- Curated Dynatrace skill context produces post-onboarding DQL checks for GCP, GKE, logs, services, and DAVIS problems.

## How It Moves Beyond Chat

Aegis uses tools to perform a multi-step mission:

1. Rank risky service dependencies.
2. Request human approval.
3. Inject a controlled fault.
4. Auto-abort when burn rate exceeds the SLO safety threshold.
5. Open a hardening PR in GitHub.
6. Apply the hardening behavior.
7. Re-run the experiment and verify the fix.
8. Publish a scorecard/report.

The agent is not just answering questions; it is carrying out a supervised operational workflow.

## What Judges Should Try

1. Open the hosted dashboard.
2. Click `Run Game Day`.
3. Approve the injection when prompted.
4. Watch burn rate cross the threshold and auto-abort.
5. Observe the hardening PR/fallback issue link and post-fix verification.
6. Open `/onboard` to see the current Google Cloud project, all configured projects, Dynatrace readiness, GitHub readiness, and post-onboarding DQL checks.

## Compliance Checklist

| Requirement | Status | Evidence |
|---|---:|---|
| Hosted project URL | Done | Cloud Run dashboard URL above |
| Public open-source repository | Done | GitHub repo is public |
| Detectable open-source license | Done | MIT license is detected by GitHub |
| Partner track selected | Ready | Dynatrace |
| Partner MCP integration | Done | Dynatrace MCP client and live DQL checks |
| Google Cloud AI usage | Done | Gemini via Google ADK/Vertex AI configuration |
| Multi-step agent actions | Done | approve, inject, abort, PR, harden, verify, report |
| Web platform | Done | Cloud Run web dashboard |
| Demo video | To do | Record and upload before final Devpost submission |

## Suggested Devpost "Built With" Tags

Google Cloud, Cloud Run, Cloud Build, Secret Manager, Vertex AI, Gemini, Google ADK, Dynatrace MCP, OpenTelemetry, FastAPI, Python, GitHub API

## Final Devpost Submission Checklist

Before clicking submit:

- Paste the hosted project URL.
- Paste the public GitHub repository URL.
- Upload or paste the demo video URL.
- Select the Dynatrace track.
- Confirm the team/eligibility details.
- Confirm the project was created during the contest period.
- Confirm the repo license is visible.
