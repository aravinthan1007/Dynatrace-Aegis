"""Focused, read-only Aegis agent used for ADK evaluations.

The production `root_agent` runs a full game day with a human-approval gate and
mutating actions — not suitable for automated evals. This eval agent exposes only
the non-blocking decision tool so `AgentEvaluator` can score whether Gemini makes
the right call (tool trajectory) and picks the right target.

ADK's evaluator resolves the agent from a module path ending in `.agent`, so this
lives at `aegis_agent.evalagent.agent`.
"""

from __future__ import annotations

from textwrap import dedent

from google.adk.apps import App
from google.adk.tools.function_tool import FunctionTool

try:
    from google.adk.agents import LlmAgent as BaseAgent
except ImportError:  # pragma: no cover
    from google.adk.agents import Agent as BaseAgent

from ..agent import gather_dynatrace_context
from ..config import get_config

config = get_config()

INSTRUCTION = dedent(
    """
    You are the Aegis Risk Advisor. When the user asks which service dependency is
    riskiest to chaos-test, call `gather_dynatrace_context` exactly once, then answer
    in one or two sentences naming the chosen target and the measured reason
    (risk score / bad-ratio / p95 / hardening). Do not call any other tools.
    """
).strip()

root_agent = BaseAgent(
    name="aegis_eval_agent",
    model=config.gemini_model,
    description="Read-only Aegis risk advisor for ADK evaluations.",
    instruction=INSTRUCTION,
    tools=[FunctionTool(gather_dynatrace_context)],
)

app = App(root_agent=root_agent, name="aegis_eval")
