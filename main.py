"""
main.py — CLI entry point for the Agentic Documentation Generator.

Usage:
    python main.py

The program guides the user through:
1. Entering topic, description, and page count.
2. Reviewing and refining the outline (human-in-the-loop via terminal).
3. Confirming to start parallel document generation.
4. Displaying progress and the path to the final .docx.
"""
from __future__ import annotations
import logging
import sys
import uuid
from typing import Any, Dict

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Suppress noisy library logs
for lib in ("httpx", "httpcore", "urllib3", "duckduckgo_search"):
    logging.getLogger(lib).setLevel(logging.WARNING)


def main() -> None:
    # ── Import after logging setup ────────────────────────────────────────────
    from config import validate_config
    validate_config()

    from langgraph.types import Command
    from graph.outline_graph import build_outline_graph, _format_outline_for_display
    from graph.doc_graph import build_doc_graph

    _print_banner()

    # ── Step 1: Gather user inputs ─────────────────────────────────────────────
    topic = _prompt("📌 Enter the documentation topic", required=True)
    description = _prompt(
        "📝 Enter a description or focus areas (press Enter to skip)", required=False
    )
    MIN_PAGES, MAX_PAGES = 5, 30
    while True:
        pages_str = _prompt(
            f"📄 How many pages should the document be? ({MIN_PAGES}–{MAX_PAGES})",
            required=True,
        )
        try:
            total_pages = int(pages_str.strip())
            if total_pages < MIN_PAGES:
                print(f"  ⚠  Minimum is {MIN_PAGES} pages. "
                      f"Please enter a value between {MIN_PAGES} and {MAX_PAGES}.")
            elif total_pages > MAX_PAGES:
                print(f"  ⚠  Maximum is {MAX_PAGES} pages. "
                      f"Please enter a value between {MIN_PAGES} and {MAX_PAGES}.")
            else:
                break
        except ValueError:
            print(f"  ⚠  Please enter a whole number between {MIN_PAGES} and {MAX_PAGES}.")

    # ── Step 2: Outline generation + HITL loop ─────────────────────────────────
    print("\n" + "─" * 70)
    print("  🤖 Generating outline... (this may take a few seconds)")
    print("─" * 70 + "\n")

    outline_graph = build_outline_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: Dict[str, Any] = {
        "topic": topic,
        "description": description,
        "total_pages": total_pages,
        "outline": {},
        "user_feedback": "",
        "approved": False,
        "iteration": 0,
        "sections_content": [],
        "references": [],
        "final_sections": [],
        "ieee_references": [],
        "output_path": None,
    }

    # Run outline graph until first interrupt (human_review node)
    events = list(outline_graph.stream(initial_state, config=config, stream_mode="values"))

    while True:
        # Get the current graph state to display pending interrupt
        snapshot = outline_graph.get_state(config)

        # Check if we have an interrupt waiting
        interrupts = snapshot.tasks
        if not interrupts:
            break

        # Display the outline to the user
        current_state = snapshot.values
        outline = current_state.get("outline", {})
        iteration = current_state.get("iteration", 1)
        display_text = _format_outline_for_display(outline, iteration)
        print(display_text)

        print("\n  Options:")
        print("  • Type 'ok' / 'yes' / 'confirm' → approve and start generation")
        print("  • Type your feedback / requested changes → refine the outline")
        print()
        user_input = input("  Your response: ").strip()

        # ── Guardrail check before resuming ──────────────────────────────────
        guardrail_msg = _apply_guardrails(user_input)
        if guardrail_msg:
            print(f"  ⚠  {guardrail_msg}")
            continue  # Re-prompt without resuming the graph

        # Resume the graph with user's input
        events = list(
            outline_graph.stream(
                Command(resume=user_input),
                config=config,
                stream_mode="values",
            )
        )

        # Check if approved
        new_snapshot = outline_graph.get_state(config)
        if new_snapshot.values.get("approved", False):
            print("\n  ✅ Outline approved! Starting document generation...\n")
            approved_state = new_snapshot.values
            break
        elif not new_snapshot.tasks:
            # Graph ended (max iterations reached)
            approved_state = new_snapshot.values
            break
    else:
        # Fallback: outline approved on first pass without interrupt
        approved_state = outline_graph.get_state(config).values

    # ── Step 3: Document generation (parallel section agents) ─────────────────
    print("─" * 70)
    n_sections = len(approved_state.get("outline", {}).get("sections", []))
    print(f"  📚 Generating {n_sections} sections in parallel...")
    print(f"     ⏳ This will take 1–3 minutes depending on section count.")
    print("─" * 70 + "\n")

    doc_graph = build_doc_graph()
    final_events = list(doc_graph.stream(approved_state, stream_mode="values"))

    # Get final state
    final_state = final_events[-1] if final_events else approved_state
    output_path = final_state.get("output_path")

    # ── Step 4: Done ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    if output_path:
        print(f"  ✅ Documentation generated successfully!")
        print(f"  📄 Output: {output_path}")
        n_refs = len(final_state.get("ieee_references", []))
        print(f"  📚 IEEE References included: {n_refs}")
    else:
        print("  ❌ Document generation failed. Check logs above for details.")
    print("=" * 70 + "\n")


