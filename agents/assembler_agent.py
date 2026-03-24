"""
agents/assembler_agent.py — Final document assembler node.
Responsibilities:
  1. Sort section outputs by index.
  2. Detect [IMAGE_PLACEHOLDER: ...] tokens in content; route each to
     the Gemini image agent; replace token with [IMAGE_PATH: <path>].
  3. Deduplicate and renumber all references from section agents.
  4. Format references per IEEE journal standard.
  5. Return the final ordered sections list + formatted references list.
"""
from __future__ import annotations
import logging
import re
from typing import Any, Dict, List, Tuple

from agents.image_agent import run_image_agent

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\[IMAGE_PLACEHOLDER:\s*(.+?)\]", re.IGNORECASE)


def run_assembler_agent(
    sections_content: List[Dict[str, Any]],
    all_references: List[Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Assemble all section outputs into a final document structure.

    Args:
        sections_content: List of section dicts from parallel section agents.
                          Each has: index, title, content, images, references.
        all_references: Flat list of all reference dicts collected via reducer.

    Returns:
        Tuple of:
          - ordered_sections: List[Dict] sorted by index, with image placeholders resolved.
          - ieee_references: List[str] of formatted IEEE reference strings.
    """
    # ── Sort sections by index ─────────────────────────────────────────────
    ordered = sorted(sections_content, key=lambda s: s.get("index", 999))
    logger.info(f"assembler: combining {len(ordered)} sections")

    # ── Resolve IMAGE_PLACEHOLDERs via Gemini ─────────────────────────────
    for section in ordered:
        section["content"] = _resolve_placeholders(section["content"])

    # ── Deduplicate and format IEEE references ─────────────────────────────
    ieee_references = _build_ieee_references(all_references)
    logger.info(f"assembler: {len(ieee_references)} unique IEEE references")

    return ordered, ieee_references


def _resolve_placeholders(content: str) -> str:
    """
    Find all [IMAGE_PLACEHOLDER: <prompt>] tokens in content,
    generate each image via Gemini, and replace token with [IMAGE_PATH: <path>].
    If generation fails, remove the placeholder entirely.
    """
    def replace_match(match: re.Match) -> str:
        prompt = match.group(1).strip()
        logger.info(f"assembler: resolving placeholder with prompt: '{prompt[:80]}'")
        path = run_image_agent(prompt)
        if path:
            return f"\n[IMAGE_PATH: {path}]\n"
        else:
            logger.warning(f"assembler: image generation failed, removing placeholder")
            return ""

    return PLACEHOLDER_RE.sub(replace_match, content)


def _build_ieee_references(raw_refs: List[Dict[str, str]]) -> List[str]:
    """
    Deduplicate references by URL or title, then format each as an IEEE citation.

    IEEE journal format:
    [N] A. Author and B. Author, "Title," Journal/Publication, vol. X, pp. Y–Z, Year.
         [Online]. Available: URL

    For web sources without full journal info:
    [N] Author(s), "Title," Available: URL, Year.
    """
    seen = set()
    unique_refs: List[Dict[str, str]] = []

    for ref in raw_refs:
        dedup_key = ref.get("url") or ref.get("title", "")
        dedup_key = dedup_key.strip().lower()
        if dedup_key and dedup_key not in seen:
            seen.add(dedup_key)
            unique_refs.append(ref)

    formatted: List[str] = []
    for i, ref in enumerate(unique_refs, start=1):
        formatted.append(_format_ieee(i, ref))

    return formatted


def _format_ieee(number: int, ref: Dict[str, str]) -> str:
    """Format a single reference dict as an IEEE citation string."""
    authors = ref.get("authors", "").strip()
    title = ref.get("title", "Untitled").strip()
    publication = ref.get("publication", "").strip()
    volume = ref.get("volume", "").strip()
    pages = ref.get("pages", "").strip()
    year = ref.get("year", "").strip()
    url = ref.get("url", "").strip()

    # Build author part
    author_part = f"{authors}, " if authors else ""

    # Build title part
    title_part = f'"{title},"' if title else ""

    # Build publication details
    pub_parts = []
    if publication and publication.lower() not in ("web", ""):
        pub_parts.append(publication)
    if volume:
        pub_parts.append(f"vol. {volume}")
    if pages:
        pub_parts.append(f"pp. {pages}")
    if year:
        pub_parts.append(year)

    pub_str = (", ".join(pub_parts) + "." if pub_parts else "")

    # Build online/URL part
    url_part = f" [Online]. Available: {url}" if url else ""

    citation = f"[{number}] {author_part}{title_part} {pub_str}{url_part}".strip()
    return citation
