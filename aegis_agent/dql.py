"""DQL snippets used by Aegis."""

from __future__ import annotations

from .config import AegisConfig


def build_burn_rate_query(config: AegisConfig) -> str:
    bad_fraction = max(1.0 - config.slo_target, 0.000001)
    # Keep the real record count as `total` (do NOT coerce 0 -> 1): the sampler
    # uses total == 0 to mean "no Grail data yet" and falls back to the realtime
    # local SLI, so the chart still jumps during the experiment despite ingest lag.
    return f"""
fetch spans, from: now()-{config.burn_window_seconds}s
| filter service.name == "{config.otel_service_name}"
| summarize total = count(), bad = countIf(duration > {config.latency_threshold_ms * 1000000})
| fieldsAdd bad_ratio = if(total == 0, 0.0, toDouble(bad) / total)
| fieldsAdd burn_rate = bad_ratio / {bad_fraction}
| fields total, bad, bad_ratio, burn_rate
""".strip()
