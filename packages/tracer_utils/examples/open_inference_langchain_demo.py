"""
Minimal LangChain + Ollama demo: OpenInference auto-instrumentation -> OTLP -> MLflow.

Demonstrates the ``tracer_utils.Tracer`` facade with automatic LangChain/LangGraph
instrumentation and manual span creation.

Hierarchy (one trace when ``main_agent`` is invoked):
  main_agent -> using_langchain | using_langraph -> LLM / tool / graph nodes

Prerequisites:
  1. Ollama running with gemma3:270m pulled
  2. MLflow: docker compose -f packages/tracer_utils/docker/docker-compose.yml up -d
     UI at http://localhost:5000
  3. (Optional) Langfuse: set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL
  4. A .env file in the project root (or env vars exported in your shell)
  5. This package installed: uv sync  (from the repo root)

Run from the repo root:
  uv run python packages/tracer_utils/examples/open_inference_langchain_demo.py
"""

from __future__ import annotations

import asyncio
import random
import re
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from tracer_utils import Tracer, TracerDestination, TracerSdk

## configuration for mlflow as backend
tracer = Tracer(
    sdk=TracerSdk.OPEN_INFERENCE,
    destinations=TracerDestination.MLFLOW,
    service_name="traces-open-inference",
)

# When using langfuse, make sure to include below env in .env file
# LANGFUSE_SECRET_KEY=
# LANGFUSE_PUBLIC_KEY=
# LANGFUSE_BASE_URL=, e.g: http://localhost:3000
# # configuration for mlflow + langfuse
# tracer = Tracer(
#     sdk=TracerSdk.OPEN_INFERENCE,
#     destinations=[TracerDestination.MLFLOW, TracerDestination.LANGFUSE],
#     service_name="traces-open-inference",
# )

## configuration for langfuse only
# tracer = Tracer(
#     sdk=TracerSdk.OPEN_INFERENCE,
#     destinations=[TracerDestination.LANGFUSE],
#     service_name="traces-open-inference",
# )

tracer.instrument_frameworks()

from langchain_core.runnables import RunnableConfig, chain
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

llm = ChatOllama(
    model="gemma3:270m",
    base_url="http://localhost:11434",
    stream_usage=True,
)

_DEFAULT_QUERY = "What is 2 + 2? Reply with just the number."


def _log_function_span(function_name: str) -> None:
    print(f"================ {function_name}")
    tracer.print_trace_ids()


@tool
def multiply_two_ints(a: int, b: int) -> int:
    """Multiply two integers and return the product."""
    _log_function_span("multiply_two_ints")
    result = a * b
    print(f"Tool multiply({a}, {b}) -> {result}")
    return result


@chain
def agent_function(query: str) -> str:
    """LLM turn then a tool call (used inside the LangChain sub-agent)."""
    _log_function_span("agent_function")
    print(f"Request: {query}")
    response = llm.invoke(query)
    answer = str(response.content)
    print(f"Response: {answer}")
    multiply_two_ints.invoke({"a": 6, "b": 7})
    return answer


@chain
def using_langchain(_: str) -> str:
    """Sub-agent: single @chain runnable with one LLM + tool step."""
    _log_function_span("using_langchain")
    return agent_function.invoke(_DEFAULT_QUERY)


class LangGraphState(TypedDict):
    query: str


def _llm_then_multiply(prompt: str, a: int, b: int, label: str) -> None:
    current = tracer.get_current_span()
    if current is not None:
        current.set_attribute("custom.label", label)
    print(f"Request ({label}): {prompt}")
    response = llm.invoke(prompt)
    print(f"Response ({label}): {response.content}")
    multiply_two_ints.invoke({"a": a, "b": b})


