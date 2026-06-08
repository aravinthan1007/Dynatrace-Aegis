# Aegis — Autonomous Resilience Game-Day Agent

Aegis is an autonomous SRE agent for the **Google Cloud × Dynatrace** hackathon. It
finds the riskiest service dependency, runs a **safe** chaos experiment, and — the
core idea — **the safety brake is deterministic Python code, not an LLM call.** Gemini
designs the experiment and writes the report; a plain numeric loop injects the fault,
watches the error‑budget burn, and **auto‑aborts** the instant it crosses a threshold.

**Live demo:** https://aegis-dashboard-948868496451.us-central1.run.app
(click **Run Game Day**, approve, watch burn rise → abort → fix → verify; or **Run Fail Scenario**.)

Built on **Google ADK** (agent runs on **Gemini 3.5 Flash via Vertex AI**) and the
**Dynatrace MCP server** (live DQL / Davis / problems).

---

## What it does (the closed loop)

1. **Rank** — scores live dependency candidates by measured risk (bad‑ratio, p95, hardening).
2. **Approve** — human‑in‑the‑loop gate before any mutation.
3. **Inject** — adds latency on the chosen dependency; a realtime burn‑rate signal climbs.
4. **Auto‑abort** — deterministic loop rolls the fault back when burn ≥ threshold.
5. **Harden** — opens a real GitHub PR adding timeout + retry to the dependency client.
6. **Verify** — re‑runs against the fixed service to confirm the fix holds (**pass**),
   or honestly reports it doesn't (**fail scenario**, e.g. latency that retry can't fix).
7. **Report** — creates a **Gemini‑authored Dynatrace notebook** (narrative + live DQL graphs).

## Why each design choice matters

- **Deterministic safety brake.** The inject→poll→abort loop is auditable Python with a
  numeric threshold — the LLM never gates safety. (`aegis_agent/experiment.py`)
- **Genuinely agentic.** Gemini (via the ADK `Runner` on Vertex) drives the tools; target
  selection is data‑driven, not hardcoded. (`aegis_agent/agent.py`)
- **Real Dynatrace integration.** Headless OAuth client‑credentials → the MCP runs live
  DQL from Cloud Run (`/dt-check` proves it).
- **Honest by design.** Verification reports `has_data:false` rather than faking success;
  evals catch ungrounded behavior.

## Components

| Path | What |
|---|---|
| `aegis_agent/agent.py` | ADK root agent, deterministic orchestration, ADK Runner path |
| `aegis_agent/experiment.py` | Deterministic inject→poll→**abort** safety loop |
| `aegis_agent/dynatrace.py` | Dynatrace MCP client, burn sampler (realtime local SLI + DQL) |
| `aegis_agent/dynatrace_skills.py` | Curated Dynatrace skill context + post-onboarding DQL checks |
| `aegis_agent/onboarding/agent.py` | **Single‑click, secure Dynatrace‑on‑GCP onboarding agent** |
| `aegis_agent/evalagent/` + `tests/` | ADK `AgentEvaluator` + hermetic decision evals + grounding gate |
| `dashboard/` | Guided‑pipeline UI + SSE + `/onboard`, `/dt-check`, `/run-agent`, `/run-fail` |
| `demo_app/` | Instrumented microservice (OTLP traces + delta metrics) + chaos controls |

## The onboarding agent (Helm‑free)

A second ADK agent turns the painful Dynatrace‑on‑GCP setup into one self‑verifying call:
enable APIs → store the OTLP token in **GCP Secret Manager** → wire Cloud Run OTLP (delta
metrics) from the secret → **bridge Cloud Run platform metrics to Dynatrace (no Helm/GKE)**
→ **verify via the Dynatrace MCP**. Auto‑remediates a disabled API and retries.
Curated Dynatrace skills provide post-onboarding DQL checks for GCP, GKE, logs,
services, and DAVIS problems without replacing the deterministic `gcloud` tools.

```bash
python -m aegis_agent.onboarding.agent \
  --project <PROJECT> --region us-central1 --services aegis-demo-app \
  --dt-environment https://<tenant>.apps.dynatrace.com \
  --dt-otlp-token <INGEST_TOKEN> --runtime-sa <RUNTIME_SA> \
  --oauth-client-id <DT0S02_ID> --oauth-client-secret <SECRET>
```

## Run locally

```bash
pip install -r requirements.txt -r demo_app/requirements.txt
uvicorn demo_app.main:app --port 8001 &
uvicorn dashboard.server:app --port 8000 &
python loadgen/loadgen.py --base-url http://127.0.0.1:8001 --rps 20
# open http://127.0.0.1:8000
```

## Tests & evals

```bash
pytest tests/ -q                                     # abort-path + hermetic decision evals (green)
RUN_ADK_EVAL=1 pytest tests/test_agent_eval.py        # ADK AgentEvaluator (needs google-adk[eval])
RUN_GROUNDING_EVAL=1 pytest tests/test_grounding.py   # data-grounding gate
```

## Submission

- Devpost packet: `docs/HACKATHON_SUBMISSION.md`
- Demo video guide: `docs/DEMO_VIDEO_GUIDE.md`

## Cloud Run

```bash
gcloud run deploy aegis-dashboard --source . --region us-central1 --allow-unauthenticated
gcloud run deploy aegis-demo-app  --source . --region us-central1 --allow-unauthenticated
```

## Notes

- Falls back to a realtime local SLI when Grail has no data yet, so the demo always works.
- Secrets live in Secret Manager / env, never in the repo (`.env` is gitignored).
- On a Dynatrace tenant that retains OTLP, the notebook charts populate and the grounding
  eval goes green with **zero code changes**.
- GitHub, Google Cloud, and Dynatrace access needed for live operations is listed in
  `docs/ACCESS_REQUIREMENTS.md`.
