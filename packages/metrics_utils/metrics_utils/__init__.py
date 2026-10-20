"""metrics_utils — A declarative metric abstraction over OpenTelemetry.

Quick start::

    from metrics_utils import (
        MetricType, MetricConfig, MetricsProvider, ExporterConfig, ExporterType,
        observe, measure, ameasure, record,
    )

    provider = MetricsProvider(
        service_name="my-service",
        exporters=[ExporterConfig(exporter_type=ExporterType.PROMETHEUS)],
    )
    provider.start()

    @observe(
        MetricConfig(name="calls_total", metric_type=MetricType.COUNTER),
        MetricConfig(name="duration_seconds", metric_type=MetricType.HISTOGRAM, unit="s"),
    )
    def do_work():
        ...
"""

from .types import MetricType, MetricConfig, ValueCalculator, AttributeExtractor
from .provider import MetricsProvider, ExporterConfig, ExporterType
from .instruments import get_or_create_instrument, clear_instrument_cache
from .decorator import observe
from .context_manager import measure, ameasure, MeasurementContext
from .recorder import record

__all__ = [
    # Types
    "MetricType",
    "MetricConfig",
    "ValueCalculator",
    "AttributeExtractor",
    # Provider
    "MetricsProvider",
    "ExporterConfig",
    "ExporterType",
    # Instruments
    "get_or_create_instrument",
    "clear_instrument_cache",
    # Decorator
    "observe",
    # Context manager
    "measure",
    "ameasure",
    "MeasurementContext",
    # Manual recording
    "record",
]
