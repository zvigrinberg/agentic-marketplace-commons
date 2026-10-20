"""OpenInference ``TracerBackend`` implementation.

Extracted from ``traces/otel_setup.py`` (``instrument_langchain``,
``chain_root_span``, ``current_trace_and_span_ids``), unchanged in behavior.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, Optional

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace import TracerProvider

from ._backend import TracerBackend
from ._types import SpanHandle

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


def _langchain_parent_otel_context() -> Optional[Context]:
    """Resolve the OTEL context for the current LangChain-tracked parent span, if any."""
    try:
        from openinference.instrumentation.langchain import get_current_span

        parent_span = get_current_span()
        if parent_span is not None:
            span_context = parent_span.get_span_context()
            if span_context.is_valid:
                return trace.set_span_in_context(parent_span)
    except ImportError:
        pass
    return None


def _detach_langchain_invoke_config(config: "RunnableConfig") -> "RunnableConfig":
    """Strip callbacks/parent-run-id so a nested ``invoke()`` starts its own LangChain run tree."""
    from langchain_core.callbacks.manager import CallbackManager
    from langchain_core.runnables.config import patch_config

    callbacks = config.get("callbacks")
    handlers = list(getattr(callbacks, "handlers", [])) if callbacks else []
    return patch_config(
        config,
        callbacks=CallbackManager(handlers=handlers, parent_run_id=None),
    )


def _active_span() -> trace.Span:
    """
    Resolve the span for the current LangChain / OpenTelemetry context.

    OpenInference's LangChain tracer does not attach spans to the OTEL context
    (see commented-out ``context_api.attach`` in its tracer), so plain
    ``trace.get_current_span()`` is often invalid inside ``@chain`` and tools.
    """
    try:
        from openinference.instrumentation.langchain import (
            get_current_span as lc_get_current_span,
        )

        lc_span = lc_get_current_span()
        if lc_span is not None:
            lc_ctx = lc_span.get_span_context()
            if lc_ctx.is_valid:
                return lc_span
    except ImportError:
        pass
    return trace.get_current_span()


class OpenInferenceBackend(TracerBackend):
    """``TracerBackend`` built on the OpenInference instrumentation SDK."""

    def setup(self, provider: TracerProvider) -> None:
        # No extra one-time init needed beyond provider creation (handled by Tracer).
        pass

    def instrument_frameworks(self, provider: TracerProvider) -> None:
        """OpenInference auto-instrumentation for LangChain (LLM spans, tokens, I/O)."""
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=provider)

    @contextmanager
    def start_span(
        self, name: str, *, langchain_config: Optional["RunnableConfig"] = None
    ) -> Iterator[SpanHandle]:
        """
        One context manager: OpenInference CHAIN span + LangChain nesting for tools/LLMs.

        Pass ``langchain_config=config`` from the enclosing ``@chain`` when the block
        calls ``invoke`` / ``ainvoke``. Use the yielded ``SpanHandle.langchain_invoke_config``
        on those calls (not the outer ``config``) so the chain tree stays on one trace.
        """
        from openinference.instrumentation import OITracer, TraceConfig
        from openinference.semconv.trace import OpenInferenceSpanKindValues

        invoke_config = (
            _detach_langchain_invoke_config(langchain_config)
            if langchain_config is not None
            else None
        )

        # Use an "openinference.*"-prefixed instrumentation scope name (not __name__,
        # which would be "tracer_utils._open_inference_backend") so destinations that
        # filter spans by instrumentation scope -- e.g. Langfuse's default
        # should_export_span, which allowlists known LLM instrumentation scopes --
        # recognize and export this span. This span genuinely is OpenInference output
        # (OITracer + OpenInference semconv attributes), matching the convention
        # LangChainInstrumentor itself uses ("openinference.instrumentation.langchain").
        oi_tracer = OITracer(
            trace.get_tracer("openinference.instrumentation.manual"), TraceConfig()
        )
        # Resolve LangChain parent *before* clearing var_child_runnable_config (see below).
        parent_context = _langchain_parent_otel_context()
        with oi_tracer.start_as_current_span(
            name,
            context=parent_context,
            openinference_span_kind=OpenInferenceSpanKindValues.CHAIN,
        ) as span:
            lc_token = None
            if langchain_config is not None:
                from langchain_core.runnables.config import var_child_runnable_config

                lc_token = var_child_runnable_config.set({})
            try:
                yield SpanHandle(span=span, langchain_invoke_config=invoke_config)
            finally:
                if lc_token is not None:
                    from langchain_core.runnables.config import var_child_runnable_config

                    var_child_runnable_config.reset(lc_token)

    def get_current_span(self) -> Optional[SpanHandle]:
        """Return a ``SpanHandle`` wrapping the currently active span, or ``None``."""
        span = _active_span()
        if not span.get_span_context().is_valid:
            return None
        return SpanHandle(span=span, langchain_invoke_config=None)

    def current_trace_and_span_ids(self) -> tuple[str, str]:
        """Return ``(trace_id, span_id)`` for the active span, as 32- and 16-char hex."""
        span_ctx = _active_span().get_span_context()
        if not span_ctx.is_valid:
            return "(no active span)", "(no active span)"
        trace_id = format(span_ctx.trace_id, "032x")
        span_id = format(span_ctx.span_id, "016x")
        return trace_id, span_id
