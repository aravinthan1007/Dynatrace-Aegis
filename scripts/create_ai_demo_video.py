"""Create a silent AI-style demo video with Playwright.

The output is a browser-recorded WebM that can be imported into Google Vids.
Use Google Vids for the narration/audio track and final MP4 export.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from textwrap import dedent

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "runtime_artifacts" / "video"
OUT_FILE = OUT_DIR / "aegis-demo-silent.webm"
RECORDING_MS = 172_000


HTML = dedent(
    r"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Aegis Demo Video</title>
      <style>
        :root {
          --bg: #07111a;
          --panel: #111d2a;
          --panel2: #172435;
          --line: #2c3c50;
          --text: #f3f8ff;
          --muted: #9fb0c4;
          --green: #73e6a4;
          --blue: #7cb7ff;
          --yellow: #f3cf55;
          --red: #ff796d;
        }
        * { box-sizing: border-box; }
        html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: var(--bg); }
        body { font-family: "Segoe UI", Arial, sans-serif; color: var(--text); }
        .stage { position: relative; width: 1280px; height: 720px; background: linear-gradient(160deg, #07111a, #0b1824 52%, #0c1f2d); }
        .top { position: absolute; inset: 0 0 auto 0; height: 74px; border-bottom: 1px solid var(--line); display: flex; align-items: center; padding: 0 26px; gap: 18px; }
        .brand h1 { margin: 0; font-size: 25px; }
        .brand p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
        .nav { margin-left: auto; display: flex; gap: 8px; align-items: center; }
        .pill { border: 1px solid var(--line); border-radius: 999px; padding: 8px 12px; color: #c9ddf7; background: rgba(255,255,255,.035); font-size: 13px; }
        .pill.ok::before { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--green); margin-right: 7px; }
        .scene { position: absolute; inset: 74px 0 0 0; opacity: 0; transform: translateY(14px); transition: opacity .8s ease, transform .8s ease; padding: 28px; }
        .scene.active { opacity: 1; transform: translateY(0); }
        .caption { position: absolute; left: 34px; bottom: 26px; right: 34px; padding: 14px 18px; background: rgba(5, 13, 22, .86); border: 1px solid var(--line); border-radius: 10px; font-weight: 700; font-size: 20px; color: var(--text); }
        .grid { display: grid; grid-template-columns: 1.05fr .95fr; gap: 18px; height: 510px; }
        .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px; position: relative; overflow: hidden; }
        .panel h2 { margin: 0 0 14px; font-size: 18px; text-transform: uppercase; letter-spacing: .04em; }
        .muted { color: var(--muted); }
        .steps { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-top: 22px; }
        .step { background: var(--panel2); border: 1px solid var(--line); border-radius: 9px; padding: 12px; min-height: 88px; }
        .step b { display: block; font-size: 14px; margin-bottom: 8px; }
        .step small { color: var(--muted); }
        .arch { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; align-items: center; margin-top: 80px; }
        .box { min-height: 128px; display: grid; place-items: center; text-align: center; padding: 16px; border-radius: 14px; border: 1px solid var(--line); background: var(--panel2); font-size: 20px; font-weight: 800; box-shadow: 0 0 0 1px rgba(124,183,255,.06); }
        .box.guard { border-color: var(--green); box-shadow: 0 0 24px rgba(115,230,164,.16); }
        table { width: 100%; border-collapse: collapse; font-size: 17px; margin-top: 20px; }
        th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 14px 8px; }
        th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
        tr.hot { background: rgba(115,230,164,.12); color: var(--text); }
        .button { display: inline-flex; align-items: center; justify-content: center; min-width: 170px; height: 48px; border-radius: 999px; background: var(--green); color: #061018; font-weight: 900; margin-top: 22px; }
        .button.blue { background: var(--blue); }
        .chart { position: relative; height: 330px; background: #08111a; border: 1px solid #162436; border-radius: 14px; overflow: hidden; margin-top: 10px; }
        .threshold { position: absolute; left: 0; right: 0; top: 120px; height: 3px; background: var(--yellow); }
        .threshold::after { content: "abort threshold"; position: absolute; top: -24px; left: 16px; color: var(--yellow); font-size: 13px; }
        svg { position: absolute; inset: 0; width: 100%; height: 100%; }
        .burn { fill: none; stroke: var(--blue); stroke-width: 5; stroke-linecap: round; stroke-dasharray: 1000; stroke-dashoffset: 1000; animation: draw 8s linear forwards; }
        .burn.safe { stroke: var(--green); animation-duration: 7s; }
        @keyframes draw { to { stroke-dashoffset: 0; } }
        .abort { position: absolute; right: 24px; top: 24px; background: rgba(255,121,109,.95); color: #260605; border-radius: 10px; padding: 14px 18px; font-weight: 900; font-size: 22px; opacity: 0; animation: pop .7s ease 5.5s forwards; }
        @keyframes pop { to { opacity: 1; transform: scale(1.02); } }
        .pr { background: #0d1117; border-radius: 12px; border: 1px solid #30363d; padding: 16px; margin-top: 24px; font-family: Consolas, monospace; font-size: 17px; }
        .plus { color: var(--green); }
        .minus { color: var(--red); }
        .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 26px; }
        .card { border: 1px solid var(--line); border-radius: 12px; background: var(--panel2); padding: 22px; min-height: 160px; }
        .card strong { font-size: 34px; display: block; margin-top: 20px; }
        .projects { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 20px; }
        .project { background: var(--panel2); border: 1px solid var(--line); border-radius: 10px; padding: 14px; }
        .project b { display: block; margin-bottom: 5px; }
        .workflow { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-top: 160px; }
        .workflow div { border: 1px solid var(--line); background: var(--panel2); border-radius: 12px; padding: 20px 10px; text-align: center; font-weight: 800; min-height: 100px; display: grid; place-items: center; }
      </style>
    </head>
    <body>
      <div class="stage">
        <header class="top">
          <div class="brand"><h1>Aegis - Autonomous Resilience Game-Day Agent</h1><p>Google Cloud + Gemini ADK + Dynatrace MCP</p></div>
          <nav class="nav"><span class="pill">Game day</span><span class="pill">Onboarding</span><span class="pill ok">Dynatrace ready</span><span class="pill ok">GitHub ready</span></nav>
        </header>

        <section class="scene active" data-ms="15000">
          <div class="grid">
            <div class="panel"><h2>Error-budget burn</h2><div class="chart"><div class="threshold"></div><svg viewBox="0 0 700 330"><path class="burn" d="M20 290 C150 285 220 260 300 210 S440 115 520 80 S610 48 680 38"/></svg></div></div>
            <div class="panel"><h2>Outcome</h2><div class="cards"><div class="card"><span class="muted">Pre-fix</span><strong style="color:var(--red)">ABORTED</strong></div><div class="card"><span class="muted">Post-fix</span><strong style="color:var(--green)">PASSED</strong></div></div></div>
          </div>
          <div class="caption">An agent that safely tests resilience, then proves the fix.</div>
        </section>

        <section class="scene" data-ms="20000">
          <div class="arch"><div class="box">Cloud Run</div><div class="box">Gemini ADK</div><div class="box">Dynatrace MCP</div><div class="box guard">Deterministic Python Safety Loop</div></div>
          <div class="caption">Gemini plans. Python enforces safety. Dynatrace verifies.</div>
        </section>

        <section class="scene" data-ms="20000">
          <div class="panel"><h2>Ranked dependencies</h2><table><thead><tr><th>Dependency</th><th>Risk</th><th>p95</th><th>Bad%</th><th>Hardened</th></tr></thead><tbody><tr><td>frontend->payment</td><td>0.7</td><td>180ms</td><td>0.2%</td><td>yes</td></tr><tr class="hot"><td>payment->store</td><td>2.9</td><td>490ms</td><td>1.8%</td><td>no</td></tr></tbody></table></div>
          <div class="caption">Aegis ranks live dependency risk before acting.</div>
        </section>

        <section class="scene" data-ms="15000">
          <div class="panel" style="width:720px;margin:60px auto;text-align:center;"><h2>Human approval required</h2><p class="muted" style="font-size:20px;">Target payment->store. Inject latency. Abort at 10x burn.</p><div class="button">Approve Injection</div></div>
          <div class="caption">Human-in-the-loop before mutation.</div>
        </section>

        <section class="scene" data-ms="25000">
          <div class="panel"><h2>Safe fault injection</h2><div class="chart"><div class="threshold"></div><svg viewBox="0 0 1180 330"><path class="burn" d="M20 290 C180 288 250 260 350 220 S520 135 650 96 S820 58 950 44 S1060 40 1160 38"/></svg><div class="abort">AUTO-ABORT: fault rolled back</div></div></div>
          <div class="caption">Deterministic abort protects the SLO.</div>
        </section>

        <section class="scene" data-ms="23000">
          <div class="panel"><h2>GitHub hardening PR</h2><div class="pr">feat: harden payment client after Aegis game day<br><br><span class="minus">- call store without retry</span><br><span class="plus">+ timeout = 500ms</span><br><span class="plus">+ retry once with backoff</span><br><span class="plus">+ fail fast before SLO burn spikes</span></div></div>
          <div class="caption">Aegis turns findings into a hardening PR.</div>
        </section>

        <section class="scene" data-ms="22000">
          <div class="grid"><div class="panel"><h2>Post-fix verify</h2><div class="chart"><div class="threshold"></div><svg viewBox="0 0 700 330"><path class="burn safe" d="M20 280 C150 278 240 270 350 268 S520 260 680 258"/></svg></div></div><div class="panel"><h2>Verdict</h2><div class="cards"><div class="card"><span class="muted">Before</span><strong style="color:var(--red)">ABORTED</strong></div><div class="card"><span class="muted">After</span><strong style="color:var(--green)">PASSED</strong></div></div></div></div>
          <div class="caption">The fix is verified, not assumed.</div>
        </section>

        <section class="scene" data-ms="18000">
          <div class="panel"><h2>Project-aware onboarding</h2><div class="projects"><div class="project"><b>gen-lang-client-0176091046</b><span class="muted">active hackathon project</span></div><div class="project"><b>spry-cortex-497218-m7</b><span class="muted">available project</span></div><div class="project"><b>GitHub ready</b><span class="muted">repo and target file verified</span></div><div class="project"><b>Dynatrace ready</b><span class="muted">DQL checks available</span></div></div></div>
          <div class="caption">Project-aware onboarding and Dynatrace-skill-backed checks.</div>
        </section>

        <section class="scene" data-ms="12000">
          <div class="workflow"><div>Detect risk</div><div>Approve</div><div>Inject</div><div>Auto-abort</div><div>Open PR</div><div>Verify fix</div></div>
          <div class="caption">A supervised, repeatable, auditable resilience agent.</div>
        </section>
      </div>
      <script>
        const scenes = [...document.querySelectorAll(".scene")];
        let i = 0;
        function show(n) {
          scenes.forEach((s, idx) => s.classList.toggle("active", idx === n));
          const ms = Number(scenes[n].dataset.ms || 8000);
          if (n < scenes.length - 1) setTimeout(() => show(n + 1), ms);
        }
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

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=str(OUT_DIR),
            record_video_size={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.set_content(HTML, wait_until="load")
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
