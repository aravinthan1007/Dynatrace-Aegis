# Fully AI-Generated Demo Video Packet

Use this packet in Google Vids with Veo 3.1. The goal is a complete AI-generated submission video that still describes the real deployed Aegis app accurately.

Important: Devpost judges should see a product that functions as described. Keep the claims in this video aligned with the live app and repo.

## Inputs To Upload Into Google Vids

Use these optional reference images:

- `docs/video-assets/dashboard.png`
- `docs/video-assets/onboarding.png`

If Google Vids lets you attach source material, attach the dashboard screenshot first. It gives the model the actual visual style.

## One-Paste Google Vids Prompt

```text
Create a polished 2 minute 50 second hackathon demo video for a project called "Aegis - Autonomous Resilience Game-Day Agent".

Audience: Google Cloud Rapid Agent Hackathon judges, Dynatrace track.

Style: professional enterprise SaaS demo, data-dense SRE dashboard, dark neutral UI, accessible contrast, subtle motion, no cartoons, no mascots, no sci-fi fantasy, no exaggerated stock footage. Use crisp dashboard mockups, animated charts, code/terminal snippets, GitHub PR visuals, Google Cloud Run visuals, Dynatrace observability visuals, and clear captions.

Core message:
Aegis is a Gemini-powered SRE agent running on Google Cloud. Gemini through Google ADK plans the workflow and calls tools. Dynatrace MCP provides live observability and DQL verification. A deterministic Python safety loop, not the LLM, controls the safety abort. The agent finds a risky dependency, asks for human approval, injects a controlled fault, auto-aborts when error-budget burn crosses the threshold, opens a GitHub hardening PR, applies timeout and retry behavior, re-runs the experiment, and verifies the fix.

Use this exact structure:

Scene 1, 0:00-0:15, Hook:
Show a modern SRE dashboard titled Aegis. Animate service dependency lines and a burn-rate chart. Caption: "An agent that safely tests resilience, then proves the fix."

Scene 2, 0:15-0:35, Architecture:
Show four connected blocks: Google Cloud Run, Gemini ADK, Dynatrace MCP, Deterministic Safety Loop. Make the deterministic safety loop visually distinct. Caption: "Gemini plans. Python enforces safety. Dynatrace verifies."

Scene 3, 0:35-0:55, Risk ranking:
Show a table of service dependencies: frontend->payment and payment->store. Highlight payment->store as highest risk because it is on the request path and lacks timeout/retry hardening. Caption: "Aegis ranks live dependency risk before acting."

Scene 4, 0:55-1:10, Human approval:
Show an approval gate with the planned fault: inject latency, abort threshold 10x burn. Caption: "Human-in-the-loop before mutation."

Scene 5, 1:10-1:35, Safe fault injection:
Show the burn-rate chart rising toward a yellow threshold line. Then show a red/orange "Auto-abort" event that immediately rolls back the fault. Caption: "Deterministic abort protects the SLO."

Scene 6, 1:35-1:58, Remediation:
Show a GitHub pull request titled "feat: harden payment client after Aegis game day". Show code snippets for timeout and retry. Caption: "Aegis turns findings into a hardening PR."

Scene 7, 1:58-2:20, Verify fix:
Show the same experiment re-run after hardening. Burn stays below threshold and the verdict changes to PASSED. Caption: "The fix is verified, not assumed."

Scene 8, 2:20-2:38, Onboarding:
Show the onboarding control panel with Google Cloud project status, four available GCP projects, GitHub ready, Dynatrace ready, and DQL checks. Caption: "Project-aware onboarding and Dynatrace-skill-backed checks."

Scene 9, 2:38-2:50, Closing:
Show final architecture and outcome: Detect risk -> Approve -> Inject -> Auto-abort -> Open PR -> Verify fix. Caption: "A supervised, repeatable, auditable resilience agent."

Voiceover should be confident, clear, and technical. Add subtle background music, but keep narration easy to hear. Include text labels for Google Cloud, Gemini ADK, Dynatrace MCP, Cloud Run, Secret Manager, GitHub, OpenTelemetry, and DQL.

Do not claim the system is fully autonomous without human approval. Do not say the LLM makes safety decisions. Do not show fake secrets, real tokens, private emails, or personal information.
```

## Voiceover Script

Use this as the narration track. It is about 400 words, which fits just under 3 minutes at a measured demo pace.

