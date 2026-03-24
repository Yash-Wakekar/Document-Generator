"""
tools/image_generate.py — Gemini image generation using google-genai SDK (v1+).

Strategy (with fallback):
  1. Primary: gemini-2.5-flash-image via generate_content with response_modalities=['IMAGE']
  2. Fallback: imagen-4.0-fast-generate-001 via client.models.generate_images()
"""
from __future__ import annotations
import io
import logging
import uuid
from typing import Optional

from config import GEMINI_API_KEY, IMAGES_DIR

logger = logging.getLogger(__name__)

# Primary: Gemini native image generation (confirmed available via ListModels)
PRIMARY_MODEL = "gemini-2.5-flash-image"
# Fallback: Imagen 4 fast
FALLBACK_MODEL = "imagen-4.0-fast-generate-001"


def generate_image_gemini(prompt: str) -> Optional[str]:
    """
    Generate an image from a text prompt.
    Tries gemini-2.5-flash-image first; falls back to imagen-4.0-fast-generate-001.

    Args:
        prompt: Descriptive text for the image to generate.

    Returns:
        Absolute path string to the saved PNG, or None on failure.
    """
    result = _try_gemini_flash_image(prompt)
    if result:
        return result
    return _try_imagen4(prompt)


def _try_gemini_flash_image(prompt: str) -> Optional[str]:
    """Use gemini-2.5-flash-image with response_modalities=['IMAGE']."""
    try:
        from google import genai
        from google.genai import types
        from PIL import Image

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model=PRIMARY_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        for candidate in (response.candidates or []):
            for part in (candidate.content.parts if candidate.content else []):
                if part.inline_data and part.inline_data.data:
                    img = Image.open(io.BytesIO(part.inline_data.data))
                    save_path = IMAGES_DIR / f"{uuid.uuid4().hex}.png"
                    img.save(save_path, "PNG")
                    logger.info(f"generate_image_gemini [{PRIMARY_MODEL}]: saved → '{save_path}'")
                    return str(save_path)

        logger.warning(f"_try_gemini_flash_image: no image in response for: '{prompt[:60]}'")
        return None

    except Exception as e:
        logger.warning(f"_try_gemini_flash_image failed: {e}")
        return None


def _try_imagen4(prompt: str) -> Optional[str]:
    """Fallback: use imagen-4.0-fast-generate-001 via generate_images()."""
    try:
        from google import genai
        from PIL import Image

        client = genai.Client(api_key=GEMINI_API_KEY)
        result = client.models.generate_images(
            model=FALLBACK_MODEL,
            prompt=prompt,
            config={"number_of_images": 1},
        )

        if result.generated_images:
            img_data = result.generated_images[0].image.image_bytes
            img = Image.open(io.BytesIO(img_data))
            save_path = IMAGES_DIR / f"{uuid.uuid4().hex}.png"
            img.save(save_path, "PNG")
            logger.info(f"generate_image_gemini [{FALLBACK_MODEL}]: saved → '{save_path}'")
            return str(save_path)

        logger.warning(f"_try_imagen4: no images returned for: '{prompt[:60]}'")
        return None

    except Exception as e:
        logger.error(f"_try_imagen4 failed: {e}")
        return None
