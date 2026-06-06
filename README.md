# Aegis

Aegis is an autonomous resilience game-day agent for the Dynatrace track of the Google Cloud Rapid Agent Hackathon. It inspects a live demo microservice via the Dynatrace MCP server, proposes a fault-injection hypothesis with Gemini, runs the experiment with a deterministic safety loop, and can open follow-up hardening actions.

## Why this concept is strong

- It has a clear hero moment: inject fault, watch burn rise, auto-abort, and show the abort live.
- It uses Dynatrace meaningfully for topology, DQL, events, and notebook-style reporting.
- It takes real actions beyond chat: chaos injection, safety stop, GitHub PR creation, and optional Slack notification.
- The strongest judge-facing design choice is explicit: the safety brake is deterministic Python code, not an LLM call.

## Winnability assessment

This idea is winnable if the demo is crisp. The biggest scoring unlocks are:

1. The burn-rate signal must react within seconds.
2. The abort moment must be visible and trustworthy.
3. The GitHub hardening PR must be real, not mocked.

The main risk is not originality. The main risk is execution drift if Dynatrace DQL or MCP setup slows you down. To reduce that risk, this implementation includes a local fallback SLI path so you can finish the demo loop before tenant tuning is complete.

## Current implementation status

- Phase 0: scaffold complete
- Phase 1: demo app, chaos control, local telemetry hooks, load generator scaffolded
- Phase 2: burn-rate helper implemented with Dynatrace-first and local-fallback paths
- Phase 3: deterministic experiment runner with hard abort and cleanup implemented
- Phase 4+: ADK agent, approval gate, dashboard, GitHub/Slack actions scaffolded with dry-run safe fallbacks

## Architecture

```text
[Load generator] --> [Demo app: frontend -> payment -> store]
                           |                 |
                           |                 +--> /chaos fault injection
                           |                 +--> local metrics buffer
                           v
                     [Dynatrace OTLP]
                           ^
                           |
[Aegis ADK agent + Gemini] +--> Dynatrace MCP
        |
        +--> deterministic run_experiment()
        +--> GitHub PR action
        +--> Slack action
        v
[Dashboard] <--> SSE reasoning feed + live burn chart + approval/abort UI
```

## Safety rule

The abort path is deterministic code. Gemini can choose the target, design the hypothesis, and write the scorecard, but the inject -> poll burn -> abort loop runs in plain Python with a numeric threshold. This keeps the safety-critical path auditable and fast.

## Quick start

1. Copy `.env.example` to `.env` and fill in the credentials you have.
2. Install dependencies:

```bash
pip install -r requirements.txt
pip install -r demo_app/requirements.txt
```

3. Start the demo app:

```bash
uvicorn demo_app.main:app --reload --port 8001
```

4. Start the dashboard:

```bash
uvicorn dashboard.server:app --reload --port 8000
```

5. Start steady traffic:

```bash
python loadgen/loadgen.py --base-url http://127.0.0.1:8001 --rps 20
```

6. Open `http://127.0.0.1:8000`.

## Notes

- If Dynatrace MCP is not configured yet, Aegis falls back to the demo app's recent request metrics so you can still validate the core loop.
- `open_github_pr` and `post_slack` return dry-run payloads when credentials are missing.
- The hardening PR content targets `demo_app/payment_client.py` by adding timeout and retry behavior.
