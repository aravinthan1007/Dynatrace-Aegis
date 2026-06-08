# Demo Video Guide

Target length: 2:45 to 3:00.

Recommended approach for your current plan: generate the full video in Google Vids with Veo 3.1, using the prompts in `docs/AI_VIDEO_PRODUCTION_PACKET.md`.

Keep the claims aligned with the real deployed app. A fully AI-generated video is fine for polish, but the product still must function as described.

## Tools

- Screen recording: OBS, QuickTime, Windows Xbox Game Bar, or Google Meet recording.
- AI video polish: Google Vids or Veo on Vertex AI.
- Editing: Google Vids, CapCut, DaVinci Resolve, or YouTube Studio.

Because the hackathon rules limit AI tooling, prefer Google AI tools for any generated video assets.

## Three-Minute Structure

### 0:00-0:15 - Hook

Show the dashboard.

Voiceover:

> Production systems fail in subtle ways. Aegis is a Gemini-powered SRE agent that finds the riskiest dependency, runs a safe chaos game day, auto-aborts when error-budget burn gets dangerous, and proves the fix with Dynatrace.

### 0:15-0:35 - Architecture

Show README or a simple slide.

Must say:

- Google Cloud Run hosts the agent and demo app.
- Gemini through Google ADK drives the tool workflow.
- Dynatrace MCP provides live observability and DQL verification.
- The safety abort is deterministic Python, not an LLM decision.

### 0:35-1:35 - Live Game-Day Flow

Show:

1. Click `Run Game Day`.
2. Agent ranks dependencies.
3. Click approve.
4. Burn chart rises.
5. Auto-abort fires.

Voiceover:

> Gemini plans the game day, but Aegis keeps a human in the loop before mutation. Once approved, the deterministic loop watches burn rate and rolls back the fault immediately when it crosses the SLO threshold.

### 1:35-2:20 - Closed Loop Remediation

Show:

1. GitHub PR or fallback issue link.
2. Hardening step.
3. Verify re-run.
4. Passed verdict.

Voiceover:

> Aegis does not stop at alerting. It opens a hardening PR, applies timeout and retry behavior in the running demo, then re-runs the same test to prove the fix holds.

### 2:20-2:45 - Onboarding and Partner Depth

Show `/onboard`.

Point out:

- Current GCP project.
- Four available projects.
- GitHub ready.
- Dynatrace ready.
- DQL post-onboarding checks.

Voiceover:

> The onboarding control panel validates the current Google Cloud project, GitHub repo, Dynatrace configuration, and provides Dynatrace-skill-backed DQL checks for GCP, GKE, logs, services, and problems.

### 2:45-3:00 - Impact Close

Voiceover:

> Aegis turns resilience engineering into a supervised, repeatable, auditable agent workflow: find risk, test safely, fix, and verify.

## AI Video Prompts

For the complete AI-generated version, start with `docs/AI_VIDEO_PRODUCTION_PACKET.md`.

Use generated clips for the full narrative, but avoid fake secrets, private emails, or claims that the live app cannot demonstrate.

### Intro Clip Prompt

```text
Create a clean enterprise SRE dashboard intro for a product called Aegis. Visual style: data-dense cloud operations dashboard, dark neutral interface, green and blue status indicators, no sci-fi characters, no decorative blobs. Show abstract service dependency lines, a burn-rate chart rising, and a clear "Auto-abort" status turning green. 5 seconds, professional Google Cloud hackathon demo tone.
```

### Outro Clip Prompt

```text
Create a concise closing animation for an SRE agent demo. Show the sequence "Detect risk -> Approve -> Inject -> Auto-abort -> Open PR -> Verify fix" as clean dashboard steps. Style: modern enterprise observability UI, dark neutral background, accessible contrast, subtle motion. 5 seconds.
```

### Thumbnail Prompt

```text
Professional hackathon demo thumbnail for "Aegis". Show a cloud operations dashboard with a burn-rate line crossing a threshold, an "Auto-aborted" badge, and small Google Cloud plus Dynatrace labels. Clean enterprise SaaS style, readable text, high contrast, no cartoon mascots.
```

## Recording Checklist

- Browser zoom: 100%.
- Resolution: 1920x1080.
- Hide bookmarks and personal tabs.
- Use the deployed URL, not localhost.
- Make sure no token/secret pages are visible.
- Start with dashboard already loaded.
- Keep cursor movement slow.
- Record one clean pass even if you plan to edit.
- Upload as unlisted YouTube or Vimeo.

## Devpost Video Title

Aegis - Gemini and Dynatrace MCP Autonomous Resilience Game Day

## Devpost Video Description

Aegis is a Google Cloud and Dynatrace MCP-powered SRE agent. Gemini plans and coordinates the game-day workflow, while deterministic Python safely injects faults, auto-aborts on SLO burn, opens a GitHub hardening PR, applies the fix, and verifies the service survives a re-run.
