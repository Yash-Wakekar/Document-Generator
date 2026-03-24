"""
agents/outline_agent.py — Outline planner agent.
Uses GPT-4o to generate a structured documentation outline from:
  - topic (str)
  - description (str, optional)
  - total_pages (int)
Returns a structured dict with sections and metadata.
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import OPENAI_API_KEY, OPENAI_MODEL, WORDS_PER_PAGE, MIN_WORDS_PER_SECTION

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert technical documentation planner.
Your job is to create a detailed documentation outline given a topic, optional description, and target page count.

You MUST respond with valid JSON only — no markdown fences, no explanation.

The JSON must follow this exact schema:
{
  "document_title": "Full title of the document",
  "topic": "The topic as provided",
  "total_pages": <integer>,
  "sections": [
    {
      "index": 1,
      "title": "Section Title",
      "key_points": ["point 1", "point 2", "point 3"],
      "estimated_pages": 1.5,
      "needs_image": true,
      "image_hint": "Brief description of what kind of image would suit this section"
    }
  ],
  "summary": "One paragraph overview of what this document will cover."
}

Rules:
- Each section should produce approximately 1.5 pages (750+ words).
- Total number of sections = ceil(total_pages / 1.5).
- Keep sections cohesive — each must cover a single well-defined subtopic.
- Set needs_image=true for sections where a diagram, chart, or illustration would add value.
- image_hint should be a rich, descriptive prompt suitable for AI image generation.
- key_points should have 3-5 items per section guiding the writing.
"""


def run_outline_agent(
    topic: str,
    description: str,
    total_pages: int,
) -> Dict[str, Any]:
    """
    Generate a documentation outline.

    Args:
        topic: The documentation topic.
        description: Optional user-provided description or focus areas.
        total_pages: Target number of pages for the final document.

    Returns:
        Parsed outline dict conforming to the schema above.
    """
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        temperature=0.3,
    )

    user_content = f"""Topic: {topic}
Description: {description if description else 'Not provided — use your judgment.'}
Target pages: {total_pages}
Approximate words per page: {WORDS_PER_PAGE}
Minimum words per section: {MIN_WORDS_PER_SECTION}

Generate the outline now."""

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    logger.info(f"outline_agent: generating outline for topic='{topic}', pages={total_pages}")
    response = llm.invoke(messages)
    raw = response.content.strip()

    # Strip markdown fences if model added them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        outline = json.loads(raw)
        logger.info(f"outline_agent: generated {len(outline.get('sections', []))} sections")
        return outline
    except json.JSONDecodeError as e:
        try:
            raw_content = response.content.strip()
            first_brace = raw_content.find("{")
            last_brace = raw_content.rfind("}")
            if first_brace != -1 and last_brace != -1:
                outline = json.loads(raw_content[first_brace:last_brace+1])
                logger.info(f"outline_agent: generated {len(outline.get('sections', []))} sections")
                return outline  
            else:
                logger.error(f"outline_agent: failed to parse JSON: {e}\nRaw: {raw[:500]}")
                raise ValueError(f"Outline agent returned invalid JSON: {e}") from e
        except Exception as e:
            logger.error(f"outline_agent: failed to parse JSON: {e}\nRaw: {raw[:500]}")
            raise ValueError(f"Outline agent returned invalid JSON: {e}") from e
