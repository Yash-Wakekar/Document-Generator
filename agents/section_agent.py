"""
agents/section_agent.py — Per-section content writer agent.
For each outline section:
  1. Searches DuckDuckGo for relevant content.
  2. Scrapes the top result page for text.
  3. Attempts to fetch an image from the same page.
  4. If no image found, inserts [IMAGE_PLACEHOLDER: <prompt>].
  5. Writes ≥1.5 pages of structured prose using GPT-4o.
  6. Collects structured IEEE-ready references.
Returns a section dict with title, content, images, and references.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import OPENAI_API_KEY, OPENAI_MODEL, MIN_WORDS_PER_SECTION, MAX_SEARCH_RESULTS
from tools.web_search import web_search, scrape_page_text
from tools.image_fetch import fetch_image_from_page

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert technical writer producing documentation content.
You will receive:
- A section title and key points to cover
- Reference context scraped from web sources

Your task:
1. Write a comprehensive, well-structured section of documentation.
2. Minimum {min_words} words (approximately 1.5 pages).
3. Use clear paragraph breaks. Do NOT use markdown headers inside the content.
4. Where an image would add value (diagrams, charts, processes), insert EXACTLY this token:
   [IMAGE_PLACEHOLDER: <a rich, detailed prompt describing the ideal image>]
   Place this token on its own line between paragraphs.
5. At the very end of your response, outside the main text, add a JSON block:
   REFERENCES_JSON_START (including the start and end tags)
   [
     {{"authors": "...", "title": "...", "publication": "...", "year": "...", "url": "..."}}
   ]
   REFERENCES_JSON_END (including the start and end tags)
   Include one entry per source you used.

IMPORTANT: Write only the section body text. No titles or headings. Be thorough and informative.
"""


def run_section_agent(
    section: Dict[str, Any],
    topic: str,
) -> Dict[str, Any]:
    """
    Generate content for one documentation section.

    Args:
        section: Outline section dict with keys: index, title, key_points,
                 needs_image, image_hint.
        topic: The parent document topic (used to frame web searches).

    Returns:
        Dict with keys: index, title, content, images (list of paths), references (list of dicts)
    """
    section_title = section.get("title", "Untitled Section")
    key_points = section.get("key_points", [])
    needs_image = section.get("needs_image", False)
    image_hint = section.get("image_hint", "")
    index = section.get("index", 0)

    logger.info(f"section_agent [{index}]: starting '{section_title}'")

    # ── Step 1: Web search ────────────────────────────────────────────────────
    query = f"{topic} {section_title}"
    search_results = web_search(query, max_results=MAX_SEARCH_RESULTS)

    # ── Step 2: Scrape top result for context text ────────────────────────────
    scraped_context = ""
    top_url = ""
    top_title = ""
    if search_results:
        top_result = search_results[0]
        top_url = top_result.get("url", "")
        top_title = top_result.get("title", "")
        if top_url:
            scraped_context = scrape_page_text(top_url)
            logger.info(f"section_agent [{index}]: scraped {len(scraped_context)} chars from '{top_url}'")

    # ── Step 3: Try to fetch image from the same page ─────────────────────────
    fetched_images: List[str] = []
    if needs_image and top_url:
        img_path = fetch_image_from_page(top_url)
        if img_path:
            fetched_images.append(img_path)
            logger.info(f"section_agent [{index}]: fetched image from web → '{img_path}'")

    # Build search snippets from all results for context
    snippets = "\n\n".join(
        f"[Source {i+1}] {r.get('title','')}\nURL: {r.get('url','')}\n{r.get('body','')}"
        for i, r in enumerate(search_results[:3])
    )

    # ── Step 4: Generate content with GPT-4o ──────────────────────────────────
    system_msg = SYSTEM_PROMPT.format(min_words=MIN_WORDS_PER_SECTION)

    has_web_image = len(fetched_images) > 0
    image_instruction = (
        "A relevant image has already been fetched from the web for this section. "
        "You may still insert [IMAGE_PLACEHOLDER: ...] if a diagram/chart would genuinely help."
        if has_web_image
        else (
            f"No web image was available. If appropriate, insert an [IMAGE_PLACEHOLDER: {image_hint}] token."
            if needs_image
            else "Only add [IMAGE_PLACEHOLDER] if a diagram or chart is truly necessary."
        )
    )

    user_content = f"""Section Title: {section_title}
Key Points to Cover:
{chr(10).join(f'- {kp}' for kp in key_points)}

Image instruction: {image_instruction}

Web Research Context (use for accurate content and citations):
---
{snippets[:4000]}
---

Scraped Page Content (top result):
---
{scraped_context[:3000]}
---

Write the section content now (minimum {MIN_WORDS_PER_SECTION} words):"""

    llm = ChatOpenAI(api_key=OPENAI_API_KEY, model=OPENAI_MODEL, temperature=0.4)
    messages = [SystemMessage(content=system_msg), HumanMessage(content=user_content)]
    response = llm.invoke(messages)
    raw_content = response.content.strip()

    # ── Step 5: Parse out references JSON ─────────────────────────────────────
    references: List[Dict[str, str]] = []
    main_content = raw_content

    ref_start = raw_content.find("REFERENCES_JSON_START")
    ref_end = raw_content.find("REFERENCES_JSON_END")
    if ref_start != -1 and ref_end != -1:
        main_content = raw_content[:ref_start].strip()
        ref_json_str = raw_content[ref_start + len("REFERENCES_JSON_START"):ref_end].strip()
        try:
            import json
            references = json.loads(ref_json_str)
        except Exception as e:
            logger.warning(f"section_agent [{index}]: could not parse references JSON: {e}")

    # Always add the top URL as a reference if not already captured
    if top_url and not any(r.get("url") == top_url for r in references):
        references.append({
            "authors": "",
            "title": top_title,
            "publication": "Web",
            "year": "",
            "url": top_url,
        })

    # ── Step 6: Embed fetched image path token in content ────────────────────
    # Insert at the start of content so the image is near the section beginning
    if fetched_images:
        img_token = f"\n[IMAGE_PATH: {fetched_images[0]}]\n"
        # Insert after first paragraph
        paragraphs = main_content.split("\n\n", 1)
        if len(paragraphs) == 2:
            main_content = paragraphs[0] + "\n" + img_token + "\n" + paragraphs[1]
        else:
            main_content = img_token + main_content

    logger.info(
        f"section_agent [{index}]: done. "
        f"words={len(main_content.split())}, refs={len(references)}, images={len(fetched_images)}"
    )

    return {
        "index": index,
        "title": section_title,
        "content": main_content,
        "images": fetched_images,
        "references": references,
    }
