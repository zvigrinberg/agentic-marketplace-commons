"""
Primary agent in a two-service distributed tracing demo.

This FastAPI app (port 8888) shows how to keep one trace across services when using
``tracer_utils`` with OpenInference, LangGraph, and MLflow:

  1. A request hits ``POST /first``, which runs a small LangGraph.
  2. A graph node invokes ``print_trace_info_tool``, which reads the current
     ``trace_id`` / ``span_id`` from the active span.
  3. The tool calls ``sub_agent.py`` over HTTP at ``http://localhost:9999/second``
     and sends a W3C ``traceparent`` header built from that context.
  4. The sub-agent parses ``traceparent`` and runs its LangGraph under a child span
     linked to the same trace (see ``packages/tracer_utils/examples/sub_agent.py``).

Prerequisites:
  - ``uv sync`` from the repo root
  - MLflow for traces: ``docker compose -f packages/tracer_utils/docker/docker-compose.yml up -d``
    (UI at http://localhost:5000)
  - Optional: project root ``.env`` for Langfuse or custom MLflow settings

Testing requires **both** example processes running:

  Terminal 1 — start the sub-agent first (listens on :9999):

    uv run python packages/tracer_utils/examples/sub_agent.py

  Terminal 2 — start the primary agent (listens on :8888):

    uv run python packages/tracer_utils/examples/primary_agent.py

  Terminal 3 — trigger the primary agent (this runs the graph and the outbound call
  to the sub-agent):

    curl -X POST 'http://localhost:8888/first?param1=value1'

In the MLflow web UI (http://localhost:5000), open the experiment traces: spans
from the sub-agent appear on the same trace as the primary agent, nested under the
parent trace and span IDs that were active when the primary agent called the
sub-agent.

Run all ``uv run`` commands from the repository root.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from fastapi import FastAPI, Request
import uvicorn
import requests
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph

from tracer_utils import Tracer, TracerDestination, TracerSdk

# Load environment variables from .env file
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# Initialize the tracer
tracer = Tracer(
    sdk=TracerSdk.OPEN_INFERENCE,
    destinations=TracerDestination.MLFLOW,
    service_name="primary-agent",
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


app = FastAPI(title="Primary Agent", lifespan=lifespan)


# --- LangGraph primary agent ---

@tool
def print_trace_info_tool() -> str:
    """A tool that prints the current trace_id and span_id."""
    trace_id, span_id = tracer.current_trace_and_span_ids()
    print("=" * 50)
    print("TRACE INFO FROM PRIMARY AGENT TOOL")
    print(f"trace_id: {trace_id}")
    print(f"span_id: {span_id}")
    print("=" * 50)

    # Build traceparent header: version-trace_id-span_id-flags
    # Format: 00-{32 hex trace_id}-{16 hex span_id}-01
    traceparent = f"00-{trace_id}-{span_id}-01"
    
    # Send HTTP request to sub-agent with traceparent header
    headers = {
        "Content-Type": "application/json",
        "traceparent": traceparent,
    }
    body = {"message": "Hello from primary agent", "timestamp": "2026-10-22T14:16:00Z"}
    
    print(f"Sending request to sub-agent with traceparent: {traceparent}")
    try:
        response = requests.post(
            "http://localhost:9999/second?param1=value1",
            json=body,
            headers=headers,
        )
        print(f"Sub-agent response status: {response.status_code}")
        print(f"Sub-agent response body: {response.json()}")
    except Exception as e:
        print(f"Failed to call sub-agent: {e}")
    
    return f"trace_id={trace_id}, span_id={span_id}"


class PrimaryAgentState(TypedDict):
    message: str


def _print_trace_node(state: PrimaryAgentState) -> PrimaryAgentState:
    """Node that invokes the print trace info tool."""
    print_trace_info_tool.invoke({})
    return state


def _build_primary_agent_graph():
    """Build a simple LangGraph with a single node."""
    graph_builder = StateGraph(PrimaryAgentState)
    graph_builder.add_node("print_trace_node", _print_trace_node)
    graph_builder.add_edge(START, "print_trace_node")
    graph_builder.add_edge("print_trace_node", END)
    return graph_builder.compile()


def run_primary_agent(message: str = "") -> dict:
    """Run the primary agent LangGraph."""
    graph = _build_primary_agent_graph()
    result = graph.invoke({"message": message})
    return result


@app.post("/first")
async def first_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = None

    # Run the primary agent LangGraph (prints trace_id and span_id)
    run_primary_agent()
    
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
    uvicorn.run(app, host="0.0.0.0", port=8888)