def _build_langraph_graph():
    def step1(state: LangGraphState, config: RunnableConfig) -> LangGraphState:
        _log_function_span("step1")
        _llm_then_multiply(f"{state['query']} (graph step 1)", 2, 3, "step1")
        with tracer.start_span("step1-manual-span"):
            print("step1: a new span was created (tracer.start_span context manager)")
            _log_function_span("xxx - create new span using tracer.start_span")
        return state

    def step2(state: LangGraphState, config: RunnableConfig) -> LangGraphState:
        _log_function_span("step2")
        _llm_then_multiply(f"{state['query']} (graph step 2)", 4, 5, "step2")
        return state

    def step3(state: LangGraphState, config: RunnableConfig) -> LangGraphState:
        _log_function_span("step3")
        _llm_then_multiply(f"{state['query']} (graph step 3)", 6, 7, "step3")
        return state

    graph_builder = StateGraph(LangGraphState)
    graph_builder.add_node("step1", step1)
    graph_builder.add_node("step2", step2)
    graph_builder.add_node("step3", step3)
    graph_builder.add_edge(START, "step1")
    graph_builder.add_edge("step1", "step2")
    graph_builder.add_edge("step2", "step3")
    graph_builder.add_edge("step3", END)
    return graph_builder.compile()


@chain
def using_langraph(_: str) -> str:
    """Sub-agent: LangGraph with three LLM + tool steps."""
    _log_function_span("using_langraph")
    graph = _build_langraph_graph()
    graph.invoke({"query": _DEFAULT_QUERY})
    return "langraph-done"


@tool
async def async_tool_1(message: str) -> str:
    """Run ten iterations with random delays (tool 1)."""
    _log_function_span("async_tool_1")
    for counter in range(1, 11):
        print(f"async_tool_1 counter={counter} time={datetime.now():%H:%M:%S}")
        await asyncio.sleep(random.uniform(1, 5))
    return f"original string {message}"


@tool
async def async_tool_2(message: str) -> str:
    """Run ten iterations with random delays (tool 2)."""
    _log_function_span("async_tool_2")
    for counter in range(1, 11):
        print(f"async_tool_2 counter={counter} time={datetime.now():%H:%M:%S}")
        await asyncio.sleep(random.uniform(1, 5))
    return f"original string {message}"


@tool
async def async_tool_3(message: str) -> str:
    """Run ten iterations with random delays (tool 3)."""
    _log_function_span("async_tool_3")
    for counter in range(1, 11):
        print(f"async_tool_3 counter={counter} time={datetime.now():%H:%M:%S}")
        await asyncio.sleep(random.uniform(1, 5))
    return f"original string {message}"


async def _invoke_three_async_tools() -> None:
    print("waiting for async_tool_1, async_tool_2, and async_tool_3 to complete...")
    await asyncio.gather(
        async_tool_1.ainvoke({"message": "calling async_tool_1"}),
        async_tool_2.ainvoke({"message": "calling async_tool_2"}),
        async_tool_3.ainvoke({"message": "calling async_tool_3"}),
    )
    print("all tools finished")


@chain
def using_langchain2_invoke_tool_async(_: str) -> str:
    """Sub-agent: langchain with 3 async tools invocation."""
    _log_function_span("using_langchain2_invoke_tool_async")
    asyncio.run(_invoke_three_async_tools())
    return "using_langchain2_invoke_tool_async-done"


@chain
def react_observe(query: str) -> str:
    """ReAct step 1: observe the task and environment."""
    _log_function_span("react_observe")
    prompt = (
        "OBSERVE step: In one short sentence, state what you observe about this task.\n"
        f"Task: {query}"
    )
    print(f"Request (observe): {prompt}")
    response = llm.invoke(prompt)
    observation = str(response.content)
    print(f"Observation: {observation}")
    return observation


@chain
def react_reflect(observation: str) -> str:
    """ReAct step 2: reflect on the observation."""
    _log_function_span("react_reflect")
    prompt = (
        "REFLECT step: In one short sentence, reflect on what the observation implies.\n"
        f"Observation: {observation}"
    )
    print(f"Request (reflect): {prompt}")
    response = llm.invoke(prompt)
    reflection = str(response.content)
    print(f"Reflection: {reflection}")
    return reflection


@chain
def react_action(reflection: str) -> str:
    """ReAct step 3: choose and execute an action."""
    _log_function_span("react_action")
    prompt = (
        "ACTION step: In one short sentence, name one concrete action to take next.\n"
        f"Reflection: {reflection}"
    )
    print(f"Request (action): {prompt}")
    response = llm.invoke(prompt)
    planned_action = str(response.content)
    print(f"Planned action: {planned_action}")
    multiply_two_ints.invoke({"a": 3, "b": 4})
    return planned_action


