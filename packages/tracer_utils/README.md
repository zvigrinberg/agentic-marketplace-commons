# tracer_utils

A small class-based abstraction over tracing SDKs (currently [OpenInference](https://github.com/Arize-ai/openinference)) and destinations (MLflow, Langfuse, or both). It wires up the OpenTelemetry `TracerProvider` + exporters for you and exposes one object -- `Tracer` -- for framework auto-instrumentation and manual span creation.

Extracted from, and functionally equivalent to, `traces/otel_setup.py` + `traces/langfuse_setup.py` -- those files are untouched; this package is the reusable, class-based version of the same logic.

## What's in here

| Name | What it is |
|---|---|
| `Tracer` | Main facade: construct it, call `instrument_frameworks()`, use `start_span()`, call `shutdown()` when done. |
| `TracerSdk` | Which tracing SDK to use for instrumentation (`OPEN_INFERENCE` today). |
| `TracerDestination` | Where spans are exported: `MLFLOW`, `LANGFUSE`, or both. |
| `SpanHandle` | Returned by `tracer.start_span(...)` and `tracer.get_current_span()`; carries the raw span plus a LangChain config for nested `invoke()` calls. Provides `set_attribute()`, `set_attributes()`, `set_input()`, and `set_output()` convenience methods. |
| `MlflowConfig` / `LangfuseConfig` | Optional explicit destination settings. Omit them to fall back to env vars. |

## Installation

**From the monorepo** (editable, recommended for development):

```bash
# From the repo root — installs all packages including tracer_utils
uv sync
```

**From GitHub** (for use in a consumer project):

```bash
pip install "tracer-utils @ git+https://github.com/your-org/agentic-marketplace-commons.git#subdirectory=packages/tracer_utils"
```

## Prerequisites

- `tracer_utils` installed (see above).
- For a live run (not just construction/shutdown): Ollama running with a pulled model, and whichever destinations you enable:
  - **MLflow**: `docker compose -f packages/tracer_utils/docker/docker-compose.yml up -d` (UI at `http://localhost:5000`)
  - **Langfuse**: `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` set in the project `.env`

## Quick start -- trace a simple LLM call to both MLflow and Langfuse

This is the minimal end-to-end example: construct a `Tracer` with the OpenInference SDK targeting both destinations, call `instrument_frameworks()` once, then make a normal LangChain call. No manual span code is needed -- auto-instrumentation captures it.

```python
from langchain_ollama import ChatOllama

from tracer_utils import Tracer, TracerDestination, TracerSdk

tracer = Tracer(
    sdk=TracerSdk.OPEN_INFERENCE,
    destinations=[TracerDestination.MLFLOW, TracerDestination.LANGFUSE],
    service_name="simple-llm-call",
)
tracer.instrument_frameworks()  # OpenInference auto-traces every LangChain call below

llm = ChatOllama(model="gemma3:270m", base_url="http://localhost:11434")

try:
    response = llm.invoke("What is 2 + 2? Reply with just the number.")
    print(response.content)
finally:
    tracer.shutdown()  # flush spans to MLflow + Langfuse and close the provider
```

Run from the repo root (after `uv sync`):

```bash
uv run python your_script.py
```

You should see the call show up as a `ChatOllama` span in both the MLflow experiment and the Langfuse project configured via your env vars.

## Using a single destination

Just pass one `TracerDestination` instead of a list:

```python
tracer = Tracer(
    sdk=TracerSdk.OPEN_INFERENCE,
    destinations=TracerDestination.MLFLOW,  # or TracerDestination.LANGFUSE
    service_name="simple-llm-call",
)
```

## Manual spans

Use `tracer.start_span(...)` to open a span around arbitrary code -- e.g. to group several LLM/tool calls under one named step. Inside a LangChain `@chain`, pass the enclosing `config` so nested `invoke()` calls stay on the same trace:

```python
from langchain_core.runnables import RunnableConfig, chain

@chain
def my_step(input_str: str, config: RunnableConfig) -> str:
    with tracer.start_span("my-operation", langchain_config=config) as handle:
        result = some_tool.invoke({"n": 3}, config=handle.langchain_invoke_config)
    return result
```

For a complete, runnable example with LLM calls, tool calls, LangGraph, async tools, and manual spans, see
[`examples/open_inference_langchain_demo.py`](examples/open_inference_langchain_demo.py).

## Span attributes

`SpanHandle` exposes convenience methods for setting attributes, input, and output on spans — no need to reach into the raw `handle.span` object.

### Via `SpanHandle` inside `start_span()`

```python
with tracer.start_span("my-operation", langchain_config=config) as handle:
    handle.set_attribute("custom.key", "value")
    handle.set_attributes({"custom.a": 1, "custom.b": "two"})
    handle.set_input({"query": "What is 2+2?"})

    result = some_tool.invoke({"n": 3}, config=handle.langchain_invoke_config)

    handle.set_output(result)
```

### Via `tracer.get_current_span()` inside auto-instrumented code

When running inside an auto-instrumented context (e.g. a LangChain `@chain` or tool), use `tracer.get_current_span()` to annotate the span that was created for you:

```python
@chain
def my_step(query: str) -> str:
    current = tracer.get_current_span()
    if current is not None:
        current.set_attribute("custom.label", "my_step")
    response = llm.invoke(query)
    return str(response.content)
```

`get_current_span()` returns `None` when there is no active span, so always check before calling methods on it.

## Overriding destination config explicitly

By default, `MlflowConfig()` / `LangfuseConfig()` are created for you and resolve everything from env vars. Pass your own to override specific fields:

```python
from tracer_utils import MlflowConfig, Tracer, TracerDestination, TracerSdk

tracer = Tracer(
    sdk=TracerSdk.OPEN_INFERENCE,
    destinations=[TracerDestination.MLFLOW],
    service_name="my-agent",
    mlflow_config=MlflowConfig(tracking_uri="http://other-mlflow:5000"),
)
```

### Env vars used when a config isn't explicitly provided

| Destination | Env var | Default |
|---|---|---|
| MLflow | `MLFLOW_TRACKING_URI` | `http://localhost:5000` |
| MLflow | `MLFLOW_EXPERIMENT_ID` | auto-resolved/created from `MLFLOW_EXPERIMENT_NAME` |
| MLflow | `MLFLOW_EXPERIMENT_NAME` | `simple-agent-traces` |
| MLflow | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `<tracking_uri>/v1/traces` |
| Langfuse | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | read directly by the Langfuse SDK |

## Checking the active trace/span

```python
tracer.print_trace_ids()                       # prints Trace ID / Span ID
trace_id, span_id = tracer.current_trace_and_span_ids()
```

## Shutdown

Always call `tracer.shutdown()` when you're done (e.g. in a `finally` block) -- it flushes every destination's exporter and shuts down the `TracerProvider`.

## Module layout

```
tracer_utils/
  __init__.py                    # Public re-exports
  _types.py                      # Enums, SpanHandle, MlflowConfig/LangfuseConfig
  _backend.py                    # Abstract TracerBackend
  _open_inference_backend.py     # OpenInference implementation (instrument/span/trace-ids)
  _exporters.py                  # Destination wiring: MLflow OTLP exporter, Langfuse client
  tracer.py                      # Tracer facade (the main public API)
```

## See also

- Structural, no-live-backend smoke test: [`tests/test_smoke.py`](tests/test_smoke.py)
- Full live demo with LLM calls, tool calls, LangGraph, async tools, and manual spans: [`examples/open_inference_langchain_demo.py`](examples/open_inference_langchain_demo.py)
