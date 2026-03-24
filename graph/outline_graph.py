"""
graph/outline_graph.py — Outline generation + Human-in-the-Loop graph.

Flow:
  [generate_outline] → [human_review] ←→ (loop back to generate_outline on feedback)
                                      → (approved=True → END)

Uses LangGraph interrupt() for terminal-based human-in-the-loop approval.
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from graph.state import GraphState
from agents.outline_agent import run_outline_agent

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10  # Safety cap on refinement loop


# ── Node: Generate / Refine Outline ──────────────────────────────────────────

def generate_outline_node(state: GraphState) -> Dict[str, Any]:
    """Call the outline agent. If user_feedback exists, include it in the prompt."""
    feedback = state.get("user_feedback", "")
    description = state.get("description", "")

    # Append user feedback to description for refinement iterations
    effective_description = description
    if feedback and feedback.strip().lower() not in ("ok", "yes", "confirm", "approve", "done"):
        effective_description = f"{description}\n\nUser refinement request: {feedback}"

    outline = run_outline_agent(
        topic=state["topic"],
        description=effective_description,
        total_pages=state["total_pages"],
    )
    iteration = state.get("iteration", 0) + 1
    logger.info(f"generate_outline_node: iteration {iteration}")
    return {
        "outline": outline,
        "iteration": iteration,
        "approved": False,
    }


# ── Node: Human Review (HITL via interrupt) ───────────────────────────────────

def human_review_node(state: GraphState) -> Command:
    """
    Pause execution and present the outline to the user in the terminal.
    Uses LangGraph interrupt() — resumes when Command(resume=...) is issued.
    """
    outline = state.get("outline", {})
    iteration = state.get("iteration", 1)

    # Format outline for display
    display = _format_outline_for_display(outline, iteration)

    # interrupt() pauses the graph and surfaces the value to the caller
    user_input: str = interrupt({"display": display})

    user_input = user_input.strip()
    approved = user_input.lower() in ("ok", "yes", "confirm", "approve", "done", "")
    logger.info(f"human_review_node: user_input='{user_input}', approved={approved}")

    return Command(
        update={
            "user_feedback": user_input,
            "approved": approved,
        }
    )


# ── Routing: Loop or proceed ───────────────────────────────────────────────────

def route_after_review(state: GraphState) -> str:
    """Route: if approved → END, else loop back to generate_outline."""
    if state.get("approved", False):
        return "approved"
    if state.get("iteration", 0) >= MAX_ITERATIONS:
        logger.warning("Max refinement iterations reached; proceeding anyway.")
        return "approved"
    return "refine"


# ── Build outline sub-graph ───────────────────────────────────────────────────

def build_outline_graph() -> StateGraph:
    """
    Construct the outline + HITL LangGraph subgraph.
    Returns a compiled graph with MemorySaver checkpointer.
    """
    builder = StateGraph(GraphState)

    builder.add_node("generate_outline", generate_outline_node)
    builder.add_node("human_review", human_review_node)

    builder.set_entry_point("generate_outline")
    builder.add_edge("generate_outline", "human_review")
    builder.add_conditional_edges(
        "human_review",
        route_after_review,
        {"approved": END, "refine": "generate_outline"},
    )

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer, interrupt_before=["human_review"])


# ── Helper: Pretty-print outline ──────────────────────────────────────────────

def _format_outline_for_display(outline: Dict[str, Any], iteration: int) -> str:
    """Format the outline dict as readable terminal output."""
    lines = [
        "=" * 70,
        f"  DOCUMENT OUTLINE (Iteration {iteration})",
        "=" * 70,
        f"  Title : {outline.get('document_title', 'N/A')}",
        f"  Topic : {outline.get('topic', 'N/A')}",
        f"  Pages : {outline.get('total_pages', 'N/A')}",
        "",
        f"  Summary:",
        f"  {outline.get('summary', '')}",
        "",
        "  Sections:",
        "-" * 70,
    ]
    for sec in outline.get("sections", []):
        lines.append(f"  [{sec.get('index', '?')}] {sec.get('title', 'Untitled')}  "
                     f"(~{sec.get('estimated_pages', 1.5)} pages)")
        for kp in sec.get("key_points", []):
            lines.append(f"       • {kp}")
        if sec.get("needs_image") and sec.get("image_hint"):
            lines.append(f"       📷 Image: {sec.get('image_hint', '')}")
        lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)
