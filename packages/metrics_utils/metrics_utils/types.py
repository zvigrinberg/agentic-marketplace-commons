from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union


# ---------------------------------------------------------------------------
# Type aliases for user-supplied callables
# ---------------------------------------------------------------------------

# (context_data, result, duration_seconds) -> metric value
ValueCalculator = Callable[[Dict[str, Any], Any, float], float]

# (context_data, result) -> dict of string attributes
AttributeExtractor = Callable[[Dict[str, Any], Any], Dict[str, str]]


# ---------------------------------------------------------------------------
# Metric type enum
# ---------------------------------------------------------------------------

class MetricType(str, Enum):
    """Supported OpenTelemetry metric instrument types."""
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"
    UP_DOWN_COUNTER = "up_down_counter"


# ---------------------------------------------------------------------------
# Metric configuration
# ---------------------------------------------------------------------------

@dataclass
class MetricConfig:
    """Complete definition of a single metric to record.

    Parameters
    ----------
    name:
        OTel instrument name (e.g. ``"llm_calls_total"``).
    metric_type:
        Which instrument kind to create.
    description:
        Human-readable description exposed to the metrics backend.
    unit:
        Unit string (e.g. ``"s"``, ``"tokens"``, ``"bytes"``).
    value_calculator:
        Optional callable ``(context_data, result, duration) -> float``.
        When omitted, sensible defaults are used per metric type (see below).
    extract_attributes:
        Optional callable ``(context_data, result) -> dict[str, str]``
        returning extra labels/attributes to attach.
    bucket_boundaries:
        Explicit histogram bucket boundaries.  Ignored for non-histogram types.
    include_status:
        If ``True`` (default), an automatic ``status=success|error`` attribute
        is added to every recording.
    include_exception_type:
        If ``True``, an ``exception_type`` attribute with the exception class
        name is added when the wrapped code raises.

    Default value logic (when *value_calculator* is ``None``):

    ============== ============================
    MetricType      Default value
    ============== ============================
    COUNTER         ``1``
    HISTOGRAM       elapsed duration (seconds)
    GAUGE           elapsed duration (seconds)
    UP_DOWN_COUNTER ``1``
    ============== ============================
    """

    name: str
    metric_type: MetricType
    description: str = ""
    unit: str = ""
    value_calculator: Optional[ValueCalculator] = None
    extract_attributes: Optional[AttributeExtractor] = None
    bucket_boundaries: Optional[Tuple[float, ...]] = None
    include_status: bool = True
    include_exception_type: bool = False
