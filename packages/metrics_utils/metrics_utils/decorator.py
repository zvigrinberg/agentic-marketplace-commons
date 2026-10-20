from __future__ import annotations

import functools
import inspect
import time
from typing import Any, Callable, Dict, List

from .types import MetricConfig, MetricType
from .instruments import get_or_create_instrument


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_attributes(
    cfg: MetricConfig,
    context_data: Dict[str, Any],
    result: Any,
    status: str,
    exception: BaseException | None,
) -> Dict[str, str]:
    """Assemble the attribute dict for a single metric recording."""
    attrs: Dict[str, str] = {}

    if cfg.include_status:
        attrs["status"] = status

    if cfg.include_exception_type and exception is not None:
        attrs["exception_type"] = type(exception).__name__

    if cfg.extract_attributes:
        try:
            extra = cfg.extract_attributes(context_data, result)
            if extra:
                attrs.update(extra)
        except Exception:
            attrs["attr_extraction_error"] = "true"

    return attrs


def _compute_value(
    cfg: MetricConfig,
    context_data: Dict[str, Any],
    result: Any,
    duration: float,
) -> float:
    """Compute the metric value to record."""
    if cfg.value_calculator:
        return cfg.value_calculator(context_data, result, duration)

    # Sensible defaults when no calculator is provided
    if cfg.metric_type == MetricType.HISTOGRAM:
        return duration
    if cfg.metric_type == MetricType.GAUGE:
        return duration
    # COUNTER and UP_DOWN_COUNTER default to 1
    return 1


def _record_metric(instrument: Any, cfg: MetricConfig, value: float, attrs: Dict[str, str]) -> None:
    """Emit a single measurement to the appropriate OTel instrument."""
    if cfg.metric_type == MetricType.COUNTER:
        instrument.add(value, attributes=attrs)
    elif cfg.metric_type == MetricType.HISTOGRAM:
        instrument.record(value, attributes=attrs)
    elif cfg.metric_type == MetricType.GAUGE:
        instrument.set(value, attributes=attrs)
    elif cfg.metric_type == MetricType.UP_DOWN_COUNTER:
        instrument.add(value, attributes=attrs)


def _record_all(
    configs_and_instruments: List[tuple],
    context_data: Dict[str, Any],
    result: Any,
    duration: float,
    status: str,
    exception: BaseException | None,
) -> None:
    """Record all configured metrics in a single pass."""
    for cfg, instrument in configs_and_instruments:
        attrs = _build_attributes(cfg, context_data, result, status, exception)
        value = _compute_value(cfg, context_data, result, duration)
        _record_metric(instrument, cfg, value, attrs)


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------

def observe(*metric_configs: MetricConfig) -> Callable:
    """Decorator that records one or more metrics around a function call.

    Supports synchronous functions, async coroutines, and class/instance
    methods.

    Usage::

        @observe(counter_cfg, histogram_cfg)
        def my_function(x, y):
            ...

        @observe(latency_cfg)
        async def my_async_function(x):
            ...

        class MyService:
            @observe(call_counter)
            def do_work(self, item):
                ...
    """
    if not metric_configs:
        raise ValueError("observe() requires at least one MetricConfig argument.")

    configs = list(metric_configs)

    def decorator(func: Callable) -> Callable:
        # Lazily resolved on first call so the provider can be started after
        # decoration time.
        resolved: List[tuple] = []

        def _ensure_instruments() -> List[tuple]:
            if not resolved:
                for cfg in configs:
                    instrument = get_or_create_instrument(cfg)
                    resolved.append((cfg, instrument))
            return resolved

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                instruments = _ensure_instruments()
                context_data = {"args": args, "kwargs": kwargs}
                start_time = time.perf_counter()
                result = None
                status = "success"
                exception: BaseException | None = None
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as exc:
                    status = "error"
                    exception = exc
                    raise
                finally:
                    duration = time.perf_counter() - start_time
                    _record_all(instruments, context_data, result, duration, status, exception)

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                instruments = _ensure_instruments()
                context_data = {"args": args, "kwargs": kwargs}
                start_time = time.perf_counter()
                result = None
                status = "success"
                exception: BaseException | None = None
                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as exc:
                    status = "error"
                    exception = exc
                    raise
                finally:
                    duration = time.perf_counter() - start_time
                    _record_all(instruments, context_data, result, duration, status, exception)

            return sync_wrapper

    return decorator
