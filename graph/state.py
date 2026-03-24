"""
graph/state.py — LangGraph shared state definition.
Uses TypedDict with Annotated reducers for parallel branch aggregation.
"""
from __future__ import annotations
import operator
from typing import Any, Annotated, Dict, List, Optional, TypedDict


class GraphState(TypedDict):
    """
    Shared state flowing through the entire documentation generation graph.

    Fields populated during Outline phase:
        topic           : The documentation topic entered by the user.
        description     : Optional user description / focus areas.
        total_pages     : Requested total page count.
        outline         : Full outline dict returned by outline_agent.
        user_feedback   : Last feedback string entered by the user.
        approved        : Whether the user has confirmed the outline.
        iteration       : Number of outline refinement iterations so far.

    Fields populated during Document Generation phase:
        sections_content: Aggregated list of section dicts (uses reducer to
                          collect from parallel section agents).
        references      : Aggregated list of reference dicts (uses reducer).

    Fields populated during Assembly / Output phase:
        final_sections  : Ordered, image-resolved sections list.
        ieee_references : Formatted IEEE reference strings.
        output_path     : Path to the generated .docx file.
    """
    # ── Input ─────────────────────────────────────────────────────────────────
    topic: str
    description: str
    total_pages: int

    # ── Outline phase ─────────────────────────────────────────────────────────
    outline: Dict[str, Any]
    user_feedback: str
    approved: bool
    iteration: int

    # ── Parallel section collection (reducers accumulate from fan-out) ────────
    sections_content: Annotated[List[Dict[str, Any]], operator.add]
    references: Annotated[List[Dict[str, str]], operator.add]

    # ── Assembly / Output ─────────────────────────────────────────────────────
    final_sections: List[Dict[str, Any]]
    ieee_references: List[str]
    output_path: Optional[str]
