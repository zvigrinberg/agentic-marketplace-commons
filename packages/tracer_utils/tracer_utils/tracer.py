"""``Tracer`` facade -- the main public API of ``tracer_utils``."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Iterator, List, Optional, Union

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from ._backend import TracerBackend
from ._exporters import add_langfuse_exporter, add_mlflow_exporter
from ._open_inference_backend import OpenInferenceBackend
from ._types import (
    LangfuseConfig,
    MlflowConfig,
    SpanHandle,
    TracerDestination,
    TracerSdk,
)

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

_BACKENDS: dict[TracerSdk, type[TracerBackend]] = {
    TracerSdk.OPEN_INFERENCE: OpenInferenceBackend,
}


class Tracer:
    """
    Facade over a tracing SDK backend (e.g. OpenInference) and one or more
    destinations (MLflow, Langfuse, or both).

    Lifecycle: construct -> ``instrument_frameworks()`` -> use ``start_span()`` ->
    ``shutdown()``.
    """

    def __init__(
        self,
        *,
        sdk: TracerSdk = TracerSdk.OPEN_INFERENCE,
        destinations: Union[
            List[TracerDestination], TracerDestination
        ] = TracerDestination.MLFLOW,
        service_name: str = "traces-default",
        mlflow_config: Optional[MlflowConfig] = None,
        langfuse_config: Optional[LangfuseConfig] = None,
    ) -> None:
        if isinstance(destinations, TracerDestination):
            destinations = [destinations]

        # 1. Create TracerProvider with Resource.
        resource = Resource.create({"service.name": service_name})
        self._provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(self._provider)

        # 2 & 3. For each destination, create a default config if None was provided
        #        (all env-var defaults), then attach its exporter.
        self._destination_cleanups: List[Callable[[], None]] = []
        for destination in destinations:
            if destination is TracerDestination.MLFLOW:
                cfg = mlflow_config if mlflow_config is not None else MlflowConfig()
                cleanup = add_mlflow_exporter(self._provider, cfg, service_name)
            elif destination is TracerDestination.LANGFUSE:
                cfg = langfuse_config if langfuse_config is not None else LangfuseConfig()
                cleanup = add_langfuse_exporter(self._provider, cfg)
            else:
                raise ValueError(f"Unsupported tracer destination: {destination!r}")
            self._destination_cleanups.append(cleanup)

        # 4 & 5. Instantiate the correct TracerBackend and run its one-time setup.
        backend_cls = _BACKENDS.get(sdk)
        if backend_cls is None:
            raise ValueError(f"Unsupported tracer SDK: {sdk!r}")
        self._backend: TracerBackend = backend_cls()
        self._backend.setup(self._provider)

    def instrument_frameworks(self) -> None:
        """Enable LangChain auto-instrumentation (LangGraph support is a future addition)."""
        self._backend.instrument_frameworks(self._provider)

    @contextmanager
    def start_span(
        self, name: str, *, langchain_config: Optional["RunnableConfig"] = None
    ) -> Iterator[SpanHandle]:
        """Open a manual CHAIN span; use the yielded ``SpanHandle.langchain_invoke_config``
        for nested ``invoke()`` calls."""
        with self._backend.start_span(name, langchain_config=langchain_config) as handle:
            yield handle

    def get_current_span(self) -> Optional[SpanHandle]:
        """Return a SpanHandle for the currently active span, or None if no span is active."""
        return self._backend.get_current_span()

    def current_trace_and_span_ids(self) -> tuple[str, str]:
        return self._backend.current_trace_and_span_ids()

    def print_trace_ids(self) -> None:
        trace_id, span_id = self.current_trace_and_span_ids()
        print(f"Trace ID: {trace_id}")
        print(f"Span ID:  {span_id}")

    def shutdown(self) -> None:
        """Flush and shut down all exporters and the provider."""
        for cleanup in self._destination_cleanups:
            cleanup()
        self._provider.force_flush()
        self._provider.shutdown()
