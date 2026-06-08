# Fully AI-Generated Demo Video Packet

Paste the block below into Google Vids with Veo 3.1. It is intentionally under 10,000 characters.

Optional reference images:

- `docs/video-assets/dashboard.png`
- `docs/video-assets/onboarding.png`

## Paste Into Google Vids

```text
Create a polished 2 minute 50 second hackathon demo video for "Aegis - Autonomous Resilience Game-Day Agent".

Audience: Google Cloud Rapid Agent Hackathon judges, Dynatrace track.

Style: professional enterprise SaaS demo, data-dense SRE dashboard, dark neutral UI, accessible contrast, subtle motion, crisp captions. No cartoons, mascots, sci-fi fantasy, exaggerated stock footage, secrets, private emails, or real tokens.

Core message:
Aegis is a Gemini-powered SRE agent running on Google Cloud. Gemini through Google ADK plans the workflow and calls tools. Dynatrace MCP provides live observability and DQL verification. A deterministic Python safety loop, not the LLM, controls the safety abort. Aegis ranks dependency risk, asks for human approval, injects a controlled fault, auto-aborts when error-budget burn crosses the threshold, opens a GitHub hardening PR, applies timeout/retry behavior, re-runs the test, and verifies the fix.

Scene 1, 0:00-0:15, Hook:
Show a modern SRE dashboard titled Aegis with service dependency lines and a burn-rate chart. Caption: "An agent that safely tests resilience, then proves the fix."

Scene 2, 0:15-0:35, Architecture:
Show four connected blocks: Google Cloud Run, Gemini ADK, Dynatrace MCP, Deterministic Python Safety Loop. Make the safety loop visually distinct. Caption: "Gemini plans. Python enforces safety. Dynatrace verifies."

Scene 3, 0:35-0:55, Risk ranking:
Show dependency rows frontend->payment and payment->store. Highlight payment->store as highest risk because it is on the request path and lacks timeout/retry hardening. Caption: "Aegis ranks live dependency risk before acting."

Scene 4, 0:55-1:10, Human approval:
Show an approval gate with target payment->store, latency injection, and abort threshold 10x burn. Caption: "Human-in-the-loop before mutation."

Scene 5, 1:10-1:35, Safe fault injection:
Show burn rate rising toward a yellow threshold. When it crosses, show "Auto-abort" and roll the fault back to safe. Caption: "Deterministic abort protects the SLO."

Scene 6, 1:35-1:58, Remediation:
Show a GitHub pull request titled "feat: harden payment client after Aegis game day". Show abstract code diff with timeout and retry additions. Caption: "Aegis turns findings into a hardening PR."

Scene 7, 1:58-2:20, Verify fix:
Show the experiment re-run after hardening. Burn stays below threshold and verdict changes to PASSED. Caption: "The fix is verified, not assumed."

Scene 8, 2:20-2:38, Onboarding:
Show onboarding with Google Cloud project status, four GCP projects, GitHub ready, Dynatrace ready, and DQL checks. Caption: "Project-aware onboarding and Dynatrace-skill-backed checks."

Scene 9, 2:38-2:50, Close:
Show final workflow: Detect risk -> Approve -> Inject -> Auto-abort -> Open PR -> Verify fix. Caption: "A supervised, repeatable, auditable resilience agent."

Voiceover:
Production systems fail in subtle ways. Aegis is a Gemini-powered SRE agent that runs safe resilience game days on Google Cloud and verifies the outcome with Dynatrace.

The key design choice is separation of responsibilities. Gemini, through Google ADK, plans the workflow and decides which tools to call. Dynatrace MCP supplies live observability and DQL verification. But the safety-critical abort is deterministic Python code with a numeric threshold. The LLM never decides whether production safety is at risk.

Aegis starts by ranking live dependency candidates. In this demo, the payment-to-store path is the riskiest dependency because it sits on the request path and does not have timeout and retry hardening.

Before anything mutates, Aegis asks for human approval. The operator can inspect the planned target, injected latency, and abort threshold. Only after approval does the experiment begin.

During the test, Aegis injects controlled latency and watches error-budget burn in real time. When burn crosses the threshold, the deterministic safety loop immediately rolls the fault back. The point is not to break the system for drama. The point is to prove risk safely and stop before customer impact gets out of hand.

Then Aegis closes the loop. It opens a GitHub hardening pull request that adds timeout and retry behavior to the vulnerable dependency client. The running demo applies the hardening behavior and re-runs the same experiment.

This time, burn stays under the threshold. The fix is verified, not assumed.

The dashboard also includes project-aware onboarding. It shows the active Google Cloud project, all configured projects, Cloud Run service status, GitHub readiness, Dynatrace readiness, and post-onboarding DQL checks generated from curated Dynatrace skills.

Aegis moves beyond chat. It performs a supervised operational workflow: detect risk, request approval, inject safely, auto-abort, harden, verify, and report.

For SRE teams, resilience engineering becomes repeatable, auditable, and grounded in live observability.

Include labels for Google Cloud, Gemini ADK, Dynatrace MCP, Cloud Run, Secret Manager, GitHub, OpenTelemetry, and DQL. Use calm technical narration, always-on captions, low-volume ambient music, 16:9, 1080p.
```

## Individual Veo Clip Prompts

Use these only if Google Vids asks for one prompt per clip.

1. Hook: `Professional enterprise SRE dashboard named Aegis. Dark cloud operations UI, service dependency graph, burn-rate chart, green and blue status indicators, smooth camera push-in, 16:9, 8 seconds.`
2. Architecture: `Technical architecture animation with blocks labeled Google Cloud Run, Gemini ADK, Dynatrace MCP, Deterministic Python Safety Loop. Thin data-flow lines, safety loop emphasized, 16:9, 8 seconds.`
3. Risk ranking: `Dashboard table ranking dependencies frontend->payment and payment->store. Highlight payment->store as highest risk. Show risk score, p95, bad percentage, hardened status, 16:9, 8 seconds.`
4. Approval: `Cloud operations approval modal for target payment->store, latency injection, abort threshold 10x burn, clear Approve button, no personal data, 16:9, 6 seconds.`
5. Auto-abort: `Error-budget burn chart crosses yellow threshold, Auto-abort appears, fault rolls back to safe, deterministic safety brake visual, 16:9, 8 seconds.`
6. GitHub PR: `GitHub-style pull request titled feat: harden payment client after Aegis game day. Abstract diff adds timeout and retry. No secrets, 16:9, 8 seconds.`
7. Verify: `Post-fix dashboard with burn staying below threshold. Before card says aborted, after card says passed, clean SRE UI, 16:9, 8 seconds.`
8. Onboarding: `Google Cloud and Dynatrace onboarding control panel with four projects, Cloud Run ready, GitHub ready, Dynatrace ready, DQL checks, 16:9, 8 seconds.`
9. Close: `Workflow animation: Detect risk -> Approve -> Inject -> Auto-abort -> Open PR -> Verify fix. Labels Google Cloud, Gemini ADK, Dynatrace MCP, 16:9, 8 seconds.`

## Final Export Checklist

- Under 3 minutes.
- Hosted URL appears once.
- GitHub repo URL appears once.
- Dynatrace MCP, Google Cloud, and Gemini ADK are mentioned.
- Human approval is shown before mutation.
- Deterministic safety loop is explicit.
- No secrets, tokens, personal emails, or private credentials.
- Upload as unlisted YouTube or Vimeo and paste the link into Devpost.
