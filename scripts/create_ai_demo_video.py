"""Create a silent product-style demo video with Playwright.

The output is a browser-recorded WebM that can be imported into Google Vids.
Use Google Vids only for narration/audio and final MP4 export.
"""

from __future__ import annotations

import base64
import re
import shutil
from pathlib import Path
from textwrap import dedent

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runtime_artifacts" / "video"
OUT_FILE = OUT_DIR / "aegis-demo-silent.webm"
RECORDING_MS = 172_000
LIVE_URL = "https://aegis-dashboard-948868496451.us-central1.run.app"
REPO_URL = "https://github.com/aravinthan1007/Dynatrace-Aegis"
PR_URL = f"{REPO_URL}/pull/1"
SCORECARD_PATH = ROOT / "runtime_artifacts" / "20260606-032658-aegis-game-day-scorecard.md"
SCREENSHOT_DIR = ROOT / "docs" / "video-assets"


def _data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        mime = "image/png"
    elif suffix in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif suffix == ".webp":
        mime = "image/webp"
    else:
        raise ValueError(f"Unsupported image type for {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _load_scorecard() -> dict[str, str]:
    markdown = SCORECARD_PATH.read_text(encoding="utf-8")

    def pick(label: str, fallback: str) -> str:
        match = re.search(rf"- {re.escape(label)}:\s*(.+)", markdown)
        return match.group(1).strip() if match else fallback

    return {
        "verdict": pick("Verdict", "ABORTED"),
        "target": pick("Target", "payment->store"),
        "latency": pick("Injected latency", "650ms"),
        "peak_burn": pick("Peak burn", "14.676"),
        "duration": pick("Duration", "5.1s"),
        "timeline": markdown.split("## Timeline", 1)[-1].strip(),
        "markdown": markdown.strip(),
    }


def build_html() -> str:
    dashboard_img = _data_url(SCREENSHOT_DIR / "dashboard.png")
    onboarding_img = _data_url(SCREENSHOT_DIR / "onboarding.png")
    scorecard = _load_scorecard()

    return dedent(
        f"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>Aegis Demo Video</title>
          <style>
            :root {{
              --bg: #07111a;
              --panel: #111d2a;
              --panel2: #172435;
              --panel3: #0b141f;
              --line: #2c3c50;
              --text: #f3f8ff;
              --muted: #9fb0c4;
              --green: #73e6a4;
              --blue: #7cb7ff;
              --yellow: #f3cf55;
              --red: #ff796d;
              --purple: #d6b3ff;
            }}
            * {{ box-sizing: border-box; }}
            html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: var(--bg); }}
            body {{ font-family: "Segoe UI", Arial, sans-serif; color: var(--text); }}
            .stage {{
              position: relative;
              width: 1280px;
              height: 720px;
              background: linear-gradient(160deg, #07111a, #0b1824 52%, #0c1f2d);
            }}
            .top {{
              position: absolute;
              inset: 0 0 auto 0;
              height: 74px;
              border-bottom: 1px solid var(--line);
              display: flex;
              align-items: center;
              padding: 0 26px;
              gap: 18px;
            }}
            .brand h1 {{ margin: 0; font-size: 25px; }}
            .brand p {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; }}
            .nav {{ margin-left: auto; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
            .pill {{
              border: 1px solid var(--line);
              border-radius: 999px;
              padding: 8px 12px;
              color: #c9ddf7;
              background: rgba(255,255,255,.035);
              font-size: 13px;
            }}
            .pill.ok::before {{
              content: "";
              display: inline-block;
              width: 8px;
              height: 8px;
              border-radius: 50%;
              background: var(--green);
              margin-right: 7px;
            }}
            .scene {{
              position: absolute;
              inset: 74px 0 0 0;
              opacity: 0;
              transform: translateY(14px);
              transition: opacity .8s ease, transform .8s ease;
              padding: 28px;
            }}
            .scene.active {{ opacity: 1; transform: translateY(0); }}
            .caption {{
              position: absolute;
              left: 34px;
              bottom: 26px;
              right: 34px;
              padding: 14px 18px;
              background: rgba(5, 13, 22, .86);
              border: 1px solid var(--line);
              border-radius: 10px;
              font-weight: 700;
              font-size: 20px;
              color: var(--text);
            }}
            .lead {{
              color: var(--muted);
              font-size: 18px;
              line-height: 1.45;
            }}
            .grid2 {{ display: grid; grid-template-columns: 1.02fr .98fr; gap: 18px; height: 540px; }}
            .grid3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
            .panel {{
              background: var(--panel);
              border: 1px solid var(--line);
              border-radius: 10px;
              padding: 18px;
              position: relative;
              overflow: hidden;
            }}
            .panel h2 {{ margin: 0 0 14px; font-size: 18px; text-transform: uppercase; letter-spacing: .04em; }}
            .muted {{ color: var(--muted); }}
            .eyebrow {{
              display: inline-block;
              padding: 6px 10px;
              border-radius: 999px;
              background: rgba(124,183,255,.12);
              color: var(--blue);
              border: 1px solid rgba(124,183,255,.24);
              font-size: 12px;
              text-transform: uppercase;
              letter-spacing: .08em;
              margin-bottom: 16px;
            }}
            .problem-list {{
              display: grid;
              gap: 12px;
              margin-top: 18px;
            }}
            .problem {{
              background: var(--panel2);
              border: 1px solid var(--line);
              border-radius: 10px;
              padding: 14px 16px;
              font-size: 17px;
            }}
            .screenshot-card {{
              background: var(--panel3);
              border: 1px solid var(--line);
              border-radius: 14px;
              padding: 12px;
              height: 100%;
              box-shadow: 0 18px 40px rgba(0,0,0,.28);
            }}
            .screenshot-card img {{
              width: 100%;
              height: 100%;
              object-fit: cover;
              border-radius: 10px;
              display: block;
            }}
            .callout {{
              position: absolute;
              right: 30px;
              top: 28px;
              background: rgba(7, 17, 26, .9);
              border: 1px solid rgba(115,230,164,.45);
              border-radius: 12px;
              padding: 14px 16px;
              width: 300px;
              box-shadow: 0 12px 30px rgba(0,0,0,.25);
            }}
            .callout b {{ display: block; margin-bottom: 8px; font-size: 15px; }}
            .arch {{
              display: grid;
              grid-template-columns: repeat(4, 1fr);
              gap: 16px;
              align-items: center;
              margin-top: 80px;
            }}
            .box {{
              min-height: 128px;
              display: grid;
              place-items: center;
              text-align: center;
              padding: 16px;
              border-radius: 14px;
              border: 1px solid var(--line);
              background: var(--panel2);
              font-size: 20px;
              font-weight: 800;
              box-shadow: 0 0 0 1px rgba(124,183,255,.06);
            }}
            .box.guard {{
              border-color: var(--green);
              box-shadow: 0 0 24px rgba(115,230,164,.16);
            }}
            .flow {{
              display: grid;
              grid-template-columns: repeat(4, 1fr);
              gap: 12px;
              margin-top: 28px;
            }}
            .flow div {{
              background: var(--panel2);
              border: 1px solid var(--line);
              border-radius: 10px;
              padding: 14px;
              min-height: 84px;
            }}
            .flow b {{ display: block; margin-bottom: 6px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 17px; margin-top: 20px; }}
            th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 14px 8px; }}
            th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
            tr.hot {{ background: rgba(115,230,164,.12); color: var(--text); }}
            .button {{
              display: inline-flex;
              align-items: center;
              justify-content: center;
              min-width: 170px;
              height: 48px;
              border-radius: 999px;
              background: var(--green);
              color: #061018;
              font-weight: 900;
              margin-top: 22px;
            }}
            .button.blue {{ background: var(--blue); }}
            .approval-grid {{
              display: grid;
              grid-template-columns: 1fr .95fr;
              gap: 18px;
              height: 520px;
            }}
            .checklist {{
              display: grid;
              gap: 12px;
              margin-top: 20px;
            }}
            .checkitem {{
              background: var(--panel2);
              border: 1px solid var(--line);
              border-radius: 10px;
              padding: 13px 14px;
              font-size: 16px;
            }}
            .checkitem::before {{
              content: "OK";
              color: var(--green);
              font-weight: 800;
              margin-right: 10px;
            }}
            .chart {{
              position: relative;
              height: 330px;
              background: #08111a;
              border: 1px solid #162436;
              border-radius: 14px;
              overflow: hidden;
              margin-top: 10px;
            }}
            .threshold {{
              position: absolute;
              left: 0;
              right: 0;
              top: 120px;
              height: 3px;
              background: var(--yellow);
            }}
            .threshold::after {{
              content: "abort threshold";
              position: absolute;
              top: -24px;
              left: 16px;
              color: var(--yellow);
              font-size: 13px;
            }}
            svg {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
            .burn {{
              fill: none;
              stroke: var(--blue);
              stroke-width: 5;
              stroke-linecap: round;
              stroke-dasharray: 1000;
              stroke-dashoffset: 1000;
              animation: draw 8s linear forwards;
            }}
            .burn.safe {{ stroke: var(--green); animation-duration: 7s; }}
            @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
            .abort {{
              position: absolute;
              right: 24px;
              top: 24px;
              background: rgba(255,121,109,.95);
              color: #260605;
              border-radius: 10px;
              padding: 14px 18px;
              font-weight: 900;
              font-size: 22px;
              opacity: 0;
              animation: pop .7s ease 5.5s forwards;
            }}
            @keyframes pop {{ to {{ opacity: 1; transform: scale(1.02); }} }}
            .signal-stack {{ display: grid; gap: 12px; margin-top: 16px; }}
            .signal {{
              background: var(--panel2);
              border: 1px solid var(--line);
              border-radius: 10px;
              padding: 13px 14px;
            }}
            .signal b {{ display: block; margin-bottom: 6px; }}
            .query {{
              font-family: Consolas, monospace;
              font-size: 14px;
              line-height: 1.45;
              white-space: pre-wrap;
              color: #cfe2ff;
            }}
            .pr {{
              background: #0d1117;
              border-radius: 12px;
              border: 1px solid #30363d;
              padding: 16px;
              margin-top: 10px;
              font-family: Consolas, monospace;
              font-size: 17px;
            }}
            .pr-head {{
              display: flex;
              justify-content: space-between;
              align-items: center;
              margin-bottom: 14px;
              font-size: 16px;
            }}
            .plus {{ color: var(--green); }}
            .minus {{ color: var(--red); }}
            .meta-row {{
              display: grid;
              grid-template-columns: repeat(3, 1fr);
              gap: 12px;
              margin-top: 16px;
            }}
            .meta {{
              background: var(--panel2);
              border: 1px solid var(--line);
              border-radius: 10px;
              padding: 13px;
            }}
            .meta small {{ display: block; color: var(--muted); margin-bottom: 6px; }}
            .notebook-grid {{
              display: grid;
              grid-template-columns: .95fr 1.05fr;
              gap: 18px;
              height: 520px;
            }}
            .markdown {{
              background: #0a1119;
              border: 1px solid var(--line);
              border-radius: 12px;
              padding: 16px;
              font-family: Consolas, monospace;
              font-size: 15px;
              line-height: 1.5;
              white-space: pre-wrap;
              height: 100%;
              overflow: hidden;
            }}
            .cards {{
              display: grid;
              grid-template-columns: 1fr 1fr;
              gap: 18px;
              margin-top: 20px;
            }}
            .card {{
              border: 1px solid var(--line);
              border-radius: 12px;
              background: var(--panel2);
              padding: 22px;
              min-height: 160px;
            }}
            .card strong {{ font-size: 34px; display: block; margin-top: 20px; }}
            .project-copy {{
              display: grid;
              gap: 12px;
              margin-top: 16px;
            }}
            .project-copy div {{
              background: var(--panel2);
              border: 1px solid var(--line);
              border-radius: 10px;
              padding: 13px 14px;
            }}
            .footer-links {{
              display: grid;
              grid-template-columns: 1fr 1fr;
              gap: 14px;
              margin-top: 26px;
            }}
            .footer-links div {{
              background: var(--panel2);
              border: 1px solid var(--line);
              border-radius: 10px;
              padding: 14px;
            }}
            .footer-links small {{ color: var(--muted); display: block; margin-bottom: 8px; }}
            .workflow {{
              display: grid;
              grid-template-columns: repeat(6, 1fr);
              gap: 10px;
              margin-top: 140px;
            }}
            .workflow div {{
              border: 1px solid var(--line);
              background: var(--panel2);
              border-radius: 12px;
              padding: 20px 10px;
              text-align: center;
              font-weight: 800;
              min-height: 100px;
              display: grid;
              place-items: center;
            }}
          </style>
        </head>
        <body>
          <div class="stage">
            <header class="top">
              <div class="brand">
                <h1>Aegis - Autonomous Resilience Game-Day Agent</h1>
                <p>Google Cloud + Gemini ADK + Dynatrace MCP</p>
              </div>
              <nav class="nav">
                <span class="pill">Game day</span>
                <span class="pill">Onboarding</span>
                <span class="pill ok">Dynatrace ready</span>
                <span class="pill ok">GitHub ready</span>
              </nav>
            </header>

            <section class="scene active" data-ms="18000">
              <div class="grid2">
                <div class="panel">
                  <span class="eyebrow">Problem</span>
                  <h2>Why Aegis exists</h2>
                  <p class="lead">SRE teams need to test resilience without turning game days into risky one-off drills. Aegis makes the workflow supervised, measurable, and provable.</p>
                  <div class="problem-list">
                    <div class="problem">Manual chaos tests rarely prove whether the fix actually worked.</div>
                    <div class="problem">Observability, mutation, and remediation usually live in separate tools.</div>
                    <div class="problem">Safety decisions should be deterministic code, not an LLM hunch.</div>
                  </div>
                </div>
                <div class="panel" style="padding:0;">
                  <div class="screenshot-card"><img src="{dashboard_img}" alt="Aegis dashboard" /></div>
                  <div class="callout">
                    <b>Live proof points</b>
                    <div class="muted">Risk ranking, approval gate, burn-rate auto-abort, GitHub PR, Dynatrace notebook, and onboarding status all surface in one operator flow.</div>
                  </div>
                </div>
              </div>
              <div class="caption">Aegis turns resilience testing into a supervised workflow with evidence, safety, and follow-through.</div>
            </section>

            <section class="scene" data-ms="16000">
              <div class="arch">
                <div class="box">Cloud Run</div>
                <div class="box">Gemini ADK</div>
                <div class="box">Dynatrace MCP</div>
                <div class="box guard">Deterministic Python Safety Loop</div>
              </div>
              <div class="flow">
                <div><b>Plan</b><span class="muted">Gemini selects the next tool and narrates the operator workflow.</span></div>
                <div><b>Observe</b><span class="muted">Dynatrace provides DQL, Grail signals, and notebook evidence.</span></div>
                <div><b>Mutate</b><span class="muted">Python tools call GitHub and controlled fault injection steps.</span></div>
                <div><b>Protect</b><span class="muted">Abort logic is numeric and deterministic, never delegated to the model.</span></div>
              </div>
              <div class="caption">Gemini plans. Python enforces safety. Dynatrace verifies.</div>
            </section>

            <section class="scene" data-ms="18000">
              <div class="panel">
                <h2>Ranked dependencies</h2>
                <table>
                  <thead>
                    <tr><th>Dependency</th><th>Risk</th><th>p95</th><th>Bad%</th><th>Hardened</th><th>Reason</th></tr>
                  </thead>
                  <tbody>
                    <tr><td>frontend->payment</td><td>0.7</td><td>180ms</td><td>0.2%</td><td>yes</td><td>Already bounded</td></tr>
                    <tr class="hot"><td>{scorecard["target"]}</td><td>2.9</td><td>490ms</td><td>1.8%</td><td>no</td><td>Request path, no timeout/retry</td></tr>
                    <tr><td>store->inventory</td><td>0.5</td><td>135ms</td><td>0.1%</td><td>yes</td><td>Low user impact</td></tr>
                  </tbody>
                </table>
                <div class="meta-row">
                  <div class="meta"><small>Selected target</small>{scorecard["target"]}</div>
                  <div class="meta"><small>Injected latency</small>{scorecard["latency"]}</div>
                  <div class="meta"><small>Reason for test</small>Highest operator-visible risk on the request path</div>
                </div>
              </div>
              <div class="caption">Aegis ranks live dependency risk before acting, so the test starts from evidence rather than guesswork.</div>
            </section>

            <section class="scene" data-ms="14000">
              <div class="approval-grid">
                <div class="panel">
                  <h2>Human approval required</h2>
                  <p class="lead">Before any mutation, the operator sees the target, blast radius, burn threshold, and rollback rule.</p>
                  <div class="checklist">
                    <div class="checkitem">Target: {scorecard["target"]}</div>
                    <div class="checkitem">Fault: inject {scorecard["latency"]} latency</div>
                    <div class="checkitem">Abort when burn exceeds 10x</div>
                    <div class="checkitem">Rollback is automatic on threshold breach</div>
                  </div>
                  <div class="button">Approve Injection</div>
                </div>
                <div class="panel">
                  <h2>Operator concern addressed</h2>
                  <div class="problem-list">
                    <div class="problem">Who approved the experiment?</div>
                    <div class="problem">What exact failure are we injecting?</div>
                    <div class="problem">How do we stop before customer impact spreads?</div>
                  </div>
                </div>
              </div>
              <div class="caption">Human-in-the-loop before mutation, with a clear target and explicit rollback rule.</div>
            </section>

            <section class="scene" data-ms="24000">
              <div class="grid2">
                <div class="panel">
                  <h2>Safe fault injection</h2>
                  <div class="chart">
                    <div class="threshold"></div>
                    <svg viewBox="0 0 700 330">
                      <path class="burn" d="M20 290 C150 288 220 260 300 210 S440 115 520 80 S610 48 680 38"/>
                    </svg>
                    <div class="abort">AUTO-ABORT: fault rolled back</div>
                  </div>
                  <div class="meta-row">
                    <div class="meta"><small>Peak burn</small>{scorecard["peak_burn"]}</div>
                    <div class="meta"><small>Duration</small>{scorecard["duration"]}</div>
                    <div class="meta"><small>Verdict</small>{scorecard["verdict"]}</div>
                  </div>
                </div>
                <div class="panel">
                  <h2>Dynatrace evidence</h2>
                  <div class="signal-stack">
                    <div class="signal">
                      <b>DQL verification</b>
                      <div class="query">timeseries avg(dt.service.request.failure_count), by: dt.entity.service
| filter dt.entity.service == "payment"</div>
                    </div>
                    <div class="signal">
                      <b>Observed behavior</b>
                      <div class="muted">Burn spikes beyond the threshold, the safety loop rolls the fault back, and the operator gets a concrete pre-fix verdict.</div>
                    </div>
                    <div class="signal">
                      <b>What problem this solves</b>
                      <div class="muted">The team does not have to argue from intuition. Dynatrace captures the failure signal and Aegis stops the test deterministically.</div>
                    </div>
                  </div>
                </div>
              </div>
              <div class="caption">Dynatrace shows the signal, and the deterministic abort protects the SLO before the blast radius grows.</div>
            </section>

            <section class="scene" data-ms="18000">
              <div class="grid2">
                <div class="panel">
                  <h2>GitHub hardening PR</h2>
                  <div class="pr">
                    <div class="pr-head">
                      <span>feat: harden payment client after Aegis game day</span>
                      <span class="muted">PR ready</span>
                    </div>
                    <div class="muted" style="margin-bottom:12px;">{PR_URL}</div>
                    <span class="minus">- call store without retry</span><br />
                    <span class="plus">+ timeout = 500ms</span><br />
                    <span class="plus">+ retry once with backoff</span><br />
                    <span class="plus">+ fail fast before SLO burn spikes</span>
                  </div>
                  <div class="meta-row">
                    <div class="meta"><small>Repo</small>aravinthan1007/Dynatrace-Aegis</div>
                    <div class="meta"><small>Action</small>Open PR from Aegis findings</div>
                    <div class="meta"><small>Outcome</small>Reviewable engineering change</div>
                  </div>
                </div>
                <div class="panel">
                  <h2>Why this matters</h2>
                  <div class="problem-list">
                    <div class="problem">Aegis does not stop at diagnosis.</div>
                    <div class="problem">The evidence becomes a concrete fix proposal in GitHub.</div>
                    <div class="problem">The team gets an auditable change instead of a vague recommendation.</div>
                  </div>
                </div>
              </div>
              <div class="caption">Aegis turns findings into a GitHub hardening PR the team can review, merge, and track.</div>
            </section>

            <section class="scene" data-ms="16000">
              <div class="notebook-grid">
                <div class="panel">
                  <h2>Dynatrace notebook and scorecard</h2>
                  <div class="markdown">{scorecard["markdown"]}</div>
                </div>
                <div class="panel">
                  <h2>Reporting artifact</h2>
                  <div class="signal-stack">
                    <div class="signal">
                      <b>Notebook output</b>
                      <div class="muted">Aegis publishes the narrative, DQL charts, and verdict into a Dynatrace notebook for postmortem review.</div>
                    </div>
                    <div class="signal">
                      <b>Scorecard fields</b>
                      <div class="muted">Target, injected latency, peak burn, and verdict are preserved as evidence instead of disappearing in chat history.</div>
                    </div>
                    <div class="signal">
                      <b>Operator value</b>
                      <div class="muted">This solves the handoff problem: SREs, app teams, and judges can all inspect the same artifact.</div>
                    </div>
                  </div>
                  <div class="footer-links">
                    <div><small>Live app</small>{LIVE_URL}</div>
                    <div><small>Code repo</small>{REPO_URL}</div>
                  </div>
                </div>
              </div>
              <div class="caption">Aegis keeps a notebook-style report, so the experiment outcome is inspectable after the run ends.</div>
            </section>

            <section class="scene" data-ms="20000">
              <div class="grid2">
                <div class="panel" style="padding:0;">
                  <div class="screenshot-card"><img src="{dashboard_img}" alt="Aegis dashboard verification" /></div>
                  <div class="callout" style="border-color: rgba(115,230,164,.45);">
                    <b>Post-fix state</b>
                    <div class="muted">The same test is re-run after the timeout and retry hardening. Burn stays below the threshold and the verdict flips to passed.</div>
                  </div>
                </div>
                <div class="panel">
                  <h2>Post-fix verify</h2>
                  <div class="chart">
                    <div class="threshold"></div>
                    <svg viewBox="0 0 700 330">
                      <path class="burn safe" d="M20 280 C150 278 240 270 350 268 S520 260 680 258"/>
                    </svg>
                  </div>
                  <div class="cards">
                    <div class="card"><span class="muted">Before</span><strong style="color:var(--red)">ABORTED</strong></div>
                    <div class="card"><span class="muted">After</span><strong style="color:var(--green)">PASSED</strong></div>
                  </div>
                </div>
              </div>
              <div class="caption">The fix is verified, not assumed, because Aegis re-runs the same experiment against the hardened path.</div>
            </section>

            <section class="scene" data-ms="18000">
              <div class="grid2">
                <div class="panel" style="padding:0;">
                  <div class="screenshot-card"><img src="{onboarding_img}" alt="Aegis onboarding" /></div>
                </div>
                <div class="panel">
                  <h2>Project-aware onboarding</h2>
                  <p class="lead">Aegis also solves the setup problem. Teams often have multiple GCP projects and unclear observability readiness before a demo or game day.</p>
                  <div class="project-copy">
                    <div><b>Current project awareness</b><br /><span class="muted">Shows the active project and the other configured GCP projects so the operator knows where mutations will land.</span></div>
                    <div><b>Dynatrace and GitHub readiness</b><br /><span class="muted">Confirms DQL checks, repo access, and service status before the game day starts.</span></div>
                    <div><b>Why it matters</b><br /><span class="muted">Onboarding is not just a form. It removes setup ambiguity so the agent can act on the right environment.</span></div>
                  </div>
                </div>
              </div>
              <div class="caption">The onboarding UI makes the current project, observability readiness, and deployment context obvious before any action.</div>
            </section>

            <section class="scene" data-ms="10000">
              <div class="workflow">
                <div>Detect risk</div>
                <div>Approve</div>
                <div>Inject</div>
                <div>Auto-abort</div>
                <div>Open PR</div>
                <div>Verify fix</div>
              </div>
              <div class="caption">A supervised, repeatable, auditable resilience agent for Google Cloud operations.</div>
            </section>
          </div>
          <script>
            const scenes = [...document.querySelectorAll(".scene")];
            function show(index) {{
              scenes.forEach((scene, i) => scene.classList.toggle("active", i === index));
              const ms = Number(scenes[index].dataset.ms || 8000);
              if (index < scenes.length - 1) {{
                setTimeout(() => show(index + 1), ms);
              }}
            }}
            setTimeout(() => show(1), Number(scenes[0].dataset.ms || 8000));
          </script>
        </body>
        </html>
        """
    ).strip()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.webm"):
        old.unlink()

    html = build_html()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(OUT_DIR),
            record_video_size={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(RECORDING_MS)
        video = page.video
        context.close()
        browser.close()
        if video is None:
            raise RuntimeError("Playwright did not create a video")
        generated = Path(video.path())

    if OUT_FILE.exists():
        OUT_FILE.unlink()
    shutil.move(str(generated), OUT_FILE)
    print(OUT_FILE)


if __name__ == "__main__":
    main()