@chain
def using_langchain3_react_patterm(_: str) -> str:
    """Sub-agent: ReAct loop -- observe, reflect, then action."""
    _log_function_span("using_langchain3_react_patterm")
    observation = react_observe.invoke(_DEFAULT_QUERY)
    reflection = react_reflect.invoke(observation)
    react_action.invoke(reflection)
    return "using_langchain3_react_patterm-done"


@tool
def check_number_below_five(n: int) -> str:
    """Return 'below' if n is strictly less than 5, otherwise 'not_below'."""
    _log_function_span("check_number_below_five")
    verdict = "below" if n < 5 else "not_below"
    print(f"check_number_below_five({n}) -> {verdict}")
    return verdict


def _parse_llm_integer(text: str) -> int:
    match = re.search(r"\d+", text.strip())
    if not match:
        raise ValueError(f"LLM did not return a number: {text!r}")
    return int(match.group())


@chain
def react4_observe(context: str) -> str:
    """ReAct observe: current goal for collecting numbers below 5."""
    _log_function_span("react4_observe")
    prompt = (
        "OBSERVE step: Briefly state what you observe about the current goal.\n"
        f"Context: {context}"
    )
    print(f"Request (observe): {prompt}")
    response = llm.invoke(prompt)
    observation = str(response.content)
    print(f"Observation: {observation}")
    return observation


@chain
def react4_reflect(observation: str) -> str:
    """ReAct reflect: implications for picking a number below 5."""
    _log_function_span("react4_reflect")
    prompt = (
        "REFLECT step: Briefly reflect on how to get an integer below 5.\n"
        f"Observation: {observation}"
    )
    print(f"Request (reflect): {prompt}")
    response = llm.invoke(prompt)
    reflection = str(response.content)
    print(f"Reflection: {reflection}")
    return reflection


@chain
def react4_action(reflection: str) -> str:
    """ReAct action: state the next step before generating a number."""
    _log_function_span("react4_action")
    prompt = (
        "ACTION step: In one short sentence, say you will ask the model for "
        "an integer from 1 to 10.\n"
        f"Reflection: {reflection}"
    )
    print(f"Request (action): {prompt}")
    response = llm.invoke(prompt)
    planned_action = str(response.content)
    print(f"Planned action: {planned_action}")
    return planned_action


@chain
def generate_number_one_to_ten(_: str) -> str:
    """Ask the LLM for a single integer in 1..10 (digits only in the reply)."""
    _log_function_span("generate_number_one_to_ten")
    prompt = (
        "Pick a random integer from 1 to 10 inclusive. "
        "Reply with ONLY that integer, no other words."
    )
    print(f"Request (generate number): {prompt}")
    response = llm.invoke(prompt)
    raw = str(response.content).strip()
    print(f"Generated number (raw): {raw}")
    return raw


@chain
def using_langchain4_react_patterm(_: str) -> str:
    """ReAct loop until three LLM numbers below 5 are collected."""
    _log_function_span("using_langchain4_react_patterm")
    numbers_below_five: list[int] = []

    for slot in range(1, 4):
        while True:
            context = (
                f"Collecting number {slot} of 3 that must be below 5. "
                f"Already accepted: {numbers_below_five}."
            )
            observation = react4_observe.invoke(context)
            reflection = react4_reflect.invoke(observation)
            react4_action.invoke(reflection)

            raw_number = generate_number_one_to_ten.invoke("")
            candidate = _parse_llm_integer(raw_number)
            verdict = check_number_below_five.invoke({"n": candidate})

            if verdict == "below":
                numbers_below_five.append(candidate)
                print(f"Accepted {candidate} as number {slot} of 3 (below 5).")
                break

            print(f"Rejected {candidate} (not below 5), retrying slot {slot}...")

    print(f"Three numbers below 5: {numbers_below_five}")
    return "using_langchain4_react_patterm-done"


