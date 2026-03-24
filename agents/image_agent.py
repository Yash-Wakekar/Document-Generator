"""
agents/image_agent.py — Gemini image generation subagent node.
Receives an image prompt string and returns a file path to the generated PNG.
Called by the assembler for every [IMAGE_PLACEHOLDER: ...] token found.
"""
from __future__ import annotations
import logging
from typing import Optional

from tools.image_generate import generate_image_gemini

logger = logging.getLogger(__name__)


def run_image_agent(prompt: str) -> Optional[str]:
    """
    Generate an image from a descriptive prompt using Gemini.

    Args:
        prompt: Rich textual description of the image to generate.

    Returns:
        Absolute path string to the saved PNG, or None on failure.
    """
    logger.info(f"image_agent: generating image for prompt: '{prompt[:100]}'")
    path = generate_image_gemini(prompt)
    if path:
        logger.info(f"image_agent: image saved → '{path}'")
    else:
        logger.warning(f"image_agent: generation failed for prompt: '{prompt[:100]}'")
    return path
