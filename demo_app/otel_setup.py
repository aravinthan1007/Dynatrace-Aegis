"""OpenTelemetry setup for sending traces and metrics to Dynatrace OTLP."""

from __future__ import annotations

import os


def configure_telemetry(app=None, service_name: str = "aegis-demo-app") -> bool:
    endpoint = os.getenv("DT_OTLP_ENDPOINT", "").strip()
    token = os.getenv("DT_OTLP_TOKEN", "").strip()
    if not endpoint or not token:
        return False

    try:
        from opentelemetry import metrics
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        return False

    headers = {"Authorization": f"Api-Token {token}"}
    resource = Resource.create({"service.name": service_name})

    # DT_OTLP_ENDPOINT is the base (…/api/v2/otlp); OTLP/HTTP needs per-signal paths.
    base = endpoint.rstrip("/")
    if base.endswith("/v1/traces") or base.endswith("/v1/metrics"):
        base = base.rsplit("/v1/", 1)[0]
    traces_endpoint = f"{base}/v1/traces"
    metrics_endpoint = f"{base}/v1/metrics"

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_endpoint, headers=headers))
    )
    trace.set_tracer_provider(tracer_provider)

    # OTLP metrics: Dynatrace requires DELTA temporality (cumulative -> HTTP 400).
    # Default on now that temporality is correct; disable with DT_OTLP_METRICS=false.
    if os.getenv("DT_OTLP_METRICS", "true").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            from opentelemetry.sdk.metrics import (
                Counter,
                Histogram,
                ObservableCounter,
                ObservableGauge,
                ObservableUpDownCounter,
                UpDownCounter,
            )
            from opentelemetry.sdk.metrics.export import AggregationTemporality

            delta = AggregationTemporality.DELTA
            preferred_temporality = {
                Counter: delta,
                UpDownCounter: delta,
                Histogram: delta,
                ObservableCounter: delta,
                ObservableUpDownCounter: delta,
                ObservableGauge: delta,
            }
            metric_exporter = OTLPMetricExporter(
                endpoint=metrics_endpoint,
                headers=headers,
                preferred_temporality=preferred_temporality,
            )
        except Exception:
            # Fallback: env-based delta preference if the import/signature differs.
            os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "delta")
            metric_exporter = OTLPMetricExporter(endpoint=metrics_endpoint, headers=headers)
        metric_reader = PeriodicExportingMetricReader(metric_exporter)
        metrics.set_meter_provider(
            MeterProvider(resource=resource, metric_readers=[metric_reader])
        )
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    return True
