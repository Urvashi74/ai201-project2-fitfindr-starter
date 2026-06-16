# FitFindr

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. Given a natural language query, FitFindr searches mock thrift listings, suggests a complete outfit using the user's wardrobe, generates a shareable fit card caption, and checks whether the price is fair — handling failures at every step rather than crashing.

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

Run the agent directly (CLI test):
```bash
python agent.py
```

Run tests:
```bash
python -m pytest tests/test_tools.py -v
```

---

## Tools

### `search_listings(description, size, max_price)` — `tools.py`

Searches the mock listings dataset and returns matching items sorted by relevance.

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Keywords describing the item (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size to filter by; case-insensitive substring match so `"M"` matches `"S/M"`. Pass `None` to skip. |
| `max_price` | `float \| None` | Maximum price inclusive. Pass `None` to skip. |

**Returns:** `list[dict]` — matching listing dicts sorted by relevance score (highest first). Returns `[]` if nothing matches — never raises.

**No-results handling:** The agent sets `session["error"]` to a message like `"No listings found for 'vintage graphic tee', size M, under $30. Try one of these: remove the size filter, raise your budget, or use broader keywords."` and returns early. `suggest_outfit` and `create_fit_card` are never called with empty input.

---

### `suggest_outfit(new_item, wardrobe)` — `tools.py`

Given the thrifted item and the user's wardrobe, calls the LLM to suggest 1–2 complete outfit combinations using named wardrobe pieces.

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict. Uses `title`, `style_tags`, `colors`, `category`, `condition`. |
| `wardrobe` | `dict` | A wardrobe dict with an `items` key. May be empty. |

**Returns:** `str` — a non-empty outfit suggestion. Never returns `""`.

**Empty wardrobe handling:** If `wardrobe["items"]` is empty, the tool switches to a general-advice prompt asking the LLM for outfit ideas using common wardrobe staples — no crash, no empty string. If the LLM call fails, returns: `"Couldn't generate outfit suggestions right now — try pairing this with basics in a similar color palette."`

---

### `create_fit_card(outfit, new_item)` — `tools.py`

Generates a short, casual Instagram/TikTok-style caption for the complete outfit. Uses a higher LLM temperature to produce different output each time.

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit`. |
| `new_item` | `dict` | The listing dict. Used to mention item name, price, and platform once each. |

**Returns:** `str` — a 2–4 sentence caption. Mentions the item name, price, and platform naturally. Never returns `""`.

**Empty input handling:** If `outfit` is empty or whitespace-only, returns `"Couldn't write a fit card — no outfit suggestion was available. Try running the full flow again from the search step."` without calling the LLM.

---

### `estimate_price_fairness(item)` — `tools.py`

Compares an item's price against comparable listings in the dataset and returns a plain-language verdict. This is pure Python — no LLM call, no external API.

| Parameter | Type | Description |
|-----------|------|-------------|
| `item` | `dict` | A listing dict — the item being evaluated. Uses `id`, `price`, `category`, and `style_tags`. |

**Returns:** `str` — a non-empty verdict string. Never raises.

**How comparisons are made:**

1. **Find comparables** — loads all listings and filters to those that share the same `category` as the item AND have at least one overlapping `style_tag`. The item itself is excluded by `id`.
2. **Calculate statistics** — computes the average, minimum, and maximum price across all comparable listings.
3. **Apply verdict tiers:**
   - **Great deal** — item is ≥15% below the comparable average
   - **Fair price** — item is within 10% of the comparable average (either direction)
   - **Above average** — item is >10% above the comparable average
4. **Return a sentence** that names the item, states the price, gives the percentage difference, and shows the full comparable price range and count.

Example output:
```
Great deal. Y2K Baby Tee — Butterfly Print ($18) — $18 is 18% below the average
for similar tops. Comparable tops range from $15–$35 across 14 similar listing(s).
Listed as excellent condition.
```

**No-comparables handling:** If no listings in the dataset share the item's category and style tags, returns `"Not enough comparable listings to estimate price fairness for this item."` — never raises.

---

## Planning Loop

The agent (`run_agent()` in `agent.py`) runs tools in a **fixed conditional chain** — each step only executes if the previous one succeeded. It does not call all tools blindly in sequence; it checks the result at each step and stops early if something fails.

```
User query + wardrobe
        |
        v
  Step 1: LLM parses query → description, size, max_price
        | description missing? → set error, return early
        v
  Step 2: search_listings(description, size, max_price)
        | results == [] ? → set error, return early
        | results non-empty → selected_item = results[0]
        v
  Step 3: suggest_outfit(selected_item, wardrobe)
        | wardrobe empty? → switch to general-advice prompt (continues)
        | outfit_suggestion == "" ? → set error, return early
        v
  Step 4: create_fit_card(outfit_suggestion, selected_item)
        | outfit empty? → return error string (no LLM call)
        v
  Return session (error=None, all fields populated)
```

`estimate_price_fairness` is called in `app.py` after `run_agent()` succeeds, using `session["selected_item"]` — it does not affect the planning loop or session state.

The conditional at Step 2 is the key branch: if `search_listings` returns an empty list, the agent sets `session["error"]` and returns immediately — `suggest_outfit` is never called with empty input.

---

## State Management

All state lives in a single `session` dict created at the start of each run. No tool writes to the session — only `run_agent()` does.

| Session key | Written after | Read by |
|-------------|---------------|---------|
| `query` | initialization | query parser |
| `parsed` | LLM query parsing | `search_listings` call |
| `search_results` | `search_listings` returns | empty check in planning loop |
| `selected_item` | top result picked from `search_results` | `suggest_outfit`, `create_fit_card`, `estimate_price_fairness` |
| `wardrobe` | initialization | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` returns | `create_fit_card`, final output |
| `fit_card` | `create_fit_card` returns | final output |
| `error` | any early-exit branch | caller checks this first |

Key handoffs:
- `session["selected_item"]` — the same listing dict flows from `search_listings` into `suggest_outfit`, `create_fit_card`, and `estimate_price_fairness`. The user never re-enters it.
- `session["outfit_suggestion"]` — the string returned by `suggest_outfit` is passed directly as the `outfit` argument to `create_fit_card`.

---

## Error Handling

| Tool | Failure mode | What happens |
|------|-------------|--------------|
| `search_listings` | No results match the query | `session["error"]` set with description, size, and price in the message plus suggestions to broaden the search. Agent returns immediately — downstream tools not called. |
| `suggest_outfit` | Wardrobe is empty | Switches to a general-advice LLM prompt. Returns non-empty styling advice — no error, flow continues. |
| `suggest_outfit` | LLM call fails | `except Exception` catches it; returns fallback string. Never crashes. |
| `create_fit_card` | `outfit` is empty or whitespace | Returns error string immediately, no LLM call made. |
| `create_fit_card` | LLM call fails | `except Exception` catches it; returns a fallback string using item title/price/platform. |
| `estimate_price_fairness` | No comparable listings | Returns a plain-language message explaining why. No exception. |
| `_parse_query` | LLM fails to parse query | Returns `{}`; agent catches the missing `description` and sets `session["error"]`. |

---

## AI Usage

### Instance 1 — Implementing `search_listings()`

**What I directed:** I gave Claude the Tool 1 block from `planning.md` — the input parameter types, the size-matching rule ("M" must match "S/M"), the scoring logic (keyword overlap across `title`, `description`, and `style_tags`), and the failure mode (return `[]`, never raise). I also gave it the `load_listings()` docstring from `utils/data_loader.py` and asked it to implement the function body only, with no changes to the signature.

**What I checked before trusting it:** I read the generated code to verify: (1) the size filter used `in` for substring matching rather than `==`, (2) `max_price=None` was guarded with `if max_price is not None` so it skipped filtering entirely, and (3) zero-score listings were dropped before sorting.

**What I revised:** The first generated version used `listing["size"] == size` for the size filter — an exact match that would have missed "S/M" when the user typed "M". I caught this before running any tests and directed Claude to fix it to case-insensitive substring matching (`size.lower() in listing["size"].lower()`). I then ran four test queries to verify the fix held, including one that specifically confirmed `"M"` matched a listing whose size field was `"S/M"`.

---

### Instance 2 — Implementing the planning loop in `run_agent()`

**What I directed:** I gave Claude the Planning Loop section of `planning.md` (all five numbered steps with their exact branch conditions), the State Management table, the Architecture diagram, and the `_new_session()` and `run_agent()` stubs from `agent.py`. I asked it to implement `run_agent()` only — no new functions, no signature changes — and specified that query parsing should use the LLM (not regex), and that the error message for no results should be built dynamically to omit the size or price clause if those filters weren't applied.

**What I checked before trusting it:** I verified that: (1) `session["selected_item"]` was set to `search_results[0]` and not re-fetched later, (2) the function returned immediately after the empty `search_results` check without calling `suggest_outfit`, and (3) `session["error"]` was `None` on a successful run.

**What I revised:** The initial implementation wrapped the entire `_parse_query` call in a `try/except` in `run_agent()` but left `_parse_query` itself with no error handling — so a network failure inside the function would propagate as an unhandled exception if the outer try/except was ever removed or moved. I directed Claude to add a `try/except` inside `_parse_query` itself that returns `{}` on failure, making each function self-contained. I also added `try/except` blocks inside `suggest_outfit` and `create_fit_card` for consistency, so every Groq API call has its own local error handler rather than relying on callers to catch exceptions.

---

## File Structure

```
fitfindr/
├── data/
│   ├── listings.json           # 40 mock secondhand listings
│   └── wardrobe_schema.json    # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py          # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tests/
│   └── test_tools.py           # 15 pytest tests covering all failure modes
├── tools.py                    # search_listings, suggest_outfit, create_fit_card, estimate_price_fairness
├── agent.py                    # run_agent() — planning loop + state management
├── app.py                      # Gradio UI
├── planning.md                 # Design spec and architecture
└── requirements.txt
```
