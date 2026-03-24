"""
graph/doc_graph.py — Main document generation orchestration graph.

Flow after outline approval:
  [split_sections] → fan-out → [section_agent × N] (parallel)
                             ↓  fan-in via reducer
                   [assemble_document]
                             ↓
                   [build_docx_output]
                             ↓
                            END
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from langgraph.graph import StateGraph, END
from langgraph.types import Send

from graph.state import GraphState
from agents.section_agent import run_section_agent
from agents.assembler_agent import run_assembler_agent
from tools.docx_builder import build_docx
from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


# ── Node: Split outline into parallel section tasks ───────────────────────────

def split_sections_node(state: GraphState) -> Dict[str, Any]:
    """
    Pass-through node that resets aggregators before fan-out.
    The actual fan-out routing is done in route_to_section_agents().
    """
    logger.info("split_sections_node: preparing parallel section execution")
    return {
        "sections_content": [],   # Reset before parallel fill
        "references": [],         # Reset before parallel fill
    }


def route_to_section_agents(state: GraphState) -> List[Send]:
    """
    Fan-out: create one Send per section in the outline.
    Each Send triggers a separate section_agent_node invocation.
    """
    sections = state["outline"].get("sections", [])
    topic = state.get("topic", "")
    logger.info(f"route_to_section_agents: fanning out to {len(sections)} section agents")
    return [
        Send("section_agent_node", {"section": sec, "topic": topic, "state": state})
        for sec in sections
    ]


# ── Node: Section Agent (runs N times in parallel) ────────────────────────────

def section_agent_node(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute one section agent instance.
    Receives: {section: dict, topic: str, state: GraphState}
    Returns updates to sections_content and references accumulators.
    """
    section = inputs["section"]
    topic = inputs["topic"]
    result = run_section_agent(section=section, topic=topic)

    return {
        "sections_content": [result],          # Appended by reducer
        "references": result.get("references", []),  # Appended by reducer
    }


# ── Node: Assemble document ───────────────────────────────────────────────────

def assemble_document_node(state: GraphState) -> Dict[str, Any]:
    """
    Collect all parallel section outputs, resolve IMAGE_PLACEHOLDERs,
    deduplicate and format IEEE references.
    """
    logger.info("assemble_document_node: assembling final document")
    ordered_sections, ieee_refs = run_assembler_agent(
        sections_content=state["sections_content"],
        all_references=state["references"],
    )
    return {
        "final_sections": ordered_sections,
        "ieee_references": ieee_refs,
    }


# ── Node: Build DOCX ──────────────────────────────────────────────────────────

def build_docx_node(state: GraphState) -> Dict[str, Any]:
    """
    Invoke the DOCX builder tool to produce the final .docx file.
    """
    title = state["outline"].get("document_title", state["topic"])
    safe_title = re.sub(r"[^\w\s-]", "", title).replace(" ", "_")
    output_path = str(OUTPUT_DIR / f"{safe_title}.docx")

    logger.info(f"build_docx_node: building '{output_path}'")
    build_docx(
        sections=state["final_sections"],
        references=state["ieee_references"],
        output_path=output_path,
        title=title,
    )
    return {"output_path": output_path}


# ── Build and compile the doc generation graph ────────────────────────────────

def build_doc_graph() -> StateGraph:
    """
    Construct the document generation orchestration graph.
    Returns a compiled graph (no checkpointer needed — single run).
    """
    builder = StateGraph(GraphState)

    builder.add_node("split_sections", split_sections_node)
    builder.add_node("section_agent_node", section_agent_node)
    builder.add_node("assemble_document", assemble_document_node)
    builder.add_node("build_docx_output", build_docx_node)

    builder.set_entry_point("split_sections")

    # Fan-out: split_sections → [section_agent_node × N] via Send()
    builder.add_conditional_edges(
        "split_sections",
        route_to_section_agents,
        ["section_agent_node"],
    )

    # Fan-in: all section_agent_node results → assemble_document
    builder.add_edge("section_agent_node", "assemble_document")
    builder.add_edge("assemble_document", "build_docx_output")
    builder.add_edge("build_docx_output", END)

    return builder.compile()
