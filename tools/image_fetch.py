"""
tools/image_fetch.py — Fetches a relevant image from a web page URL.
Scrapes the same page the section agent used for content extraction.
Returns a local file path if successful, None otherwise.
"""
from __future__ import annotations
import logging
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

from config import IMAGES_DIR

logger = logging.getLogger(__name__)

# Minimum image dimensions to be considered "content" (not icons/ads)
MIN_WIDTH = 200
MIN_HEIGHT = 150
# Allowed image MIME types
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def fetch_image_from_page(page_url: str) -> Optional[str]:
    """
    Scrape the given URL and download the first suitable image found.

    Strategy:
    1. Parse all <img> tags on the page.
    2. Filter out tiny icons, SVGs, base64 blobs, and tracker pixels.
    3. Download the first eligible image.
    4. Verify dimensions meet the minimum threshold.
    5. Save to IMAGES_DIR and return the absolute path string.

    Args:
        page_url: The page URL to scrape for images.

    Returns:
        Absolute path string to the saved image, or None if none found.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DocGenBot/1.0)"}
    try:
        resp = requests.get(page_url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        img_tags = soup.find_all("img")
    except Exception as e:
        logger.warning(f"fetch_image_from_page: failed to load page '{page_url}': {e}")
        return None

    for img in img_tags:
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if not src:
            continue
        # Skip base64-embedded and SVG
        if src.startswith("data:") or src.endswith(".svg"):
            continue
        # Resolve relative URLs
        img_url = urljoin(page_url, src)
        # Validate URL scheme
        parsed = urlparse(img_url)
        if parsed.scheme not in ("http", "https"):
            continue

        saved_path = _download_and_validate(img_url, headers)
        if saved_path:
            logger.info(f"fetch_image_from_page: saved '{img_url}' → '{saved_path}'")
            return saved_path

    logger.info(f"fetch_image_from_page: no suitable image found on '{page_url}'")
    return None


def _download_and_validate(img_url: str, headers: dict) -> Optional[str]:
    """Download an image URL, validate size, save to disk."""
    try:
        resp = requests.get(img_url, headers=headers, timeout=10, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in ALLOWED_CONTENT_TYPES:
            return None

        # Save to a temp buffer first to check dimensions
        img_bytes = resp.content
        from io import BytesIO
        img = Image.open(BytesIO(img_bytes))
        if img.width < MIN_WIDTH or img.height < MIN_HEIGHT:
            return None

        # Convert to RGB so we can always save as PNG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        filename = f"{uuid.uuid4().hex}.png"
        save_path = IMAGES_DIR / filename
        img.save(save_path, "PNG")
        return str(save_path)
    except Exception as e:
        logger.debug(f"_download_and_validate failed for '{img_url}': {e}")
        return None
