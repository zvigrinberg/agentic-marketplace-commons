from __future__ import annotations

from typing import Any, Dict, Optional

from .types import MetricConfig, MetricType
from .instruments import get_or_create_instrument
from .decorator import _record_metric


def record(
    metric: MetricConfig,
    value: float,
    attributes: Optional[Dict[str, str]] = None,
) -> None:
    """Manually record a single metric value.

    Use this when neither the decorator nor the context manager fits —
    for example, recording a queue depth from a polling loop or a value
    received from an external system.

    Usage::

        record(queue_depth_gauge, value=42.0, attributes={"queue": "tasks"})
    """
    instrument = get_or_create_instrument(metric)
    attrs = dict(attributes) if attributes else {}
    _record_metric(instrument, metric, value, attrs)
