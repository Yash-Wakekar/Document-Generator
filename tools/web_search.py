"""
tools/web_search.py — DuckDuckGo web search tool using the renamed 'ddgs' package.
Returns structured results: [{url, title, body}]
"""
from __future__ import annotations
import logging
from typing import List, Dict
from ddgs import DDGS
from config import MAX_SEARCH_RESULTS

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int = MAX_SEARCH_RESULTS) -> List[Dict[str, str]]:
    """
    Search the web using DuckDuckGo (via ddgs package).

    Args:
        query: The search query string.
        max_results: Number of results to return.

    Returns:
        List of dicts with keys: 'title', 'url', 'body'
    """
    results = []
    try:
        raw = DDGS().text(query, max_results=max_results)
        for r in (raw or []):
            results.append({
                "title": r.get("title", ""),
                "url":   r.get("href", "") or r.get("url", ""),
                "body":  r.get("body", "") or r.get("description", ""),
            })
        logger.info(f"web_search: '{query}' → {len(results)} results")
    except Exception as e:
        logger.warning(f"web_search failed for '{query}': {e}")
    return results


def scrape_page_text(url: str, max_chars: int = 8000) -> str:
    """
    Scrape and return the main text content of a web page.

    Args:
        url: The URL to scrape.
        max_chars: Maximum characters to return (avoids token overflow).

    Returns:
        Cleaned plain text from the page, or empty string on failure.
    """
    import requests
    from bs4 import BeautifulSoup

    headers = {"User-Agent": "Mozilla/5.0 (compatible; DocGenBot/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        cleaned = "\n".join(lines)
        return cleaned[:max_chars]
    except Exception as e:
        logger.warning(f"scrape_page_text failed for '{url}': {e}")
        return ""
