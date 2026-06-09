# Google Vids Audio Steps

Use this after generating the silent Playwright video.

Silent video file:

`runtime_artifacts/video/aegis-demo-silent.webm`

The video is designed to be about 2 minutes 52 seconds. The safest way to work around Google Vids input limits is to create one narration clip per scene, not one giant script.

## How To Use This In Vids

1. Open Google Vids.
2. Create a blank video.
3. Import `runtime_artifacts/video/aegis-demo-silent.webm`.
4. Keep the imported video timing unchanged.
5. Add one voice clip per scene using the short blocks below.
6. Use a calm technical narrator at a medium pace.
7. Turn captions on.
8. Export at 1080p.

## Scene Timing

| Time | Scene | Focus |
|---|---|---|
| 0:00-0:18 | Scene 1 | Problem Aegis solves |
| 0:18-0:34 | Scene 2 | Architecture and safety separation |
| 0:34-0:52 | Scene 3 | Dependency risk ranking |
| 0:52-1:06 | Scene 4 | Human approval gate |
| 1:06-1:30 | Scene 5 | Dynatrace evidence and auto-abort |
| 1:30-1:48 | Scene 6 | GitHub hardening PR |
| 1:48-2:04 | Scene 7 | Dynatrace notebook and scorecard |
| 2:04-2:24 | Scene 8 | Post-fix verification |
| 2:24-2:42 | Scene 9 | Onboarding and project awareness |
| 2:42-2:52 | Scene 10 | Closing workflow |

## Per-Scene Voice Clips

Paste these one at a time. Each block is comfortably below the 2400-character limit.

### Scene 1 voiceover

```text
Production systems fail in subtle ways, and resilience testing is often manual, risky, and hard to prove afterward. Aegis solves that by turning game day work into one supervised operator flow with evidence, safety, and follow-through.
```

### Scene 2 voiceover

```text
Aegis runs on Google Cloud with Gemini through Google ADK, Dynatrace MCP, and a deterministic Python safety loop. Gemini plans the workflow, Dynatrace supplies live observability, and Python owns the safety-critical abort decision.
```

### Scene 3 voiceover

```text
The run starts with dependency ranking. In this demo, payment to store is the highest-risk path because it is on the request path and lacks timeout and retry hardening. Aegis chooses the target from evidence instead of static rules.
```

### Scene 4 voiceover

```text
Before anything mutates, Aegis asks for human approval. The operator can inspect the target, the injected latency, and the exact rollback condition. That keeps the experiment supervised and auditable.
```

### Scene 5 voiceover

```text
During the test, Aegis injects controlled latency and watches burn rate through Dynatrace. When burn crosses the threshold, the deterministic safety loop immediately rolls the fault back. The goal is to prove risk safely, not create uncontrolled impact.
```

### Scene 6 voiceover

```text
Once the weakness is proven, Aegis opens a GitHub hardening pull request. The recommendation becomes a reviewable engineering change with timeout and retry behavior, instead of ending as a chat suggestion.
```

### Scene 7 voiceover

```text
Aegis also creates a notebook-style report and scorecard. The target, injected fault, peak burn, and verdict are preserved as evidence, so SREs and application teams can review the same artifact after the run.
```

### Scene 8 voiceover

```text
Then Aegis re-runs the same experiment against the hardened path. This time, burn stays below the threshold and the verdict changes to passed. The fix is verified, not assumed.
```

### Scene 9 voiceover

```text
The onboarding dashboard solves a different problem: setup ambiguity. It shows the active Google Cloud project, the other available projects, GitHub readiness, Dynatrace readiness, and DQL checks, so the operator knows the agent is acting in the right environment.
```

### Scene 10 voiceover

```text
Aegis moves beyond chat. It detects risk, asks for approval, tests safely, auto-aborts when needed, opens a hardening PR, and verifies the fix with live observability.
```

## Matching Captions

1. `Aegis solves the proof gap in resilience testing`
2. `Gemini plans. Python enforces safety. Dynatrace verifies.`
3. `Ranks dependency risk before acting`
4. `Human approval before mutation`
5. `Dynatrace evidence plus deterministic auto-abort`
6. `Findings become a GitHub hardening PR`
7. `Notebook and scorecard preserve the evidence`
8. `The fix is verified, not assumed`
9. `Onboarding removes project and setup ambiguity`
10. `Detect risk -> approve -> inject -> harden -> verify`
