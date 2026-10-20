from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from .types import MetricConfig, MetricType
from .provider import MetricsProvider


# ---------------------------------------------------------------------------
# Instrument cache
# ---------------------------------------------------------------------------

_INSTRUMENTS: Dict[str, Any] = {}


def _cache_key(cfg: MetricConfig) -> str:
    """Deterministic cache key for an instrument configuration."""
    key = f"{cfg.name}|{cfg.metric_type.value}"
    if cfg.bucket_boundaries is not None:
        key += f"|{'_'.join(str(b) for b in cfg.bucket_boundaries)}"
    return key


def get_or_create_instrument(cfg: MetricConfig) -> Any:
    """Return an existing OTel instrument or create a new one.

    The instrument is cached by ``(name, metric_type, bucket_boundaries)``
    so that the same config always returns the same object.
    """
    key = _cache_key(cfg)
    if key in _INSTRUMENTS:
        return _INSTRUMENTS[key]

    provider = MetricsProvider.get_instance()

    # Register histogram buckets (must happen before first instrument
    # creation when the provider is freshly started, but the provider
    # handles the ordering internally).
    if cfg.metric_type == MetricType.HISTOGRAM and cfg.bucket_boundaries is not None:
        provider.register_histogram_boundaries(cfg.name, cfg.bucket_boundaries)

    meter = provider.get_meter()

    instrument_kwargs: Dict[str, Any] = {
        "name": cfg.name,
        "description": cfg.description,
    }
    if cfg.unit:
        instrument_kwargs["unit"] = cfg.unit

    if cfg.metric_type == MetricType.COUNTER:
        inst = meter.create_counter(**instrument_kwargs)
    elif cfg.metric_type == MetricType.HISTOGRAM:
        inst = meter.create_histogram(**instrument_kwargs)
    elif cfg.metric_type == MetricType.GAUGE:
        inst = meter.create_gauge(**instrument_kwargs)
    elif cfg.metric_type == MetricType.UP_DOWN_COUNTER:
        inst = meter.create_up_down_counter(**instrument_kwargs)
    else:
        raise ValueError(f"Unsupported metric type: {cfg.metric_type}")

    _INSTRUMENTS[key] = inst
    return inst


def clear_instrument_cache() -> None:
    """Reset the instrument cache (useful for testing)."""
    _INSTRUMENTS.clear()
