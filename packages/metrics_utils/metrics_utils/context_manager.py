from __future__ import annotations

import time
from contextlib import contextmanager, asynccontextmanager
from typing import Any, Dict, List, Optional

from .types import MetricConfig, MetricType
from .instruments import get_or_create_instrument
from .decorator import _build_attributes, _compute_value, _record_metric


# ---------------------------------------------------------------------------
# Measurement context (yielded to the caller)
# ---------------------------------------------------------------------------

class MeasurementContext:
    """Handle yielded by ``measure()`` / ``ameasure()`` that lets the caller
    inject extra attributes while the block is executing."""

    def __init__(self) -> None:
        self._extra_attrs: Dict[str, str] = {}

    def set_attribute(self, key: str, value: str) -> None:
        """Add or overwrite a label on all metrics recorded for this block."""
        self._extra_attrs[key] = value

    @property
    def extra_attributes(self) -> Dict[str, str]:
        return dict(self._extra_attrs)


# ---------------------------------------------------------------------------
# Synchronous context manager
# ---------------------------------------------------------------------------

@contextmanager
def measure(
    *metric_configs: MetricConfig,
    attributes: Optional[Dict[str, str]] = None,
):
    """Context manager that records metrics for the enclosed code block.

    Usage::

        with measure(latency_histogram, attributes={"op": "db_query"}) as ctx:
            rows = db.execute(query)
            ctx.set_attribute("row_count", str(len(rows)))
    """
    if not metric_configs:
        raise ValueError("measure() requires at least one MetricConfig.")

    configs_instruments = [
        (cfg, get_or_create_instrument(cfg)) for cfg in metric_configs
    ]

    ctx = MeasurementContext()
    start_time = time.perf_counter()
    status = "success"
    exception: BaseException | None = None

    try:
        yield ctx
    except Exception as exc:
        status = "error"
        exception = exc
        raise
    finally:
        duration = time.perf_counter() - start_time
        # result is None for context-manager usage (no return value)
        context_data: Dict[str, Any] = {"args": (), "kwargs": {}}
        for cfg, instrument in configs_instruments:
            attrs = _build_attributes(cfg, context_data, None, status, exception)
            if attributes:
                attrs.update(attributes)
            attrs.update(ctx.extra_attributes)
            value = _compute_value(cfg, context_data, None, duration)
            _record_metric(instrument, cfg, value, attrs)


# ---------------------------------------------------------------------------
# Async context manager
# ---------------------------------------------------------------------------

@asynccontextmanager
async def ameasure(
    *metric_configs: MetricConfig,
    attributes: Optional[Dict[str, str]] = None,
):
    """Async context manager equivalent of ``measure()``.

    Usage::

        async with ameasure(latency_histogram) as ctx:
            result = await async_db_call()
            ctx.set_attribute("status_code", str(result.status))
    """
    if not metric_configs:
        raise ValueError("ameasure() requires at least one MetricConfig.")

    configs_instruments = [
        (cfg, get_or_create_instrument(cfg)) for cfg in metric_configs
    ]

    ctx = MeasurementContext()
    start_time = time.perf_counter()
    status = "success"
    exception: BaseException | None = None

    try:
        yield ctx
    except Exception as exc:
        status = "error"
        exception = exc
        raise
    finally:
        duration = time.perf_counter() - start_time
        context_data: Dict[str, Any] = {"args": (), "kwargs": {}}
        for cfg, instrument in configs_instruments:
            attrs = _build_attributes(cfg, context_data, None, status, exception)
            if attributes:
                attrs.update(attributes)
            attrs.update(ctx.extra_attributes)
            value = _compute_value(cfg, context_data, None, duration)
            _record_metric(instrument, cfg, value, attrs)
