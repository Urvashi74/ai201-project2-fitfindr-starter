"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Use the LLM to extract description, size, and max_price from a natural
    language query. Returns a dict with keys:
        description (str), size (str | None), max_price (float | None)
    """
    prompt = (
        "Extract search parameters from this secondhand clothing query. "
        "Return ONLY valid JSON with exactly these keys:\n"
        '  "description": a short keyword phrase describing the item (required)\n'
        '  "size": the size string if mentioned, otherwise null\n'
        '  "max_price": the maximum price as a number if mentioned, otherwise null\n\n'
        f"Query: {query}\n\n"
        "JSON only, no explanation:"
    )
    try:
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if the LLM wrapped the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    # Step 1: initialize session
    session = _new_session(query, wardrobe)

    # Step 2: parse query with LLM → description, size, max_price
    try:
        parsed = _parse_query(query)
    except Exception:
        session["error"] = "Couldn't understand your request — please describe what you're looking for."
        return session

    description = parsed.get("description", "").strip()
    if not description:
        session["error"] = "Couldn't understand your request — please describe what you're looking for."
        return session

    size      = parsed.get("size") or None
    max_price = parsed.get("max_price") or None
    if max_price is not None:
        max_price = float(max_price)

    session["parsed"] = {"description": description, "size": size, "max_price": max_price}

    # Step 3: search listings; stop early if nothing found
    session["search_results"] = search_listings(description, size=size, max_price=max_price)

    if not session["search_results"]:
        parts = [f"No listings found for '{description}'"]
        if size:
            parts.append(f"size {size}")
        if max_price is not None:
            parts.append(f"under ${max_price:.0f}")
        hint = ". Try one of these: remove the size filter, raise your budget, or use broader keywords."
        session["error"] = ", ".join(parts) + hint
        return session

    # Step 4: pick the top-ranked result
    session["selected_item"] = session["search_results"][0]
    print(f"\n[STATE] selected_item → passing to suggest_outfit:\n{session['selected_item']}\n")

    # Step 5: suggest an outfit
    session["outfit_suggestion"] = suggest_outfit(session["selected_item"], wardrobe)
    print(f"[STATE] outfit_suggestion → passing to create_fit_card:\n{session['outfit_suggestion']}\n")

    if not session["outfit_suggestion"].strip():
        session["error"] = "Couldn't generate outfit suggestions — try again."
        return session

    # Step 6: generate the fit card
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])

    if not session["fit_card"].strip():
        session["error"] = "Couldn't generate a fit card."
        return session

    # Step 7: return completed session (error stays None)
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
