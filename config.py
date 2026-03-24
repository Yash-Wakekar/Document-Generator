"""
config.py — Central configuration for the Documentation Generator.
Loads all API keys and model settings from the .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
load_dotenv(Path(__file__).parent / ".env")

# ── API Keys ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ── Model Names ───────────────────────────────────────────────────────────────
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
GEMINI_IMAGE_MODEL: str = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# ── Paths ─────────────────────────────────────────────────────────────────────
OUTPUT_DIR: Path = Path(__file__).parent / "output"
IMAGES_DIR: Path = OUTPUT_DIR / "images"
OUTPUT_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

# ── Generation Settings ───────────────────────────────────────────────────────
# Approximate words per page in a standard document
WORDS_PER_PAGE: int = 500
# Minimum words each section agent must produce
MIN_WORDS_PER_SECTION: int = 750   # ~1.5 pages
# Max web search results returned per query
MAX_SEARCH_RESULTS: int = 10
# Max number of images to attempt to scrape per section
MAX_IMAGES_PER_SECTION: int = 3

# ── Validation ────────────────────────────────────────────────────────────────
def validate_config() -> None:
    """Raise an error if required environment variables are missing."""
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Please copy .env.example to .env and fill in the values."
        )
