# Aegis — Plan to Win the Dynatrace Track

Scope: a code review of the current Aegis implementation plus a prioritized, file-by-file
improvement plan. Built around the four equally-weighted judging criteria:
**Technological Implementation · Design · Potential Impact · Quality of Idea.**

Goal for today: ship P0 (close the credibility gaps that lose points) and at least one P1
(the feature that wins points). Everything below names exact files and functions.

---

## 1. Honest assessment of where Aegis stands

**The concept is a winner.** "LLM designs the chaos experiment, deterministic Python runs the
safety abort" is a genuinely sharp idea, it uses Dynatrace meaningfully (topology, DQL, events,
notebooks), and it takes real actions (chaos injection, hard abort, a real GitHub PR). The README's
own winnability instincts are correct.

**But the code undercuts the pitch in three places a judge will notice:**

1. **It is not actually agentic yet.** `gather_dynatrace_context()` in `aegis_agent/agent.py`
   returns a hardcoded `target = "payment->store"`, a hardcoded rationale, hypothesis, and latency.
   Gemini never reasons over live data to *choose* the risky dependency. `list_dynatrace_tools()`
   is called and its output discarded. A judge reading the repo sees an LLM wrapper around a fixed
   script. **This is the single biggest threat to the "Technological Implementation" and
   "Quality of Idea" scores.**

2. **The safety-critical path is untested.** `tests/` only covers `clarity_app`. The abort loop —
   the thing the whole pitch rests on — has zero tests. An untested safety brake is a credibility
   hole.

3. **The burn signal is slow and jumpy.** `get_burn_rate()` calls `asyncio.run()` on every 3s poll,
   which spawns a fresh `npx` MCP subprocess each time. That contradicts the README's "burn must
   react within seconds." And with only ~2 local samples the burn jumps to ~14 instantly (see the
   saved scorecard: timeline `[{t:0.9, burn:0}, {t:4.3, burn:14.67}]`), which looks fake on camera.

Minor: `@app.on_event("startup")` is deprecated (FastAPI lifespan), and the scorecard embeds the
timeline as a raw `str(list)` instead of a chart.

---

## 2. Priorities (do them in this order)

### P0 — Credibility fixes (land these today, ~2-4 hrs)

These don't add features; they make the existing pitch *true*. Highest ROI.

**P0.1 — Make target selection genuinely agentic.**
File: `aegis_agent/agent.py`, function `gather_dynatrace_context()`.
- Use the live Dynatrace MCP to pull candidate dependencies. The MCP exposes topology/entity and
  DQL tools — query the service call graph (or, in fallback mode, read the demo app's
  `/metrics/recent` per service) to build a list of real candidate edges with measured
  latency/error stats.
- Pass that candidate list to Gemini and let it *rank* and pick the target + propose the latency,
  returning structured JSON (target, rationale, hypothesis, latency_ms). Keep `payment->store` only
  as the fallback when no live data exists.
- Net effect: the rationale a judge sees in the reasoning feed is now produced from real numbers, not
  a string literal. This is the change that turns "LLM wrapper" into "agent."

**P0.2 — Reuse one MCP session across the poll loop.**
Files: `aegis_agent/dynatrace.py`, `aegis_agent/experiment.py`.
- Open the `DynatraceMcpClient` once at experiment start, pass it into the poll loop, close at end.
  Remove the per-poll `asyncio.run()` / fresh-subprocess pattern. Run the loop inside a single async
  context. This is what delivers the "reacts within seconds" promise.

**P0.3 — Add tests for the abort path.**
New file: `aegis/tests/test_experiment.py`.
- Inject a fake burn function that climbs past the threshold; assert `aborted is True`, that chaos
  was reset to `latency_ms=0` (mock `set_chaos`), and that an `abort` event was published.
- Add a second test where burn stays low → assert `aborted is False` and an END event fired.
- This makes "deterministic safety brake" a verifiable claim, not just a sentence in the README.

**P0.4 — Smooth the burn signal for a believable chart.**
File: `demo_app/chaos.py` `summarize_recent()` and/or `aegis_agent/dql.py`.
- Require a minimum sample count before computing ratio, or use an EWMA so the line *rises* over a
  few seconds instead of snapping to 14. A smooth climb that crosses the threshold on camera is far
  more convincing than an instant spike.

