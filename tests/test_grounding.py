"""Grounding eval: the queries Aegis charts must actually return data.

This is the gate that catches the "notebook shows no data" problem — it runs the
real burn DQL against the tenant and asserts Grail returns rows. It's opt-in
(needs DT creds), and is expected to FAIL until span ingest is actually active —
which is exactly the signal we want.

    set RUN_GROUNDING_EVAL=1
    set DT_ENVIRONMENT=https://<env>.apps.dynatrace.com
    set OAUTH_CLIENT_ID=dt0s02....
    set OAUTH_CLIENT_SECRET=...
    pytest tests/test_grounding.py -q
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    not os.getenv("RUN_GROUNDING_EVAL"),
    reason="Set RUN_GROUNDING_EVAL=1 (+ DT creds) to run the data-grounding eval.",
)
def test_burn_query_returns_data():
    from aegis_agent.config import get_config
    from aegis_agent.dql import build_burn_rate_query
    from aegis_agent.dynatrace import query_dql

    config = get_config()
    assert config.has_dynatrace, "DT_ENVIRONMENT must be set"
    rows = query_dql(build_burn_rate_query(config), config)
    assert rows, (
        "Burn DQL returned no rows — Grail has no spans for the service. "
        "Span ingest is not active; the notebook charts will be empty."
    )
