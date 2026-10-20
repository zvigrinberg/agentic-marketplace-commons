"""Destination setup: MLflow OTLP exporter and Langfuse client.

Extracted from ``traces/otel_setup.py`` (MLflow OTLP wiring) and
``traces/langfuse_setup.py`` (Langfuse client attach), unchanged in behavior.
"""

from __future__ import annotations

import os
from typing import Callable

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ._types import LangfuseConfig, MlflowConfig

Cleanup = Callable[[], None]


def _resolve_mlflow_experiment_id(
    tracking_uri: str, configured_experiment_id: str | None
) -> str:
    if configured_experiment_id:
        return configured_experiment_id

    env_configured = os.getenv("MLFLOW_EXPERIMENT_ID")
    if env_configured:
        return env_configured

    experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "simple-agent-traces")
    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    experiment = mlflow.get_experiment_by_name(experiment_name)
    if experiment is None:
        return str(mlflow.create_experiment(experiment_name))
    return str(experiment.experiment_id)


def add_mlflow_exporter(
    provider: TracerProvider,
    config: MlflowConfig,
    service_name: str,
) -> Cleanup:
    """
    Attach an OTLP HTTP exporter targeting MLflow's trace ingestion endpoint.

    Reads ``config.tracking_uri`` / ``config.experiment_id`` / ``config.endpoint``
    with env-var fallbacks (same resolution as ``traces/otel_setup.py:setup_tracing``).
    Returns a no-op cleanup callable -- provider shutdown (handled by ``Tracer.shutdown``)
    flushes this processor.
    """
    tracking_uri = config.tracking_uri or os.getenv(
        "MLFLOW_TRACKING_URI", "http://localhost:5000"
    )
    experiment_id = _resolve_mlflow_experiment_id(tracking_uri, config.experiment_id)
    endpoint = config.endpoint or os.getenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        f"{tracking_uri.rstrip('/')}/v1/traces",
    )
    headers = {
        "x-mlflow-experiment-id": experiment_id,
    }

    exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", endpoint)
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
        f"x-mlflow-experiment-id={experiment_id}",
    )

    def _cleanup() -> None:
        # Provider.force_flush()/shutdown() (called by Tracer.shutdown) flush this
        # processor's exporter; nothing extra to do here.
        pass

    return _cleanup


def add_langfuse_exporter(provider: TracerProvider, config: LangfuseConfig) -> Cleanup:
    """
    Initialize the Langfuse client so it picks up spans off the same ``TracerProvider``.

    ``config`` is currently unused (``LangfuseConfig`` is a placeholder) -- the
    Langfuse SDK reads ``LANGFUSE_*`` env vars directly, same as
    ``traces/langfuse_setup.py``. Returns a cleanup callable that flushes the client.
    """
    del config  # placeholder for future extensibility; unused today.
    from langfuse import get_client

    get_client()

    def _cleanup() -> None:
        get_client().flush()

    return _cleanup
