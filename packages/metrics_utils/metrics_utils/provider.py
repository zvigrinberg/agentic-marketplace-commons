from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import (
    ExplicitBucketHistogramAggregation,
    View,
)
from opentelemetry.sdk.resources import Resource


# ---------------------------------------------------------------------------
# Exporter configuration
# ---------------------------------------------------------------------------

class ExporterType(str, Enum):
    """Supported metric exporter backends."""
    PROMETHEUS = "prometheus"
    OTLP_HTTP = "otlp_http"
    OTLP_GRPC = "otlp_grpc"
    CONSOLE = "console"


@dataclass
class ExporterConfig:
    """Configuration for a single metric exporter.

    Parameters
    ----------
    exporter_type:
        Which exporter to use.
    endpoint:
        Remote endpoint for OTLP exporters (ignored for Prometheus/console).
    port:
        HTTP port for the Prometheus scrape endpoint (default ``9464``).
    headers:
        Extra headers sent with OTLP requests (e.g. auth tokens).
    """

    exporter_type: ExporterType
    endpoint: Optional[str] = None
    port: int = 9464
    headers: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# Metrics provider (singleton)
# ---------------------------------------------------------------------------

class MetricsProvider:
    """Central manager for the OpenTelemetry metrics SDK.

    Holds the ``MeterProvider``, registers histogram views, and owns the
    lifecycle (``start`` / ``shutdown``).  Only one active provider is
    supported at a time (singleton pattern).

    Usage::

        provider = MetricsProvider(
            service_name="my-service",
            exporters=[ExporterConfig(exporter_type=ExporterType.PROMETHEUS)],
        )
        provider.start()
        ...
        provider.shutdown()
    """

    _instance: Optional["MetricsProvider"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        service_name: str = "unknown_service",
        exporters: Optional[List[ExporterConfig]] = None,
        resource_attributes: Optional[Dict[str, str]] = None,
    ) -> None:
        self._service_name = service_name
        self._exporter_configs = exporters or [
            ExporterConfig(exporter_type=ExporterType.PROMETHEUS)
        ]
        self._resource_attributes = resource_attributes or {}
        self._meter_provider: Optional[MeterProvider] = None
        self._meter: Any = None
        self._started = False
        self._histogram_views: Dict[str, Sequence[float]] = {}
        self._http_server_started = False

    # -- Singleton access ---------------------------------------------------

    @classmethod
    def get_instance(cls) -> "MetricsProvider":
        """Return the active provider, raising if none has been started."""
        if cls._instance is None or not cls._instance._started:
            raise RuntimeError(
                "MetricsProvider has not been started. "
                "Call MetricsProvider(...).start() first."
            )
        return cls._instance

    # -- Histogram view registration ----------------------------------------

    def register_histogram_boundaries(
        self, name: str, boundaries: Sequence[float]
    ) -> None:
        """Register custom bucket boundaries for a histogram instrument.

        Must be called **before** ``start()``.
        """
        bounds = tuple(boundaries)
        if name in self._histogram_views:
            if self._histogram_views[name] != bounds:
                raise ValueError(
                    f"Conflicting bucket boundaries for histogram '{name}'"
                )
            return
        if self._started:
            raise RuntimeError(
                f"Cannot set bucket boundaries for '{name}' after the "
                "metrics provider has already started."
            )
        self._histogram_views[name] = bounds

    # -- Lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Initialise the OTel MeterProvider, register exporters, and
        set this instance as the global singleton."""
        if self._started:
            return

        with self._lock:
            if self._started:
                return

            readers = self._build_readers()
            views = self._build_views()

            resource_attrs = {"service.name": self._service_name}
            resource_attrs.update(self._resource_attributes)
            resource = Resource.create(resource_attrs)

            self._meter_provider = MeterProvider(
                metric_readers=readers,
                views=views if views else None,
                resource=resource,
            )
            metrics.set_meter_provider(self._meter_provider)
            self._meter = metrics.get_meter(self._service_name)
            self._started = True
            MetricsProvider._instance = self

    def shutdown(self) -> None:
        """Flush pending metrics and shut down the provider."""
        if self._meter_provider is not None:
            self._meter_provider.shutdown()
        self._started = False
        if MetricsProvider._instance is self:
            MetricsProvider._instance = None

    def get_meter(self) -> Any:
        """Return the ``Meter`` used to create instruments."""
        if not self._started:
            raise RuntimeError("MetricsProvider has not been started yet.")
        return self._meter

    # -- Internal helpers ---------------------------------------------------

    def _build_readers(self) -> list:
        readers: list = []
        for cfg in self._exporter_configs:
            if cfg.exporter_type == ExporterType.PROMETHEUS:
                from opentelemetry.exporter.prometheus import (
                    PrometheusMetricReader,
                )
                from prometheus_client import start_http_server

                reader = PrometheusMetricReader()
                if not self._http_server_started:
                    start_http_server(port=cfg.port)
                    self._http_server_started = True
                readers.append(reader)

            elif cfg.exporter_type == ExporterType.OTLP_HTTP:
                from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                    OTLPMetricExporter,
                )
                from opentelemetry.sdk.metrics.export import (
                    PeriodicExportingMetricReader,
                )

                exporter = OTLPMetricExporter(
                    endpoint=cfg.endpoint or "http://localhost:4318/v1/metrics",
                    headers=cfg.headers or {},
                )
                readers.append(PeriodicExportingMetricReader(exporter))

            elif cfg.exporter_type == ExporterType.OTLP_GRPC:
                from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                    OTLPMetricExporter as GrpcExporter,
                )
                from opentelemetry.sdk.metrics.export import (
                    PeriodicExportingMetricReader,
                )

                exporter = GrpcExporter(
                    endpoint=cfg.endpoint or "http://localhost:4317",
                    headers=cfg.headers or {},
                )
                readers.append(PeriodicExportingMetricReader(exporter))

            elif cfg.exporter_type == ExporterType.CONSOLE:
                from opentelemetry.sdk.metrics.export import (
                    ConsoleMetricExporter,
                    PeriodicExportingMetricReader,
                )

                readers.append(
                    PeriodicExportingMetricReader(ConsoleMetricExporter())
                )
            else:
                raise ValueError(f"Unsupported exporter type: {cfg.exporter_type}")

        if not readers:
            raise ValueError("At least one exporter must be configured.")
        return readers

    def _build_views(self) -> list:
        return [
            View(
                instrument_name=name,
                aggregation=ExplicitBucketHistogramAggregation(
                    boundaries=list(bounds)
                ),
            )
            for name, bounds in self._histogram_views.items()
        ]
