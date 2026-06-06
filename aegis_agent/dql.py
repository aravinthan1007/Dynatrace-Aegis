"""DQL snippets used by Aegis."""

from __future__ import annotations

from .config import AegisConfig


def build_burn_rate_query(config: AegisConfig) -> str:
    bad_fraction = max(1.0 - config.slo_target, 0.000001)
    return f"""
fetch spans, from: now()-{config.burn_window_seconds}s
| filter service.name == "frontend"
| summarize total = count(), bad = countIf(duration > {config.latency_threshold_ms * 1000000})
| fieldsAdd total = if(total == 0, 1, total)
| fieldsAdd bad_ratio = toDouble(bad) / total
| fieldsAdd burn_rate = bad_ratio / {bad_fraction}
| fields total, bad, bad_ratio, burn_rate
""".strip()
