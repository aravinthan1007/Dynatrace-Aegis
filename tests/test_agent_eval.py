"""ADK evaluations for the Aegis agent.

Tool-trajectory eval: does the agent call `gather_dynatrace_context` and pick the
right target? Runs the real ADK `AgentEvaluator` against the focused eval agent.

Requires Gemini access (Vertex via ADC, or GOOGLE_API_KEY) and reachable demo
metrics, so it's opt-in:

    set RUN_ADK_EVAL=1
    set GOOGLE_GENAI_USE_VERTEXAI=True
    set GOOGLE_CLOUD_PROJECT=<project>
    set GOOGLE_CLOUD_LOCATION=global
    set AEGIS_DEMO_APP_URL=<demo url>
    pytest tests/test_agent_eval.py -q

Or via the ADK CLI:
    adk eval aegis_agent.eval_agent aegis_agent/eval/aegis.test.json
"""

from __future__ import annotations

import asyncio
import inspect
import os
from pathlib import Path

import pytest

EVAL_FILE = str(Path(__file__).resolve().parents[1] / "aegis_agent" / "eval" / "aegis.test.json")


@pytest.mark.skipif(
    not os.getenv("RUN_ADK_EVAL"),
    reason="Set RUN_ADK_EVAL=1 (+ Gemini/Vertex creds) to run the ADK trajectory eval.",
)
def test_target_selection_trajectory():
    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    try:
        result = AgentEvaluator.evaluate(
            agent_module="aegis_agent.evalagent.agent",
            eval_dataset_file_path_or_dir=EVAL_FILE,
            num_runs=1,
        )
        if inspect.iscoroutine(result):
            asyncio.run(result)
    except ImportError as exc:
        pytest.skip(f"ADK eval extras not installed (pip install 'google-adk[eval]'): {exc}")
