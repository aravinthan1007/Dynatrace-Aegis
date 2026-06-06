"""Tests for the deterministic abort path.

These exercise the safety-critical claim directly: when the burn signal crosses
the numeric threshold, `run_experiment` must abort, reset chaos, and emit an
abort event — with no LLM in the loop. A scripted fake sampler drives the burn
values so the test is fast and deterministic.
"""

from __future__ import annotations

from aegis_agent import experiment
from aegis_agent.config import get_config
from aegis_agent.events import event_bus


class FakeSampler:
    """Async-context sampler that yields scripted burn values."""

    def __init__(self, values):
        self._values = list(values)
        self._i = 0
        self.events: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def sample(self) -> float:
        value = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return float(value)

    async def send_event(self, title, properties=None):
        self.events.append(title)


def _factory(values):
    return lambda config: FakeSampler(values)


def test_aborts_when_burn_exceeds_threshold(monkeypatch):
    chaos_calls: list[dict] = []
    monkeypatch.setattr(experiment, "set_chaos", lambda **kw: chaos_calls.append(kw))

    abort_events: list[dict] = []
    original_publish = event_bus.publish

    def capture(event):
        if event.get("type") == "abort":
            abort_events.append(event)
        return original_publish(event)

    monkeypatch.setattr(event_bus, "publish", capture)

    result = experiment.run_experiment(
        target="payment->store",
        latency_ms=650,
        burn_abort=10.0,
        poll_seconds=0,
        max_duration_s=5,
        config=get_config(),
        sampler_factory=_factory([2.0, 8.0, 14.0]),
    )

    assert result["aborted"] is True
    assert result["peak_burn"] >= 10.0
    # Chaos was reset to a safe state at least once (latency_ms == 0).
    assert any(call.get("latency_ms") == 0 for call in chaos_calls)
    # The deterministic abort event was published.
    assert abort_events, "expected an abort event to be published"


def test_no_abort_when_healthy(monkeypatch):
    monkeypatch.setattr(experiment, "set_chaos", lambda **kw: None)

    result = experiment.run_experiment(
        target="payment->store",
        latency_ms=200,
        burn_abort=10.0,
        poll_seconds=0.01,
        max_duration_s=0.05,
        config=get_config(),
        sampler_factory=_factory([1.0, 1.5, 2.0]),
    )

    assert result["aborted"] is False
    assert result["peak_burn"] < 10.0


def test_chaos_is_reset_even_on_pass(monkeypatch):
    chaos_calls: list[dict] = []
    monkeypatch.setattr(experiment, "set_chaos", lambda **kw: chaos_calls.append(kw))

    experiment.run_experiment(
        target="payment->store",
        latency_ms=300,
        burn_abort=10.0,
        poll_seconds=0.01,
        max_duration_s=0.05,
        config=get_config(),
        sampler_factory=_factory([1.0]),
    )

    # Last chaos call must leave the system clean.
    assert chaos_calls[-1].get("latency_ms") == 0
    assert chaos_calls[-1].get("error_rate") == 0.0
