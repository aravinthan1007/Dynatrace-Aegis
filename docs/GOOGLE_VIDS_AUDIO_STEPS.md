# Google Vids Audio Steps

Use this after generating the silent Playwright video.

Silent video file:

`runtime_artifacts/video/aegis-demo-silent.webm`

The generated video is about 2 minutes 52 seconds. Use the scene timings below so the narration fills the whole video instead of ending around 2 minutes.

## Steps

1. Open Google Vids.
2. Create a new blank video.
3. Import `runtime_artifacts/video/aegis-demo-silent.webm`.
4. Keep the imported video timing unchanged.
5. Add AI voiceover using the timed script below.
6. Use a calm technical narrator at a medium-slow pace.
7. Add captions from the voiceover.
8. Export at 1080p.
9. Upload as unlisted YouTube and paste the link into Devpost.

## Scene Timing

| Time | Scene | What is on screen |
|---|---|---|
| 0:00-0:15 | Hook | Aegis dashboard, burn chart, pre/post outcome |
| 0:15-0:35 | Architecture | Cloud Run, Gemini ADK, Dynatrace MCP, deterministic safety loop |
| 0:35-0:55 | Risk ranking | Dependency table, payment->store highlighted |
| 0:55-1:10 | Approval | Human approval gate |
| 1:10-1:35 | Fault injection | Burn crosses threshold and auto-aborts |
| 1:35-1:58 | Remediation | GitHub hardening PR/code diff |
| 1:58-2:20 | Verify fix | Post-fix burn stays below threshold |
| 2:20-2:38 | Onboarding | Project-aware onboarding and readiness |
| 2:38-2:52 | Close | Detect -> Approve -> Inject -> Auto-abort -> Open PR -> Verify |

## Timed Narration Script

Paste this into Google Vids as the narration source. If Vids creates one continuous voiceover, ask it to keep a measured pace and align each paragraph to the matching time range.

```text
[0:00-0:15]
Production systems fail in subtle ways. Aegis is a Gemini-powered SRE agent that runs safe resilience game days on Google Cloud, watches error-budget burn, and verifies the outcome with Dynatrace.

[0:15-0:35]
The key design choice is separation of responsibilities. Gemini, through Google ADK, plans the workflow and decides which tools to call. Dynatrace MCP supplies live observability and DQL verification. But the safety-critical abort is deterministic Python code with a numeric threshold.

[0:35-0:55]
Aegis starts by ranking live dependency candidates. In this demo, payment-to-store is the riskiest path because it sits on the request path and lacks timeout and retry hardening. The agent chooses a target from evidence, not from a static chat answer.

[0:55-1:10]
Before anything mutates, Aegis asks for human approval. The operator can inspect the target, the injected latency, and the abort threshold. Only after approval does the experiment begin.

[1:10-1:35]
During the test, Aegis injects controlled latency and watches burn rate in real time. When burn crosses the threshold, the deterministic safety loop immediately rolls the fault back. The point is not chaos for drama. The point is proving risk safely.

[1:35-1:58]
Then Aegis closes the loop. It opens a GitHub hardening pull request that adds timeout and retry behavior to the vulnerable dependency client. The finding turns into an engineering action the team can review and merge.

[1:58-2:20]
Next, the running demo applies the hardening behavior and re-runs the same experiment. This time, burn stays below the abort threshold. The fix is verified, not assumed.

[2:20-2:38]
The dashboard also includes project-aware onboarding. It shows the active Google Cloud project, configured projects, Cloud Run service status, GitHub readiness, Dynatrace readiness, and post-onboarding DQL checks generated from curated Dynatrace skills.

[2:38-2:52]
Aegis moves beyond chat. It performs a supervised operational workflow: detect risk, request approval, inject safely, auto-abort, harden, verify, and report. For SRE teams, resilience engineering becomes repeatable, auditable, and grounded in live observability.
```

## Short Caption Set

Use these if Google Vids asks for captions separately:

1. `Aegis: Autonomous Resilience Game-Day Agent`
2. `Gemini plans. Deterministic Python enforces safety. Dynatrace verifies.`
3. `Ranks dependency risk before acting`
4. `Human approval before mutation`
5. `Auto-abort protects the SLO`
6. `Findings become a GitHub hardening PR`
7. `The fix is verified, not assumed`
8. `Project-aware onboarding with Dynatrace DQL checks`
9. `Detect risk -> test safely -> harden -> verify`
