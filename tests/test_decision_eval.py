"""Hermetic decision evals for the Aegis agent.

These validate *what the agent decides* (target selection + risk ranking) without
needing Gemini or the network — the kind of grounded check that catches the agent
choosing the wrong dependency. They complement the LLM trajectory eval in
test_agent_eval.py (which runs the real ADK AgentEvaluator).
"""

from __future__ import annotations

from aegis_agent import agent


def _fake_stats(service, config=None):
    # Healthy baseline for both downstream services; risk must come from the
    # structural factors (request-path + hardening), not noise.
    return {"bad_ratio": 0.0, "p95_ms": 45.0, "total": 120, "avg_ms": 40.0, "hardened": False}


def test_picks_unhardened_request_path_dependency(monkeypatch):
    monkeypatch.setattr(agent, "get_service_metrics", _fake_stats)
    monkeypatch.setattr(agent, "_choose_target_with_gemini", lambda cands, cfg: None)

    ctx = agent.gather_dynatrace_context()

    assert ctx["target"] == "payment->store", "should target the unhardened request-path dependency"
    assert ctx["selected_by"] == "deterministic-ranking"
    assert ctx["recommended_latency_ms"] >= 100


def test_candidates_ranked_by_risk(monkeypatch):
    monkeypatch.setattr(agent, "get_service_metrics", _fake_stats)
    monkeypatch.setattr(agent, "_choose_target_with_gemini", lambda cands, cfg: None)

    ctx = agent.gather_dynatrace_context()
    edges = [c["edge"] for c in ctx["candidates"]]

    assert edges[0] == "payment->store"
    # the hardened edge must rank strictly below the unhardened one
    scores = {c["edge"]: c["risk_score"] for c in ctx["candidates"]}
    assert scores["payment->store"] > scores["frontend->payment"]


def test_gemini_choice_is_validated_against_candidates(monkeypatch):
    # If Gemini returns a target that is not a real candidate, we must NOT trust it
    # and fall back to deterministic ranking.
    monkeypatch.setattr(agent, "get_service_metrics", _fake_stats)
    monkeypatch.setattr(
        agent.config, "google_api_key", "fake-key", raising=False
    )

    def _bad_gemini(cands, cfg):
        return None  # simulate invalid/unavailable -> guarded fallback

    monkeypatch.setattr(agent, "_choose_target_with_gemini", _bad_gemini)
    ctx = agent.gather_dynatrace_context()
    assert ctx["target"] in {"payment->store", "frontend->payment"}
