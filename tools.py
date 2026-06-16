"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings() from utils/data_loader.py.
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    keywords = set(description.lower().split())

    def _score(listing: dict) -> int:
        searchable = " ".join([
            listing["title"],
            listing["description"],
            " ".join(listing["style_tags"]),
        ]).lower()
        return sum(1 for kw in keywords if kw in searchable)

    scored = [(s, l) for l in listings if (s := _score(l)) > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    print(f"\n[suggest_outfit] received new_item:\n{new_item}\n")

    title    = new_item.get("title", "this item")
    style_tags = ", ".join(new_item.get("style_tags", []))
    colors   = ", ".join(new_item.get("colors", []))
    category = new_item.get("category", "clothing")
    condition = new_item.get("condition", "good")

    if not wardrobe.get("items"):
        prompt = (
            f"The user is considering buying a secondhand {category} called '{title}' "
            f"(style: {style_tags}; colors: {colors}; condition: {condition}). "
            f"They haven't described their wardrobe yet. "
            f"Suggest 2 complete outfits using common wardrobe staples that would pair "
            f"well with this item's vibe. Be specific about garment types, colors, and "
            f"how to wear them together. Keep the response under 150 words."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {item['name']} ({item['category']}; "
            f"colors: {', '.join(item['colors'])}; "
            f"style: {', '.join(item['style_tags'])})"
            for item in wardrobe["items"]
        )
        prompt = (
            f"The user just found a secondhand {category} called '{title}' "
            f"(style: {style_tags}; colors: {colors}; condition: {condition}). "
            f"Here is their current wardrobe:\n{wardrobe_lines}\n\n"
            f"Suggest 1–2 complete outfits pairing this new item with specific named "
            f"pieces from their wardrobe above. Use the exact names listed. "
            f"Include shoes and accessories where relevant. Keep the response under 150 words."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return (
            "Couldn't generate outfit suggestions right now — "
            "try pairing this with basics in a similar color palette."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    print(f"\n[create_fit_card] received outfit:\n{outfit}\n")
    print(f"[create_fit_card] received new_item:\n{new_item}\n")

    if not outfit.strip():
        return (
            "Couldn't write a fit card — no outfit suggestion was available. "
            "Try running the full flow again from the search step."
        )

    title    = new_item.get("title", "this piece")
    price    = new_item.get("price", "")
    platform = new_item.get("platform", "a thrift app")

    prompt = (
        f"Write a 2–4 sentence Instagram caption for a thrift outfit post. "
        f"The thrifted item is '{title}', bought for ${price} on {platform}. "
        f"The full outfit is: {outfit}\n\n"
        f"Rules:\n"
        f"- Mention the item name, price (${price}), and platform ({platform}) exactly once each\n"
        f"- Write in first person, casual and authentic — like a real person's OOTD post, not an ad\n"
        f"- Reference specific outfit details from the description above\n"
        f"- No hashtags\n"
        f"Return only the caption text, nothing else."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.1,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return (
            f"just thrifted '{title}' for ${price} on {platform} "
            "and can't stop thinking about this outfit."
        )


# ── Tool 4: estimate_price_fairness ──────────────────────────────────────────

def estimate_price_fairness(item: dict) -> str:
    """
    Compare an item's price against comparable listings in the dataset and
    return a plain-language verdict.

    Args:
        item: A listing dict (same format returned by search_listings).
              Uses id, price, category, and style_tags to find comparables.

    Returns:
        A non-empty string verdict. Never raises an exception.
        If no comparables exist, explains that rather than guessing.
    """
    item_price    = item.get("price")
    item_category = item.get("category", "")
    item_tags     = set(item.get("style_tags", []))
    item_id       = item.get("id")
    item_title    = item.get("title", "This item")
    item_condition = item.get("condition", "")

    if item_price is None:
        return "Can't estimate price fairness — this item has no price listed."

    all_listings = load_listings()

    # Find comparables: same category, at least one overlapping style tag, not the item itself
    comparables = [
        l for l in all_listings
        if l["id"] != item_id
        and l["category"] == item_category
        and set(l.get("style_tags", [])) & item_tags
    ]

    if not comparables:
        return (
            f"Not enough comparable listings to estimate price fairness for this item "
            f"(no other {item_category} listings share its style tags)."
        )

    prices = [l["price"] for l in comparables]
    avg    = sum(prices) / len(prices)
    low    = min(prices)
    high   = max(prices)
    diff   = item_price - avg
    pct    = (diff / avg) * 100

    if pct <= -15:
        verdict = "Great deal"
        detail  = f"${item_price:.0f} is {abs(pct):.0f}% below the average for similar {item_category}."
    elif pct <= 10:
        verdict = "Fair price"
        detail  = f"${item_price:.0f} is right in line with similar {item_category} (avg ${avg:.0f})."
    else:
        verdict = "Above average"
        detail  = f"${item_price:.0f} is {pct:.0f}% above the average for similar {item_category}."

    condition_note = f" Listed as {item_condition} condition." if item_condition else ""

    return (
        f"{verdict}. {item_title} (${item_price:.0f}) — {detail} "
        f"Comparable {item_category} range from ${low:.0f}–${high:.0f} "
        f"across {len(comparables)} similar listing(s).{condition_note}"
    )