```text
Production systems fail in subtle ways. Aegis is a Gemini-powered SRE agent that runs safe resilience game days on Google Cloud and verifies the outcome with Dynatrace.

The key design choice is separation of responsibilities. Gemini, through Google ADK, plans the workflow and decides which tools to call. Dynatrace MCP supplies live observability and DQL verification. But the safety-critical abort is deterministic Python code with a numeric threshold. The LLM never decides whether production safety is at risk.

Aegis starts by ranking live dependency candidates. In this demo, the payment-to-store path is the riskiest dependency because it sits on the request path and does not have timeout and retry hardening.

Before anything mutates, Aegis asks for human approval. The operator can inspect the planned target, injected latency, and abort threshold. Only after approval does the experiment begin.

During the test, Aegis injects controlled latency and watches error-budget burn in real time. When burn crosses the threshold, the deterministic safety loop immediately rolls the fault back. The point is not to break the system for drama. The point is to prove risk safely and stop before customer impact gets out of hand.

Then Aegis closes the loop. It opens a GitHub hardening pull request that adds timeout and retry behavior to the vulnerable dependency client. The running demo applies the hardening behavior and re-runs the same experiment.

This time, burn stays under the threshold. The fix is verified, not assumed.

The dashboard also includes project-aware onboarding. It shows the active Google Cloud project, all configured projects, Cloud Run service status, GitHub readiness, Dynatrace readiness, and post-onboarding DQL checks generated from curated Dynatrace skills.

Aegis moves beyond chat. It performs a supervised operational workflow: detect risk, request approval, inject safely, auto-abort, harden, verify, and report.

For SRE teams, that means resilience engineering becomes repeatable, auditable, and grounded in live observability.
```

## Scene-By-Scene Veo 3.1 Prompts

Generate each as a short clip if Google Vids asks for individual video prompts.

### Scene 1 - Hook

```text
Professional enterprise SRE dashboard for a product named Aegis. Dark neutral cloud operations UI, service dependency graph, burn-rate chart, green and blue status indicators, crisp text labels, no characters, no mascots. A line chart starts calm then begins rising. Smooth subtle camera push-in. 16:9, 8 seconds.
```

### Scene 2 - Architecture

```text
Clean technical architecture animation. Four connected blocks labeled Google Cloud Run, Gemini ADK, Dynatrace MCP, Deterministic Python Safety Loop. Data flows between blocks with thin glowing lines. Deterministic Safety Loop is emphasized as the guardrail. Enterprise SaaS visual style, dark background, high contrast, 16:9, 8 seconds.
```

### Scene 3 - Risk Ranking

```text
Data-dense dashboard table ranking service dependencies. Rows include frontend to payment and payment to store. Highlight payment to store as highest risk. Show columns risk score, p95 latency, bad percentage, hardened status. Professional observability dashboard style, subtle motion, 16:9, 8 seconds.
```

### Scene 4 - Approval Gate

```text
Human approval workflow in a cloud operations dashboard. A modal shows planned fault injection: target payment to store, latency injection, abort threshold 10x burn. A clear Approve button is visible but no personal data. Calm professional UI, 16:9, 6 seconds.
```

### Scene 5 - Auto-Abort

```text
Error-budget burn chart rising toward a yellow threshold line. When the line crosses the threshold, an Auto-abort status appears and the fault indicator rolls back to safe. Show deterministic safety brake as a clear system control, not AI magic. Enterprise dashboard style, 16:9, 8 seconds.
```

### Scene 6 - GitHub Hardening PR

```text
GitHub-style pull request screen in a browser. Title: feat: harden payment client after Aegis game day. Show abstract code diff with timeout and retry additions, no real secrets. Professional software engineering demo visual, 16:9, 8 seconds.
```

### Scene 7 - Verify Fix

```text
Post-fix verification dashboard. Show second experiment run with burn-rate line staying below threshold. Verdict changes to PASSED. Show before and after comparison cards: Pre-fix aborted, Post-fix passed. Clean SRE dashboard style, 16:9, 8 seconds.
```

### Scene 8 - Onboarding

```text
Onboarding control panel for Google Cloud and Dynatrace. Show four configured Google Cloud projects, Cloud Run service ready, GitHub ready, Dynatrace ready, and DQL checks. Professional enterprise dashboard UI, dark neutral colors, readable labels, 16:9, 8 seconds.
```

### Scene 9 - Closing

```text
Final workflow animation with six connected steps: Detect risk, Approve, Inject, Auto-abort, Open PR, Verify fix. Add small labels Google Cloud, Gemini ADK, Dynatrace MCP. Clean enterprise hackathon demo closing, subtle motion, 16:9, 8 seconds.
```

## Captions

Use these on-screen captions:

1. `Aegis: Autonomous Resilience Game-Day Agent`
2. `Gemini plans. Deterministic Python enforces safety. Dynatrace verifies.`
3. `Ranks live dependency risk before acting`
4. `Human approval before mutation`
5. `Auto-abort protects the SLO`
6. `Findings become a GitHub hardening PR`
7. `The fix is verified, not assumed`
8. `Project-aware onboarding with Dynatrace DQL checks`
9. `Detect risk -> test safely -> harden -> verify`

## Music And Voice Settings

- Voice: calm technical narrator, medium pace.
- Music: low-volume modern ambient technology bed.
- Captions: always on.
- Aspect ratio: 16:9.
- Resolution: 1080p.
- Length: 2:45 to 2:55.

## Final Export Checklist

- Video is under 3 minutes.
- Hosted URL appears once.
- GitHub repo URL appears once.
- Dynatrace MCP is mentioned.
- Google Cloud and Gemini ADK are mentioned.
- Human approval is shown before mutation.
- Deterministic safety loop is explicitly described.
- No secrets, tokens, personal emails, or private project credentials appear.
- Upload as unlisted YouTube or Vimeo and paste the link into Devpost.
