"""
Structural smoke test for ``tracer_utils`` -- no live MLflow/Langfuse server required.

Exercises Tracer construction, framework instrumentation, manual span creation
(inside and outside a LangChain ``@chain``), trace/span id resolution, and
shutdown. An explicit ``MlflowConfig(experiment_id=...)`` is passed so no live
MLflow HTTP call is made to resolve/create an experiment; the OTLP exporter
itself is created lazily and only touches the network on flush, where network
errors are swallowed internally by the OTLP SDK (logged, not raised).

Run with pytest from the repo root:
    uv run pytest packages/tracer_utils/tests/

For a full *live* run against real MLflow (and optionally Langfuse) services,
see ``examples/open_inference_langchain_demo.py`` and its module docstring --
that script talks to Ollama + MLflow for real and is the end-to-end equivalent
of this smoke test.
"""

from __future__ import annotations

from langchain_core.runnables import chain

from tracer_utils import MlflowConfig, Tracer, TracerDestination, TracerSdk


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"OK: {message}")


def test_tracer_smoke() -> None:
    tracer = Tracer(
        sdk=TracerSdk.OPEN_INFERENCE,
        destinations=TracerDestination.MLFLOW,
        service_name="tracer-utils-smoke-test",
        # Explicit experiment_id avoids a live MLflow HTTP call to resolve/create
        # an experiment by name -- keeps this test fully offline.
        mlflow_config=MlflowConfig(experiment_id="0"),
    )
    print("OK: Tracer constructed")

    tracer.instrument_frameworks()
    print("OK: instrument_frameworks() ran without error")

    # Plain manual span (no LangChain config).
    with tracer.start_span("smoke-test-span") as handle:
        _check(handle.span is not None, "start_span() yields a SpanHandle with a span")
        _check(
            handle.langchain_invoke_config is None,
            "langchain_invoke_config is None when no langchain_config was passed",
        )
        trace_id, span_id = tracer.current_trace_and_span_ids()
        _check(
            trace_id != "(no active span)" and span_id != "(no active span)",
            "current_trace_and_span_ids() resolves a valid trace/span inside start_span()",
        )
        tracer.print_trace_ids()

        # SpanHandle convenience methods -- should not raise.
        handle.set_attribute("test.key", "value")
        _check(True, "handle.set_attribute() does not raise")

        handle.set_attributes({"test.a": 1, "test.b": "two"})
        _check(True, "handle.set_attributes() does not raise")

        handle.set_input({"query": "test"})
        _check(True, "handle.set_input() does not raise")

        handle.set_output("result")
        _check(True, "handle.set_output() does not raise")

        # get_current_span() inside an active span should return a non-None SpanHandle.
        current = tracer.get_current_span()
        _check(current is not None, "get_current_span() returns a SpanHandle inside start_span()")

    # Outside any span, ids should report "(no active span)".
    trace_id, span_id = tracer.current_trace_and_span_ids()
    _check(
        trace_id == "(no active span)" and span_id == "(no active span)",
        "current_trace_and_span_ids() reports no active span outside start_span()",
    )

    # get_current_span() outside any span should return None.
    _check(
        tracer.get_current_span() is None,
        "get_current_span() returns None outside any span",
    )

    # Manual span nested inside a LangChain @chain, exercising langchain_invoke_config.
    @chain
    def smoke_chain(_: str, config) -> str:
        with tracer.start_span("smoke-test-nested-span", langchain_config=config) as handle:
            _check(
                handle.langchain_invoke_config is not None,
                "langchain_invoke_config is populated when langchain_config was passed",
            )
            tracer.print_trace_ids()
        return "smoke-chain-done"

    result = smoke_chain.invoke("")
    _check(result == "smoke-chain-done", "manual span works inside a LangChain @chain")

    tracer.shutdown()
    print("OK: shutdown() completed without raising")
    print("\nAll smoke test checks passed.")


if __name__ == "__main__":
    test_tracer_smoke()
