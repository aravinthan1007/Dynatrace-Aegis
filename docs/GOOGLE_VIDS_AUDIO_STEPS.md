# Google Vids Audio Steps

Use this after generating the silent Playwright video.

Silent video file:

`runtime_artifacts/video/aegis-demo-silent.webm`

## Steps

1. Open Google Vids.
2. Create a new blank video.
3. Import `runtime_artifacts/video/aegis-demo-silent.webm`.
4. Add AI narration using the script below.
5. Keep the imported video timing unchanged.
6. Add captions from the narration.
7. Export at 1080p.
8. Upload the exported video as unlisted YouTube.
9. Paste the YouTube link into Devpost.

## Narration Script

```text
Production systems fail in subtle ways. Aegis is a Gemini-powered SRE agent that runs safe resilience game days on Google Cloud and verifies the outcome with Dynatrace.

The key design choice is separation of responsibilities. Gemini, through Google ADK, plans the workflow and decides which tools to call. Dynatrace MCP supplies live observability and DQL verification. But the safety-critical abort is deterministic Python code with a numeric threshold. The LLM never decides whether production safety is at risk.

Aegis starts by ranking live dependency candidates. In this demo, the payment-to-store path is the riskiest dependency because it sits on the request path and does not have timeout and retry hardening.

Before anything mutates, Aegis asks for human approval. The operator can inspect the planned target, injected latency, and abort threshold. Only after approval does the experiment begin.

During the test, Aegis injects controlled latency and watches error-budget burn in real time. When burn crosses the threshold, the deterministic safety loop immediately rolls the fault back.

Then Aegis closes the loop. It opens a GitHub hardening pull request that adds timeout and retry behavior to the vulnerable dependency client. The running demo applies the hardening behavior and re-runs the same experiment.

This time, burn stays under the threshold. The fix is verified, not assumed.

The dashboard also includes project-aware onboarding. It shows the active Google Cloud project, configured projects, Cloud Run service status, GitHub readiness, Dynatrace readiness, and post-onboarding DQL checks generated from curated Dynatrace skills.

Aegis moves beyond chat. It performs a supervised operational workflow: detect risk, request approval, inject safely, auto-abort, harden, verify, and report.

For SRE teams, resilience engineering becomes repeatable, auditable, and grounded in live observability.
```
