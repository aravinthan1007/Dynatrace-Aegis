"""Backwards-compatible alias. The eval agent lives at
`aegis_agent.evalagent.agent` (ADK resolves agents from a `.agent` module path)."""

from .evalagent.agent import app, root_agent

__all__ = ["root_agent", "app"]