@chain
def using_langchain5_new_span(input_str: str, config: RunnableConfig) -> str:
    """Sub-agent: open a manual span and invoke check_number_below_five inside it."""
    check_number_below_five.invoke({"n": 3})
    _log_function_span("using_langchain5_new_span")
    with tracer.start_span(
        "new_span_using_langchain5-check-number",
        langchain_config=config,
    ) as root:
        _log_function_span("using_langchain5_new_span-inside-span")

        # Attach extra information to this span: arbitrary custom attributes plus
        # OpenInference's input/output semantic attributes. Both show up in MLflow
        # and Langfuse, since both read from the same underlying span.
        root.set_attribute("custom.slot", "using_langchain5_new_span")
        root.set_attributes({"custom.n": 3, "custom.source": "manual-span-demo"})
        root.set_input({"n": 3})

        verdict = check_number_below_five.invoke(
            {"n": 3},
            config=root.langchain_invoke_config,
        )
        print(f"check_number_below_five(3) -> {verdict}")
        root.set_output(verdict)

    # Tool call outside the above span, for comparison in the trace view.
    verdict = check_number_below_five.invoke({"n": 3})
    print(f"check_number_below_five(3) -> {verdict}")
    return "using_langchain5_new_span-done"


@chain
def using_langchain6_set_attributes(_: str, config: RunnableConfig) -> str:
    """Sub-agent: focused test of every set-attributes API on SpanHandle.

    Tests (in order):
    1. ``tracer.get_current_span()`` – set a single attribute on the
       auto-instrumented (framework-managed) outer span.
    2. ``tracer.start_span()`` context manager:
       a. ``root.set_attribute()``   – one key/value pair.
       b. ``root.set_attributes()``  – several key/value pairs in a dict.
       c. ``root.set_input()``       – OpenInference input semantic attribute.
       d. ``root.set_output()``      – OpenInference output semantic attribute.
    """
    _log_function_span("using_langchain6_set_attributes")

    # ── 1. Annotate the current (outer, framework-managed) span ──────────────
    current = tracer.get_current_span()
    if current is not None:
        current.set_attribute("custom.test_step", "outer_span_annotation")
        print("using_langchain6_set_attributes: set attribute on outer (current) span")
    else:
        print("using_langchain6_set_attributes: no outer span found (running standalone?)")

    # ── 2. Open a manual child span and exercise all attribute helpers ────────
    with tracer.start_span(
        "set_attributes_test_span",
        langchain_config=config,
    ) as root:
        _log_function_span("using_langchain6_set_attributes-inside-span")

        # 2a. Single attribute
        root.set_attribute("custom.test", "set_attribute_single")
        print("using_langchain6_set_attributes: set_attribute -> custom.test")

        # 2b. Multiple attributes at once
        root.set_attributes(
            {
                "custom.source": "using_langchain6_set_attributes",
                "custom.version": 6,
                "custom.flag": True,
            }
        )
        print("using_langchain6_set_attributes: set_attributes -> custom.source / version / flag")

        # 2c. OpenInference input semantic attribute
        root.set_input({"query": "set-attributes test", "n": 42})
        print("using_langchain6_set_attributes: set_input -> {'query': ..., 'n': 42}")

        # 2d. Run a real tool call so the span contains meaningful child activity
        verdict = check_number_below_five.invoke(
            {"n": 3},
            config=root.langchain_invoke_config,
        )
        print(f"using_langchain6_set_attributes: check_number_below_five(3) -> {verdict}")

        # 2e. OpenInference output semantic attribute (set after we have a result)
        root.set_output({"verdict": verdict, "accepted": verdict == "below"})
        print("using_langchain6_set_attributes: set_output -> verdict result")

    return "using_langchain6_set_attributes-done"


@chain
def main_agent(_: str, config: RunnableConfig) -> str:
    """Top-level agent: runs both sub-agents under one Runnable trace."""
    # using_langchain.invoke("")
    # using_langraph.invoke("")
    # using_langchain2_invoke_tool_async.invoke("")
    # using_langchain3_react_patterm.invoke("")
    # using_langchain4_react_patterm.invoke("")

    # Below function is also testing attributes (within new span and
    # within existing span etc.)
    # using_langchain5_new_span.invoke("")

    # Tests all set-attribute helpers: set_attribute, set_attributes,
    # set_input, set_output (on a manual span) plus get_current_span (outer span).
    using_langchain6_set_attributes.invoke("")

    return "main-agent-done"


def main() -> None:
    try:
        main_agent.invoke("")
    finally:
        tracer.shutdown()
        print("Flushed OpenInference spans to MLflow")


if __name__ == "__main__":
    main()