def _apply_guardrails(user_input: str) -> str:
    """
    Validate outline-review feedback before sending it to the AI.
    Returns an error message string if input is invalid, else empty string.

    Guardrails:
    1. Empty input (not a confirmation) → prompt again.
    2. Too short to be meaningful feedback (< 3 words and not a confirm keyword).
    3. Likely off-topic (contains no document/content-related words AND is not a confirm).
    4. Potentially harmful / prompt-injection patterns.
    """
    CONFIRM_KEYWORDS = {"ok", "yes", "confirm", "approve", "done", "looks good",
                        "good", "proceed", "go", "fine", "great", "perfect"}
    HARMFUL_PATTERNS = [
        "ignore previous", "disregard", "forget instructions", "jailbreak",
        "do not follow", "override",
    ]
    FEEDBACK_HINT_WORDS = [
        "add", "remove", "change", "update", "include", "exclude", "more",
        "less", "section", "topic", "focus", "cover", "expand", "reduce",
        "rename", "replace", "merge", "split", "reorder", "page", "detail",
    ]

    lowered = user_input.lower().strip()

    # Empty input
    if not lowered:
        return "Response cannot be empty. Type 'ok' to approve or describe your changes."

    # Confirm keyword — always valid
    if any(lowered == kw or lowered.startswith(kw) for kw in CONFIRM_KEYWORDS):
        return ""

    # Harmful / injection patterns
    for pattern in HARMFUL_PATTERNS:
        if pattern in lowered:
            return ("That input cannot be processed. Please provide constructive "
                    "feedback about the outline content only.")

    words = lowered.split()

    # Too short without being a confirm keyword
    if len(words) < 3:
        return ("Feedback is too short to be useful. Please describe what you'd "
                "like to change in the outline (e.g. 'Add a section on deployment').")

    # Optionally warn if input looks completely off-topic (no feedback-hint words)
    has_hint = any(hw in lowered for hw in FEEDBACK_HINT_WORDS)
    if not has_hint and len(words) < 6:
        return ("That doesn't look like outline feedback. Please describe a specific "
                "change you'd like (e.g. 'Remove the history section and add more on "
                "practical use cases').")

    return ""  # Input is valid


def _prompt(message: str, required: bool = True) -> str:
    """Print a prompt and return stripped user input."""
    while True:
        print(f"\n  {message}")
        value = input("  > ").strip()
        if value or not required:
            return value
        print("  ⚠  This field is required.")


def _print_banner() -> None:
    banner = r"""
  ╔══════════════════════════════════════════════════════════════╗
  ║         🤖  Agentic AI Documentation Generator              ║
  ║   Powered by LangGraph · GPT-4o · Gemini · DuckDuckGo      ║
  ╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


if __name__ == "__main__":
    main()
