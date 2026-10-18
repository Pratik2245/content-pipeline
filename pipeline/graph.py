"""LangGraph workflow with two feedback loops (the part worth studying).

             ┌────────────── feedback loop 1 (editor) ─────────────┐
             ▼                                                     │
START ──► research ──► write ──► editor ──► approved? ──no──► revise
                                          │ yes                    │
                                          ▼                        │
             ┌────────── feedback loop 2 (fact-check) ──► revise ◄──┘
             ▼
          factcheck ──► claims supported? ──no──► (back to writer)
                                          │ yes
                                          ▼
                                       finalize ──► END
"""

import operator
from typing import Annotated, Literal
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END

from .schemas import Research, PipelineResult
from . import agents


class State(TypedDict, total=False):
    topic: str
    research: Research
    posts: list[dict]           # working drafts + status/feedback per post
    final: PipelineResult
    # Every node appends human-readable progress lines; LangGraph merges them.
    run_log: Annotated[list[str], operator.add]


# --- Wiring ---------------------------------------------------------------

graph = StateGraph(State)

graph.add_node("research", agents.research_node)
graph.add_node("write", agents.write_node)
graph.add_node("editor", agents.editor_node)
graph.add_node("factcheck", agents.factcheck_node)
graph.add_node("revise", agents.revise_node)
graph.add_node("finalize", agents.finalize_node)

graph.add_edge(START, "research")
graph.add_edge("research", "write")
graph.add_edge("write", "editor")

# Feedback loop #1: editor rejections go back to the writer.
graph.add_conditional_edges(
    "editor", agents.route_after_editor,
    {"revise": "revise", "factcheck": "factcheck"},
)
graph.add_edge("revise", "editor")

# Feedback loop #2: fact-checker rejections go back to the writer too.
graph.add_conditional_edges(
    "factcheck", agents.route_after_factcheck,
    {"revise": "revise", "finalize": "finalize"},
)
graph.add_edge("finalize", END)

app = graph.compile()
