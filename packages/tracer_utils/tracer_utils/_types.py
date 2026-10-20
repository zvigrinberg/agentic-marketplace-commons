"""Enums, span handle, and destination config dataclasses for ``tracer_utils``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, NamedTuple, Optional

from opentelemetry import trace
from opentelemetry.util.types import AttributeValue

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


class TracerSdk(Enum):
    """Tracing SDK used for framework auto-instrumentation and manual spans."""

    OPEN_INFERENCE = "open_inference"


class TracerDestination(Enum):
    """Backend(s) that exported spans are sent to."""

    MLFLOW = "mlflow"
    LANGFUSE = "langfuse"


class SpanHandle(NamedTuple):
    """Active manual span plus an optional detached LangChain config for nested invokes.

    Mirrors the ``ChainRootSpan`` used in ``traces/otel_setup.py``.
    """

    span: trace.Span
    langchain_invoke_config: Optional["RunnableConfig"]

    def set_attribute(self, key: str, value: AttributeValue) -> None:
        """Set a single attribute on the underlying span."""
        self.span.set_attribute(key, value)

    def set_attributes(self, attributes: dict[str, AttributeValue]) -> None:
        """Set multiple attributes on the underlying span."""
        self.span.set_attributes(attributes)

    def set_input(self, value: Any) -> None:
        """Set the OpenInference input attribute (no-op if the span doesn't support it)."""
        if hasattr(self.span, "set_input"):
            self.span.set_input(value)

    def set_output(self, value: Any) -> None:
        """Set the OpenInference output attribute (no-op if the span doesn't support it)."""
        if hasattr(self.span, "set_output"):
            self.span.set_output(value)


@dataclass
class MlflowConfig:
    """MLflow OTLP destination settings. All fields fall back to env vars when ``None``."""

    tracking_uri: Optional[str] = None
    """MLFLOW_TRACKING_URI env var, defaults to "http://localhost:5000"."""

    experiment_id: Optional[str] = None
    """MLFLOW_EXPERIMENT_ID env var, or auto-resolved/created by MLFLOW_EXPERIMENT_NAME."""

    endpoint: Optional[str] = None
    """OTEL_EXPORTER_OTLP_TRACES_ENDPOINT env var, defaults to "<tracking_uri>/v1/traces"."""


@dataclass
class LangfuseConfig:
    """Langfuse destination settings.

    The Langfuse SDK reads ``LANGFUSE_*`` env vars directly. This dataclass is a
    placeholder for future extensibility.
    """
