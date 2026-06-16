"""
tests/test_tools.py

One test per failure mode for each of the three FitFindr tools.
LLM-dependent tests use unittest.mock to avoid real API calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def graphic_tee():
    """Top-ranked result for 'vintage graphic tee' under $30."""
    results = search_listings("vintage graphic tee", max_price=30.0)
    assert results, "fixture needs at least one match"
    return results[0]


@pytest.fixture
def outfit_suggestion():
    return (
        "Pair with baggy straight-leg jeans, chunky white sneakers, "
        "and the vintage black denim jacket."
    )


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # impossible query — must return [] not raise
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_substring():
    # "M" must match listings whose size field contains "M", including "S/M"
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_size_m_matches_s_slash_m():
    # Specifically verify the S/M case mentioned in planning.md
    results = search_listings("tee", size="M", max_price=None)
    sizes = [r["size"] for r in results]
    assert any("S/M" in s for s in sizes), f"Expected S/M in results, got: {sizes}"


def test_search_sorted_by_relevance():
    # First result should score higher than the last for a specific query
    results = search_listings("vintage graphic tee", max_price=None)
    assert len(results) >= 2
    # Top result must mention either "graphic", "tee", or "vintage" in title/tags
    top = results[0]
    searchable = (top["title"] + " ".join(top["style_tags"])).lower()
    assert any(kw in searchable for kw in ["graphic", "tee", "vintage"])


def test_search_no_filters_skipped():
    # size=None and max_price=None should not filter anything out
    all_results = search_listings("vintage", size=None, max_price=None)
    filtered = search_listings("vintage", size=None, max_price=999)
    assert len(all_results) == len(filtered)


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def _mock_groq_response(text: str):
    """Return a mock Groq client whose completion returns `text`."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=text))]
    )
    return mock_client


def test_suggest_outfit_empty_wardrobe_does_not_crash(graphic_tee):
    # Empty wardrobe must not raise — must return a non-empty string
    with patch("tools._get_groq_client", return_value=_mock_groq_response(
        "Pair with white straight-leg jeans and chunky sneakers."
    )):
        result = suggest_outfit(graphic_tee, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_empty_wardrobe_uses_general_prompt(graphic_tee):
    # When wardrobe is empty, the prompt sent to the LLM must NOT reference wardrobe pieces
    captured_prompt = {}

    def mock_create(**kwargs):
        captured_prompt["content"] = kwargs["messages"][0]["content"]
        return MagicMock(choices=[MagicMock(message=MagicMock(content="General advice."))])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = mock_create

    with patch("tools._get_groq_client", return_value=mock_client):
        suggest_outfit(graphic_tee, get_empty_wardrobe())

    assert "wardrobe" not in captured_prompt["content"].lower() or \
           "haven't described" in captured_prompt["content"].lower()


def test_suggest_outfit_wardrobe_prompt_names_pieces(graphic_tee):
    # When wardrobe has items, the prompt must include at least one item name
    wardrobe = get_example_wardrobe()
    first_item_name = wardrobe["items"][0]["name"]
    captured_prompt = {}

    def mock_create(**kwargs):
        captured_prompt["content"] = kwargs["messages"][0]["content"]
        return MagicMock(choices=[MagicMock(message=MagicMock(content="Wear with jeans."))])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = mock_create

    with patch("tools._get_groq_client", return_value=mock_client):
        suggest_outfit(graphic_tee, wardrobe)

    assert first_item_name in captured_prompt["content"]


def test_suggest_outfit_llm_exception_returns_fallback(graphic_tee):
    # If the LLM call throws, must return the fallback string — not crash
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("network error")

    with patch("tools._get_groq_client", return_value=mock_client):
        result = suggest_outfit(graphic_tee, get_example_wardrobe())

    assert "color palette" in result
    assert result.strip() != ""


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string(graphic_tee):
    # Empty string must return error message without calling the LLM
    with patch("tools._get_groq_client") as mock_groq:
        result = create_fit_card("", graphic_tee)
        mock_groq.assert_not_called()

    assert "Couldn't write a fit card" in result


def test_create_fit_card_whitespace_outfit_returns_error_string(graphic_tee):
    # Whitespace-only string must also trigger the guard
    result = create_fit_card("   ", graphic_tee)
    assert "Couldn't write a fit card" in result


def test_create_fit_card_returns_nonempty_string(graphic_tee, outfit_suggestion):
    with patch("tools._get_groq_client", return_value=_mock_groq_response(
        "thrifted this tee for $18 on depop and it goes with everything."
    )):
        result = create_fit_card(outfit_suggestion, graphic_tee)

    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_llm_exception_returns_fallback(graphic_tee, outfit_suggestion):
    # If the LLM call throws, must return the fallback string — not crash
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("timeout")

    with patch("tools._get_groq_client", return_value=mock_client):
        result = create_fit_card(outfit_suggestion, graphic_tee)

    assert isinstance(result, str)
    assert result.strip() != ""
    assert graphic_tee["title"] in result
