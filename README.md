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
    │   └── metrics_utils/      # Importable Python package
    │       └── ...
    └── tracer_utils/           # Installable package: tracer-utils
        ├── pyproject.toml
        ├── README.md
        └── tracer_utils/       # Importable Python package
            └── ...
```

## Adding a new package

1. Create `packages/<your_package>/` with a `pyproject.toml` and `<your_package>/` subdirectory
2. The workspace root `pyproject.toml` picks it up automatically via `members = ["packages/*"]`
3. Run `uv sync` to refresh the lockfile
