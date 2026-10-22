from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from fastapi import FastAPI, Request
import uvicorn
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace
from opentelemetry.trace import SpanContext, TraceFlags, NonRecordingSpan

from tracer_utils import Tracer, TracerDestination, TracerSdk

# Load environment variables from .env file
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# Initialize the tracer
tracer = Tracer(
    sdk=TracerSdk.OPEN_INFERENCE,
    destinations=TracerDestination.MLFLOW,
    service_name="sub-agent",
)

# Instrument frameworks (e.g., LangChain, LangGraph if used)
tracer.instrument_frameworks()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown - flush spans
    tracer.shutdown()
    print("Tracer shutdown complete - spans flushed")


app = FastAPI(title="Sub Agent", lifespan=lifespan)


# --- LangGraph subagent ---

@tool
def hello_tool() -> str:
    """A simple tool that prints a greeting message."""
    print("hello from sub agent tool")
    return "hello from sub agent tool"


class SubAgentState(TypedDict):
    message: str


def _hello_node(state: SubAgentState) -> SubAgentState:
    """Node that invokes the hello tool."""
    hello_tool.invoke({})
    return state


def _build_subagent_graph():
    """Build a simple LangGraph with a single node."""
    graph_builder = StateGraph(SubAgentState)
    graph_builder.add_node("hello_node", _hello_node)
    graph_builder.add_edge(START, "hello_node")
    graph_builder.add_edge("hello_node", END)
    return graph_builder.compile()


def subagent(message: str = "") -> str:
    """Run the subagent LangGraph with a single tool node."""
    graph = _build_subagent_graph()
    result = graph.invoke({"message": message})
    return result


def parse_traceparent(traceparent: str) -> tuple[str, str] | None:
    """Parse traceparent header and return (trace_id, span_id) or None if invalid.
    
    Format: 00-{trace_id}-{span_id}-{flags}
    Example: 00-abcdef1234567890abcdef1234567890-fedcba0987654321-01
    """
    if not traceparent:
        return None
    parts = traceparent.split("-")
    if len(parts) != 4:
        return None
    # parts[0] = version (00), parts[1] = trace_id, parts[2] = span_id, parts[3] = flags
    trace_id = parts[1]
    span_id = parts[2]
    return trace_id, span_id


def call_subagent_with_parent_context(trace_id_hex: str, span_id_hex: str):
    """Create a span linked to the given parent trace_id and span_id, then run subagent.
    
    Args:
        trace_id_hex: 32-character hex string for trace ID
        span_id_hex: 16-character hex string for span ID
    """
    # Convert hex strings to integers
    parent_trace_id = int(trace_id_hex, 16)
    parent_span_id = int(span_id_hex, 16)

    # Create a SpanContext representing the remote parent
    parent_span_context = SpanContext(
        trace_id=parent_trace_id,
        span_id=parent_span_id,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )

    # Attach the parent context
    parent_ctx = trace.set_span_in_context(NonRecordingSpan(parent_span_context))

    # Get the OITracer and start a span with the parent context
    from openinference.instrumentation import OITracer, TraceConfig
    from openinference.semconv.trace import OpenInferenceSpanKindValues

    oi_tracer = OITracer(
        trace.get_tracer("openinference.instrumentation.manual"), TraceConfig()
    )

    with oi_tracer.start_as_current_span(
        "subagent-with-remote-parent",
        context=parent_ctx,
        openinference_span_kind=OpenInferenceSpanKindValues.CHAIN,
    ) as span:
        print(f"Created span under parent trace: {trace_id_hex}")
        print(f"Created span under parent span: {span_id_hex}")
        result = subagent()
        return result


@app.post("/second")
async def second_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = None

    # Print detailed request information
    print("=" * 50)
    print("REQUEST RECEIVED")
    print("=" * 50)
    print(f"Method: {request.method}")
    print(f"URL: {request.url}")
    print(f"Path: {request.url.path}")
    print(f"Query Params: {dict(request.query_params)}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Client: {request.client.host}:{request.client.port}" if request.client else "Client: None")
    print(f"Body: {body}")
    print("=" * 50)

    # Extract trace_id and span_id from traceparent header
    traceparent = request.headers.get("traceparent")
    if traceparent:
        parsed = parse_traceparent(traceparent)
        if parsed:
            trace_id, span_id = parsed
            print(f"Extracted from traceparent - trace_id: {trace_id}, span_id: {span_id}")
            # Call subagent with the extracted parent context
            call_subagent_with_parent_context(trace_id, span_id)
        else:
            print(f"Invalid traceparent format: {traceparent}")
    else:
        print("No traceparent header found in request")

    return {
        "status": "ok",
        "request_info": {
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "headers": dict(request.headers),
            "client": f"{request.client.host}:{request.client.port}" if request.client else None,
            "body": body,
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9999)
