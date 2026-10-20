"""Sample client demonstrating all metrics_utils usage patterns.

Prerequisites:
  1. This package installed: uv sync  (from the repo root)
  2. (Optional) Prometheus scraping http://localhost:9464/metrics

Run from the repo root:
    uv run python packages/metrics_utils/examples/sample_client.py

Metrics will be exposed at http://localhost:9464/metrics for Prometheus scraping.
"""

import asyncio
import random
import time
from queue import Queue

from metrics_utils import (
    MetricType,
    MetricConfig,
    MetricsProvider,
    ExporterConfig,
    ExporterType,
    observe,
    measure,
    record,
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Provider initialisation (once at startup)
# ═══════════════════════════════════════════════════════════════════════════

provider = MetricsProvider(
    service_name="llm-agent",
    exporters=[
        ExporterConfig(exporter_type=ExporterType.PROMETHEUS, port=9464),
    ],
    resource_attributes={"deployment.environment": "development"},
)

# Register histogram bucket boundaries before starting
provider.register_histogram_boundaries(
    "llm_duration_seconds",
    (0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0),
)
provider.register_histogram_boundaries(
    "llm_tokens_per_request",
    (50, 100, 200, 500, 1000, 2000, 4000),
)

provider.start()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Reusable metric configs
# ═══════════════════════════════════════════════════════════════════════════

call_counter = MetricConfig(
    name="llm_calls_total",
    metric_type=MetricType.COUNTER,
    description="Total LLM API invocations",
)

duration_histogram = MetricConfig(
    name="llm_duration_seconds",
    metric_type=MetricType.HISTOGRAM,
    description="LLM call duration distribution",
    unit="s",
    bucket_boundaries=(0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0),
)

tokens_histogram = MetricConfig(
    name="llm_tokens_per_request",
    metric_type=MetricType.HISTOGRAM,
    description="Token count distribution per LLM call",
    unit="tokens",
    bucket_boundaries=(50, 100, 200, 500, 1000, 2000, 4000),
    value_calculator=lambda ctx, res, dur: float(res.get("tokens_used", 0)) if res else 0.0,
    extract_attributes=lambda ctx, res: {"model": ctx["kwargs"].get("model", "unknown")},
)

tokens_consumed_counter = MetricConfig(
    name="llm_tokens_consumed_total",
    metric_type=MetricType.COUNTER,
    description="Cumulative tokens consumed across all calls",
    value_calculator=lambda ctx, res, dur: res.get("tokens_used", 0) if res else 0,
    extract_attributes=lambda ctx, res: {"model": ctx["kwargs"].get("model", "unknown")},
)

last_tokens_gauge = MetricConfig(
    name="llm_last_tokens_used",
    metric_type=MetricType.GAUGE,
    description="Tokens used in the most recent call (point-in-time)",
    value_calculator=lambda ctx, res, dur: float(res.get("tokens_used", 0)) if res else 0.0,
    extract_attributes=lambda ctx, res: {"model": ctx["kwargs"].get("model", "unknown")},
)

queue_depth_gauge = MetricConfig(
    name="task_queue_depth",
    metric_type=MetricType.GAUGE,
    description="Current depth of the task queue",
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Decorator — sync function with multiple metrics
# ═══════════════════════════════════════════════════════════════════════════

@observe(
    call_counter,
    duration_histogram,
    tokens_histogram,
    tokens_consumed_counter,
    last_tokens_gauge,
)
def call_llm(prompt: str, model: str = "gpt-4o"):
    """Simulated LLM call."""
    time.sleep(random.uniform(0.1, 1.0))
    tokens_used = random.randint(100, 1000)
    return {"response": "Analysis complete", "tokens_used": tokens_used}


# ═══════════════════════════════════════════════════════════════════════════
# 4. Decorator — async function
# ═══════════════════════════════════════════════════════════════════════════

@observe(call_counter, duration_histogram)
async def call_llm_async(prompt: str, model: str = "gpt-4o"):
    """Simulated async LLM call."""
    await asyncio.sleep(random.uniform(0.1, 0.5))
    return {"response": "Async analysis complete", "tokens_used": random.randint(100, 500)}


# ═══════════════════════════════════════════════════════════════════════════
# 5. Decorator — class method
# ═══════════════════════════════════════════════════════════════════════════

class AgentToolExecutor:
    @observe(
        MetricConfig(
            name="tool_execution_seconds",
            metric_type=MetricType.HISTOGRAM,
            unit="s",
            description="Duration of agent tool execution",
            extract_attributes=lambda ctx, res: {
                "tool_name": ctx["kwargs"].get("tool_name", "unknown"),
            },
        ),
        MetricConfig(
            name="tool_calls_total",
            metric_type=MetricType.COUNTER,
            description="Total agent tool invocations",
            extract_attributes=lambda ctx, res: {
                "tool_name": ctx["kwargs"].get("tool_name", "unknown"),
            },
        ),
    )
    def execute(self, tool_name: str, query: str):
        """Simulated tool execution."""
        time.sleep(random.uniform(0.05, 0.3))
        return {"status": "success", "data": f"Results for '{query}'"}


# ═══════════════════════════════════════════════════════════════════════════
# 6. Context manager — measure a code block
# ═══════════════════════════════════════════════════════════════════════════

db_latency = MetricConfig(
    name="db_query_seconds",
    metric_type=MetricType.HISTOGRAM,
    unit="s",
    description="Database query latency",
)


def process_batch(items):
    """Demonstrates context manager with mid-block attribute injection."""
    with measure(db_latency, attributes={"table": "embeddings"}) as ctx:
        time.sleep(random.uniform(0.01, 0.1))
        results = [{"id": i, "embedding": [0.0] * 128} for i in items]
        ctx.set_attribute("row_count", str(len(results)))
    return results


# ═══════════════════════════════════════════════════════════════════════════
# 7. Manual record — polling-style gauge
# ═══════════════════════════════════════════════════════════════════════════

task_queue: Queue = Queue()


def poll_queue_depth():
    """Record current queue depth as a gauge (no decorator needed)."""
    record(queue_depth_gauge, value=float(task_queue.qsize()), attributes={"queue": "default"})


# ═══════════════════════════════════════════════════════════════════════════
# 8. Main loop
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    executor = AgentToolExecutor()
    models = ["gpt-4o", "gpt-4o-mini", "claude-sonnet"]

    print("Agent running... Prometheus metrics at http://localhost:9464/metrics")

    try:
        for i in range(30):
            print(f"\n--- Iteration {i + 1}/30 ---")

            # Sync decorator
            model = random.choice(models)
            result = call_llm(prompt="Summarize this text", model=model)
            print(f"  LLM ({model}): {result['tokens_used']} tokens")

            # Async decorator
            async_result = asyncio.run(
                call_llm_async(prompt="Async analysis", model=model)
            )
            print(f"  Async LLM: {async_result['tokens_used']} tokens")

            # Class method
            tool_result = executor.execute(tool_name="web_search", query="OpenTelemetry")
            print(f"  Tool: {tool_result['status']}")

            # Context manager
            batch = process_batch(list(range(random.randint(5, 50))))
            print(f"  Batch: {len(batch)} rows")

            # Manual record
            for _ in range(random.randint(0, 10)):
                task_queue.put("task")
            poll_queue_depth()
            print(f"  Queue depth: {task_queue.qsize()}")

            time.sleep(10)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        provider.shutdown()
        print("Provider shut down cleanly.")
