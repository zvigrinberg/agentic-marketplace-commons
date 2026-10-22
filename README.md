# agentic-marketplace-commons

A monorepo of shared Python utility packages for the agentic marketplace platform.

## Packages

| Package | Description | Install |
|---|---|---|
| [`metrics_utils`](packages/metrics_utils) | Declarative metric abstraction over OpenTelemetry | See below |
| [`tracer_utils`](packages/tracer_utils) | Class-based tracing abstraction over OpenInference / MLflow / Langfuse | See below |

## Installing packages in a consumer project

### From GitHub (recommended for internal use)

Add to your project's `pyproject.toml` or `requirements.txt`:

```toml
# pyproject.toml
[project]
dependencies = [
    "metrics-utils @ git+https://github.com/your-org/agentic-marketplace-commons.git#subdirectory=packages/metrics_utils",
    "tracer-utils  @ git+https://github.com/your-org/agentic-marketplace-commons.git#subdirectory=packages/tracer_utils",
]
```

Or in `requirements.txt`:

```
metrics-utils @ git+https://github.com/your-org/agentic-marketplace-commons.git#subdirectory=packages/metrics_utils
tracer-utils  @ git+https://github.com/your-org/agentic-marketplace-commons.git#subdirectory=packages/tracer_utils
```

### Local editable install (for development)

> **Note:** If you're working inside this repo, `uv sync` (see Development setup below) already installs all packages in editable mode — no manual install needed.
>
> If you need to install a single package into an external environment:

```bash
uv pip install -e ./packages/metrics_utils
uv pip install -e ./packages/tracer_utils
```

## Development setup

This repo uses [uv](https://docs.astral.sh/uv/) workspaces. To set up the full dev environment:

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all packages in editable mode into a shared venv
uv sync
```

This creates a single `.venv` at the repo root with all packages installed.

## Repository layout

```
agentic-marketplace-commons/
├── pyproject.toml              # Workspace root (not published)
├── uv.lock                     # Single lockfile for the whole monorepo
├── .venv/                      # Single shared virtual environment
└── packages/
    ├── metrics_utils/          # Installable package: metrics-utils
    │   ├── pyproject.toml
    │   ├── README.md
    │   ├── metrics_utils/      # Importable Python package
    │   │   └── ...
    │   └── examples/           # Runnable demos + Docker Compose stack
    │       ├── sample_client.py
    │       ├── Dockerfile
    │       ├── docker-compose.yml
    │       └── prometheus.yml
    └── tracer_utils/           # Installable package: tracer-utils
        ├── pyproject.toml
        ├── README.md
        ├── tracer_utils/       # Importable Python package
        │   └── ...
        ├── examples/           # Runnable demos
        │   ├── open_inference_langchain_demo.py  # LangChain/LangGraph + Ollama, manual spans
        │   ├── primary_agent.py                  # FastAPI primary agent (port 8888)
        │   └── sub_agent.py                      # FastAPI sub-agent (port 9999); W3C traceparent — spans on same MLflow trace as primary, nested under its parent trace/span IDs
        ├── docker/             # Docker Compose stack for tracing backends
        │   └── docker-compose.yml
        └── tests/
            └── ...
```

## tracer_utils examples

Package-level API and setup are documented in [`packages/tracer_utils/README.md`](packages/tracer_utils/README.md).

| Example | What it demonstrates |
|---|---|
| [`open_inference_langchain_demo.py`](packages/tracer_utils/examples/open_inference_langchain_demo.py) | OpenInference auto-instrumentation, LLM/tool/LangGraph flows, manual spans, MLflow (optional Langfuse). Requires Ollama + MLflow (see that file’s docstring). |
| [`primary_agent.py`](packages/tracer_utils/examples/primary_agent.py) + [`sub_agent.py`](packages/tracer_utils/examples/sub_agent.py) | Two FastAPI services: the primary agent runs a LangGraph tool that calls the sub-agent over HTTP with a W3C `traceparent` header so spans from the sub-agent attach to the same trace in MLflow. |

**Distributed tracing demo (primary + sub-agent)**

Prerequisites: `uv sync`, MLflow up (`docker compose -f packages/tracer_utils/docker/docker-compose.yml up -d`), and a root `.env` if you use Langfuse or custom MLflow settings.

```bash
# Terminal 1 — sub-agent on :9999
uv run python packages/tracer_utils/examples/sub_agent.py

# Terminal 2 — primary agent on :8888
uv run python packages/tracer_utils/examples/primary_agent.py

# Terminal 3 — trigger the flow (primary calls sub-agent from inside its LangGraph tool)
curl -X POST http://localhost:8888/first -H "Content-Type: application/json" -d '{"hello":"world"}'
```

Check traces in the MLflow UI (`http://localhost:5000` by default).

## Adding a new package

1. Create `packages/<your_package>/` with a `pyproject.toml` and `<your_package>/` subdirectory
2. The workspace root `pyproject.toml` picks it up automatically via `members = ["packages/*"]`
3. Run `uv sync` to refresh the lockfile
