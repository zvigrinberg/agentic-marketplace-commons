# metrics_utils

A declarative metric abstraction over OpenTelemetry for Python. Define metrics as configuration, attach them to your code with decorators, context managers, or manual calls, and export to any supported backend.

## Installation

Install the dependencies (from `metric_utils_agent/`):

```bash
pip install -r requirements.txt
```

Required packages:

- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-exporter-prometheus`
- `prometheus-client`
- `opentelemetry-exporter-otlp-proto-http` (optional, for OTLP export)

## Quick Start

### 1. Initialise the provider

Before recording any metrics you must create and start a `MetricsProvider`. This is done **once** at application startup.

```python
from metrics_utils import MetricsProvider, ExporterConfig, ExporterType

provider = MetricsProvider(
    service_name="my-service",
    exporters=[
        ExporterConfig(exporter_type=ExporterType.PROMETHEUS, port=9464),
    ],
)
provider.start()
```

At shutdown, call `provider.shutdown()` to flush pending metrics.

### 2. Define metrics

Each metric is described by a `MetricConfig`:

```python
from metrics_utils import MetricType, MetricConfig

call_counter = MetricConfig(
    name="http_requests_total",
    metric_type=MetricType.COUNTER,
    description="Total HTTP requests",
)

latency_histogram = MetricConfig(
    name="http_request_duration_seconds",
    metric_type=MetricType.HISTOGRAM,
    description="Request latency distribution",
    unit="s",
    bucket_boundaries=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
```

## Usage Patterns

### Decorator — `@observe`

Attach one or more metrics to a function. Works with sync functions, async functions, and class methods.

```python
from metrics_utils import observe

@observe(call_counter, latency_histogram)
def handle_request(path: str):
    ...
    return response
```

**Async function:**

```python
@observe(call_counter, latency_histogram)
async def handle_request_async(path: str):
    ...
    return response
```

**Class method:**

```python
class OrderService:
    @observe(call_counter, latency_histogram)
    def create_order(self, item: str, quantity: int):
        ...
```

### Context Manager — `measure`

Measure a specific code block within a function. Yields a `MeasurementContext` that lets you add attributes during execution.

```python
from metrics_utils import measure

db_latency = MetricConfig(
    name="db_query_seconds",
    metric_type=MetricType.HISTOGRAM,
    unit="s",
    description="Database query latency",
)

def process_order(order_id: str):
    with measure(db_latency, attributes={"table": "orders"}) as ctx:
        rows = db.execute("SELECT * FROM orders WHERE id = ?", order_id)
        ctx.set_attribute("row_count", str(len(rows)))
    return rows
```

**Async version:**

```python
from metrics_utils import ameasure

async def fetch_data():
    async with ameasure(db_latency, attributes={"table": "users"}) as ctx:
        result = await async_db.execute(query)
        ctx.set_attribute("row_count", str(len(result)))
    return result
```

### Manual Recording — `record`

Record a metric value directly, without a decorator or context manager. Useful for values from external sources, polling loops, or callbacks.

```python
from metrics_utils import record

queue_depth = MetricConfig(
    name="task_queue_depth",
    metric_type=MetricType.GAUGE,
    description="Current task queue depth",
)

record(queue_depth, value=42.0, attributes={"queue": "default"})
```

## Metric Types

| Type | Enum Value | Description | Default value (no `value_calculator`) |
|---|---|---|---|
| Counter | `MetricType.COUNTER` | Monotonically increasing count | `1` |
| Histogram | `MetricType.HISTOGRAM` | Distribution of values in buckets | elapsed duration (seconds) |
| Gauge | `MetricType.GAUGE` | Point-in-time measurement | elapsed duration (seconds) |
| UpDownCounter | `MetricType.UP_DOWN_COUNTER` | Count that can increase or decrease | `1` |

## MetricConfig Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | *required* | Instrument name (e.g. `"llm_calls_total"`) |
| `metric_type` | `MetricType` | *required* | Instrument kind |
| `description` | `str` | `""` | Human-readable description |
| `unit` | `str` | `""` | Unit label (e.g. `"s"`, `"tokens"`, `"bytes"`) |
| `value_calculator` | `Callable` | `None` | `(context_data, result, duration) -> float` |
| `extract_attributes` | `Callable` | `None` | `(context_data, result) -> dict[str, str]` |
| `bucket_boundaries` | `tuple[float]` | `None` | Histogram bucket boundaries |
| `include_status` | `bool` | `True` | Auto-add `status=success\|error` attribute |
| `include_exception_type` | `bool` | `False` | Add `exception_type` attribute on errors |

### Custom Value Calculators

Override the default metric value by providing a `value_calculator`. It receives three arguments:

- `context_data` — dict with `"args"` and `"kwargs"` of the decorated function
- `result` — the return value (or `None` if the function raised)
- `duration` — wall-clock time in seconds

```python
tokens_counter = MetricConfig(
    name="llm_tokens_total",
    metric_type=MetricType.COUNTER,
    value_calculator=lambda ctx, res, dur: res.get("tokens_used", 0) if res else 0,
    description="Total tokens consumed",
)
```

### Custom Attribute Extractors

Add dynamic labels/attributes per invocation:

```python
llm_histogram = MetricConfig(
    name="llm_duration_seconds",
    metric_type=MetricType.HISTOGRAM,
    unit="s",
    extract_attributes=lambda ctx, res: {
        "model": ctx["kwargs"].get("model", "unknown"),
    },
    description="LLM call latency by model",
)
```

## Exporters

Configure exporters when creating the provider. Multiple exporters can run simultaneously.

```python
provider = MetricsProvider(
    service_name="my-service",
    exporters=[
        # Local Prometheus endpoint on port 9464
        ExporterConfig(exporter_type=ExporterType.PROMETHEUS, port=9464),

        # OTLP HTTP exporter (e.g. for Grafana Cloud, Datadog, etc.)
        ExporterConfig(
            exporter_type=ExporterType.OTLP_HTTP,
            endpoint="https://otlp.example.com/v1/metrics",
            headers={"Authorization": "Bearer <token>"},
        ),

        # Console exporter (prints to stdout, useful for debugging)
        ExporterConfig(exporter_type=ExporterType.CONSOLE),
    ],
)
```

| Exporter | `ExporterType` | Key config |
|---|---|---|
| Prometheus | `PROMETHEUS` | `port` (default `9464`) |
| OTLP over HTTP | `OTLP_HTTP` | `endpoint`, `headers` |
| OTLP over gRPC | `OTLP_GRPC` | `endpoint`, `headers` |
| Console (stdout) | `CONSOLE` | — |

## Full Example

```python
import time
import random
from metrics_utils import (
    MetricType, MetricConfig, MetricsProvider, ExporterConfig, ExporterType,
    observe, measure, record,
)

# --- Provider ---
provider = MetricsProvider(
    service_name="llm-agent",
    exporters=[ExporterConfig(exporter_type=ExporterType.PROMETHEUS)],
)
provider.start()

# --- Metric definitions ---
call_counter = MetricConfig(
    name="llm_calls_total",
    metric_type=MetricType.COUNTER,
    description="Total LLM invocations",
)

duration_hist = MetricConfig(
    name="llm_duration_seconds",
    metric_type=MetricType.HISTOGRAM,
    unit="s",
    bucket_boundaries=(0.1, 0.5, 1.0, 2.5, 5.0),
    description="LLM call latency",
)

tokens_gauge = MetricConfig(
    name="llm_last_tokens",
    metric_type=MetricType.GAUGE,
    value_calculator=lambda ctx, res, dur: float(res.get("tokens", 0)) if res else 0.0,
    extract_attributes=lambda ctx, res: {"model": ctx["kwargs"].get("model", "unknown")},
    description="Tokens used in the last call",
)

# --- Decorator usage ---
@observe(call_counter, duration_hist, tokens_gauge)
def call_llm(prompt: str, model: str = "gpt-4o"):
    time.sleep(random.uniform(0.1, 1.0))
    return {"response": "done", "tokens": random.randint(100, 800)}

# --- Context manager usage ---
db_hist = MetricConfig(
    name="db_query_seconds",
    metric_type=MetricType.HISTOGRAM,
    unit="s",
)

def fetch_user(user_id: int):
    with measure(db_hist, attributes={"table": "users"}) as ctx:
        time.sleep(0.05)
        ctx.set_attribute("cache", "miss")
    return {"id": user_id}

# --- Manual record usage ---
queue_gauge = MetricConfig(
    name="queue_depth",
    metric_type=MetricType.GAUGE,
)

# --- Run ---
if __name__ == "__main__":
    try:
        for i in range(10):
            call_llm(prompt="Hello", model="gpt-4o")
            fetch_user(user_id=i)
            record(queue_gauge, value=float(i * 3), attributes={"queue": "tasks"})
            time.sleep(5)
    finally:
        provider.shutdown()
```

## Running with Docker

From the `metric_utils_agent/` directory:

```bash
docker compose up --build
```

This starts three services:

| Service | URL |
|---|---|
| Sample client (Prometheus scrape) | `http://localhost:9464/metrics` |
| Prometheus | `http://localhost:9091` |
| Grafana | `http://localhost:3001` |

Grafana login: **admin** / **admin**. The Prometheus datasource is auto-provisioned.