### P1 — The feature that wins (pick ONE today)

**P1.A — Closed-loop "fix verified" narrative (recommended).** *Impact + Idea + Tech.*
Right now Aegis aborts and opens a PR, but never *proves the fix works*. Add a verification re-run:
after the hardening PR, re-run the same experiment against the hardened payment client and show the
burn staying under threshold (PASSED). The demo story becomes: **break it → auto-abort → open PR →
apply fix → re-run → it survives.** That closed loop is the most memorable 30 seconds you can give a
judge and directly lifts Potential Impact ("this actually remediates, not just alerts").
- Files: add a `verify_after_fix` step in `agent.py` `run_aegis_game_day()`; toggle the demo app to
  use the hardened `payment_client` (env flag `PAYMENT_HARDENED=1` selecting the timeout/retry client
  that already exists in `actions._build_hardened_payment_client`). Emit a second `scorecard` event
  with a before/after comparison.

**P1.B — Multi-candidate ranking dashboard panel.** *Design + Tech.*
Show the ranked list of dependency candidates with their measured risk scores in the UI, then
highlight the one Gemini chose. Makes the agency from P0.1 *visible*, which scores on Design.

**P1.C — Davis AI / Problems integration.** *Dynatrace depth.*
After abort, query the Dynatrace MCP for any auto-detected Problems/Davis findings in the window and
fold them into the scorecard. Shows deeper platform use.

> Recommendation: **P1.A**. It's the strongest on-camera moment and touches three of four criteria.

### P2 — Polish for submission (the checklist judges literally gave you)

- **Repo:** confirm it's public, license visible in the GitHub "About" panel (LICENSE exists — make
  sure it shows). Remove the misspelled `Credencials/` folder from the repo and scrub any secrets;
  confirm `.env` is gitignored (it is) but verify nothing leaked in git history.
- **Hosted URL:** deploy the dashboard to Cloud Run (a `deploy/cloudrun-notes.md` already exists) and
  test that a judge can open it cold. The local-fallback path means it works without a live tenant —
  lean on that for reliability.
- **Demo video (<3 min):** script it around the P1.A closed loop. Say the words "Google Cloud /
  Gemini" and "Dynatrace MCP" explicitly — judges check for partner-service usage.
- **README:** add an architecture GIF/screenshot of the abort moment and a one-line "how it uses
  Google Cloud + Dynatrace MCP" near the top. Replace the "scaffolded/Phase X" status language —
  it reads as unfinished to a judge.
- **FastAPI lifespan:** swap the two deprecated `@app.on_event` handlers in `demo_app/main.py` for a
  `lifespan` context manager. Cheap, removes warnings on startup that show up in a live demo.

---

## 3. Suggested order for today

1. P0.2 (session reuse) — unblocks a fast, smooth demo. ~30 min.
2. P0.4 (smooth burn) — makes the chart believable. ~30 min.
3. P0.1 (real agentic selection) — the credibility centerpiece. ~60-90 min.
4. P0.3 (abort tests) — locks in the safety claim. ~30 min.
5. P1.A (verify-after-fix loop) — the winning moment. ~60-90 min.
6. P2 polish + record video. Remaining time.

If you run short, P0.1 + P0.3 + P1.A are the three that move the score the most.

---

## 4. How each item maps to the judging criteria

| Item | Tech Impl | Design | Impact | Idea |
|------|:---:|:---:|:---:|:---:|
| P0.1 real agentic selection | ✔✔ |  |  | ✔✔ |
| P0.2 MCP session reuse | ✔ | ✔ |  |  |
| P0.3 abort tests | ✔✔ |  |  |  |
| P0.4 smooth burn | ✔ | ✔✔ |  |  |
| P1.A verify-after-fix loop | ✔ | ✔ | ✔✔ | ✔✔ |
| P1.B ranking panel | ✔ | ✔✔ |  | ✔ |
| P1.C Davis/Problems | ✔✔ |  | ✔ | ✔ |
| P2 polish (repo/URL/video) | ✔ | ✔✔ | ✔ |  |

---

*Next step: say the word and I'll start implementing in this order — beginning with P0.2 and P0.1.*
