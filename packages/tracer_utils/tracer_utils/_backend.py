"""Abstract tracing-SDK backend contract used by the ``Tracer`` facade."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, Optional

from opentelemetry.sdk.trace import TracerProvider

from ._types import SpanHandle

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


class TracerBackend(ABC):
    """SDK-specific tracing logic (e.g. OpenInference).

    A backend knows how to enable framework auto-instrumentation, open manual
    spans, and resolve the currently active trace/span ids for its SDK. The
    ``Tracer`` facade owns the ``TracerProvider``/exporters and delegates all
    SDK-specific work to a ``TracerBackend`` implementation.
    """

    @abstractmethod
    def setup(self, provider: TracerProvider) -> None:
        """One-time init after the provider is created."""

    @abstractmethod
    def instrument_frameworks(self, provider: TracerProvider) -> None:
        """Enable auto-instrumentation for supported frameworks (e.g. LangChain)."""

    @abstractmethod
    @contextmanager
    def start_span(
        self, name: str, *, langchain_config: Optional["RunnableConfig"] = None
    ) -> Iterator[SpanHandle]:
        """Create a manual CHAIN span (like ``chain_root_span``) and yield a ``SpanHandle``."""
        ...

    @abstractmethod
    def get_current_span(self) -> Optional[SpanHandle]:
        """Return a SpanHandle for the currently active span, or None."""

    @abstractmethod
    def current_trace_and_span_ids(self) -> tuple[str, str]:
        """Return ``(trace_id, span_id)`` hex strings for the active span."""
