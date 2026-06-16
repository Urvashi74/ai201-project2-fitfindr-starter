# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Filters the mock listings dataset by size and price, then scores and ranks results by keyword overlap with the user's description. Returns the best-matching items sorted by relevance.

**Input parameters:**
- `description` (str): Keywords describing what the user wants (e.g., "vintage graphic tee"). Used to score each listing by overlap with its `title`, `description`, and `style_tags`.
- `size` (str | None): Size string to filter by (e.g., "M"). Case-insensitive; "M" also matches "S/M". Pass `None` to skip size filtering.
- `max_price` (float | None): Maximum price in dollars, inclusive (e.g., 30.0). Pass `None` to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Returns an empty list if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to a message like "No listings found for '[description]' in size [size] under $[max_price]. Try broadening your search — remove the size filter or raise your budget." It then returns the session immediately without calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Given the thrifted item and the user's wardrobe, calls the LLM to suggest 1–2 complete outfit combinations using specific named pieces from the wardrobe. Falls back to general styling advice when the wardrobe is empty.

**Input parameters:**
- `new_item` (dict): A listing dict (the item the user is considering buying). The tool uses its `title`, `style_tags`, `colors`, `category`, and `condition` to build the prompt.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts (each with `name`, `category`, `colors`, `style_tags`, `notes`). May be empty.

**What it returns:**
A non-empty string with outfit suggestions. If the wardrobe has items, the response names specific pieces (e.g., "your baggy dark-wash jeans"). If the wardrobe is empty, the response gives general styling advice for the item's vibe and category.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the tool switches to a general-advice prompt rather than failing. If the LLM call itself fails (network error, etc.), the tool catches the exception and returns a fallback string like "Couldn't generate outfit suggestions right now — try pairing this with basics in a similar color palette."

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, casual, Instagram/TikTok-style caption for the complete outfit — the kind of text someone would post with an OOTD photo. Uses a higher LLM temperature to produce varied output each time.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit`. Used to describe the full look in the caption.
- `new_item` (dict): The listing dict for the thrifted item. Used to naturally mention the item name, price, and platform once each.

**What it returns:**
A 2–4 sentence string usable as a social media caption. It should feel authentic and specific, mention the item name, price, and platform once each, and capture the outfit's vibe in concrete terms. Never returns an empty string.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the tool returns an error string like "Can't generate a fit card without an outfit suggestion — make sure suggest_outfit ran successfully first." No exception is raised.

---

### Additional Tools (if any)

### Tool 4: estimate_price_fairness

**What it does:**
Compares an item's price against comparable listings in the dataset (same category, overlapping style tags) and returns a plain-language verdict: whether the price is a deal, fair, or above average relative to similar items.

**Input parameters:**
- `item` (dict): A listing dict — the item being evaluated. Uses `id`, `price`, `category`, and `style_tags` to find and score comparables.

**What it returns:**
A non-empty string verdict. Example: `"Fair price. The Y2K Baby Tee ($18) is right in line with 4 similar tops in the dataset (avg $21). Good value for excellent condition."` Always returns a string — never raises.

**What happens if it fails or returns nothing:**
If no comparable listings exist in the same category with overlapping style tags, returns `"Not enough comparable listings to estimate price fairness for this item."` No exception is raised. This is pure Python — no LLM call, no external dependency.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop runs the tools in a fixed conditional chain — each step only executes if the previous one succeeded. Here is the exact branching logic:

1. **Parse the query.** Extract `description`, `size`, and `max_price` from the user's natural language input using the LLM. Store the result in `session["parsed"]`. If parsing fails or `description` is missing, set `session["error"] = "Couldn't understand your request — please describe what you're looking for."` and return early.

2. **Call `search_listings(description, size, max_price)`.** Store the result in `session["search_results"]`.
   - If `session["search_results"]` is an empty list: set `session["error"]` to a message like `"No listings found for '[description]' in size [size] under $[max_price]. Try removing the size filter or raising your budget."` and return the session immediately. Do not proceed.
   - If `session["search_results"]` is non-empty: set `session["selected_item"] = session["search_results"][0]` (top-ranked result) and continue.

3. **Call `suggest_outfit(selected_item, wardrobe)`.** Store the result in `session["outfit_suggestion"]`.
   - If `session["outfit_suggestion"]` is an empty string: set `session["error"] = "Couldn't generate outfit suggestions — try again."` and return early.
   - If non-empty: continue.

4. **Call `create_fit_card(outfit_suggestion, selected_item)`.** Store the result in `session["fit_card"]`.
   - If `session["fit_card"]` is empty: set `session["error"] = "Couldn't generate a fit card."` and return early.
   - If non-empty: continue.

5. **Return the session.** `session["error"]` is `None`, and `session["fit_card"]`, `session["outfit_suggestion"]`, and `session["selected_item"]` are all populated. The caller checks `session["error"]` first to determine which fields are safe to use.


---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict created by `_new_session(query, wardrobe)` at the start of each run. No tool writes to the session directly — only `run_agent()` does. Here is what each key holds and when it gets written:

| Key | Type | Written after | Read by |
|-----|------|---------------|---------|
| `query` | str | initialization | query parser |
| `parsed` | dict (`description`, `size`, `max_price`) | query parsing | `search_listings` call |
| `search_results` | list[dict] | `search_listings` returns | planning loop (empty check) |
| `selected_item` | dict | top result picked from `search_results` | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | dict | initialization (passed in by caller) | `suggest_outfit` |
| `outfit_suggestion` | str | `suggest_outfit` returns | `create_fit_card`, final output |
| `fit_card` | str | `create_fit_card` returns | final output |
| `error` | str or None | any early-exit branch | caller checks this first |

The key handoffs are:
- `session["selected_item"]` bridges Steps 2→3 and 2→4 — the same listing dict flows into both `suggest_outfit` and `create_fit_card` without the user re-entering anything.
- `session["outfit_suggestion"]` bridges Steps 3→4 — the string returned by `suggest_outfit` is passed directly as the `outfit` argument to `create_fit_card`.
- `session["wardrobe"]` is set once at initialization and never mutated — `suggest_outfit` reads it but does not modify it.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session["error"]` to: "No listings found for '[description]'[, size [size]][, under $[max_price]]. Try one of these: remove the size filter, raise your budget, or use broader keywords (e.g. 'graphic tee' instead of 'vintage band tee')." Omit the size/price clause if that filter wasn't applied. Return the session immediately — do not call `suggest_outfit` or `create_fit_card`. |
| suggest_outfit | Wardrobe is empty | Do not error. Switch to a general-advice LLM prompt: "The user is considering buying [title] ([style_tags], [colors]). They haven't described their wardrobe yet. Suggest 2 complete outfits using common wardrobe staples that would pair well with this item's vibe." Return the LLM's response as-is — the user sees styling advice without any mention of their wardrobe. |
| create_fit_card | Outfit input is empty or whitespace-only | Skip the LLM call and return the literal string: "Couldn't write a fit card — no outfit suggestion was available. Try running the full flow again from the search step." No exception is raised. |

---

## Architecture

<!-- Draw a diagram of your agent showing how the components connect:
     User input → Planning Loop → Tools (search_listings, suggest_outfit, create_fit_card)
                                                                          ↕
                                                                   State / Session
     Show what triggers each tool, how state flows between them, and where error paths branch off.
     ASCII art, a Mermaid diagram (https://mermaid.js.org/syntax/flowchart.html), or an embedded
     sketch are all fine. You'll share this diagram with an AI tool when asking it to implement
     the planning loop and each individual tool. -->

```
User query + wardrobe
        |
        v
  ┌─────────────────────────────────────────────────────────────┐
  │                      Planning Loop                          │
  │                      (run_agent)                            │
  │                                                             │
  │  Step 1: Parse query ──► session["parsed"]                  │
  │            |                                                │
  │            | description missing?                           │
  │            ├──► [ERROR] session["error"] = "Couldn't        │
  │            |             understand..." ──────────────────► return session
  │            |                                                │
  │            v                                                │
  │  Step 2: search_listings(description, size, max_price)      │
  │            |         writes ──► session["search_results"]   │
  │            |                                                │
  │            | results == [] ?                                │
  │            ├──► [ERROR] session["error"] = "No listings     │
  │            |             found..." ───────────────────────► return session
  │            |                                                │
  │            | results non-empty                              │
  │            ├──► session["selected_item"] = results[0]       │
  │            |                                                │
  │            v                                                │
  │  Step 3: suggest_outfit(selected_item, wardrobe)            │
  │            |         writes ──► session["outfit_suggestion"] │
  │            |                                                │
  │            | wardrobe empty? ──► switch to general-advice   │
  │            |                    prompt (no error, continues)│
  │            |                                                │
  │            | outfit_suggestion == "" ?                      │
  │            ├──► [ERROR] session["error"] = "Couldn't        │
  │            |             generate suggestions..." ────────► return session
  │            |                                                │
  │            v                                                │
  │  Step 4: create_fit_card(outfit_suggestion, selected_item)  │
  │            |         writes ──► session["fit_card"]         │
  │            |                                                │
  │            | outfit arg empty? ──► return error string      │
  │            |                      (no LLM call, no crash)   │
  │            |                                                │
  │            v                                                │
  │         return session  (error=None, all fields populated)  │
  └─────────────────────────────────────────────────────────────┘
                    |               |               |
              session["selected_item"]  session["outfit_suggestion"]  session["fit_card"]
                    └───────────────┴───────────────┘
                           State / Session dict
                    (written by run_agent, read by each tool call)
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

*Tool 1 — `search_listings`:*
I'll give Claude the Tool 1 block from planning.md (what it does, all three input parameters with types and matching rules, what it returns, the empty-results failure mode) plus the `load_listings()` docstring from `utils/data_loader.py`. I'll ask it to implement the function body only — no changes to the signature. I expect it to produce: a call to `load_listings()`, a size filter that does case-insensitive substring matching (so "M" catches "S/M"), a price filter using `<=`, a keyword scorer that checks overlap with `title`, `description`, and `style_tags`, a step that drops zero-score listings, and a sort by score descending. Before trusting it I'll check: (1) the size filter handles "S/M" correctly, (2) `max_price=None` skips price filtering entirely, (3) it returns `[]` rather than raising when nothing matches. Then I'll run it against three queries: one that should return multiple results, one that returns nothing, and one with `size=None` and `max_price=None`.

*Tool 2 — `suggest_outfit`:*
I'll give Claude the Tool 2 block from planning.md (both input shapes, the empty-wardrobe fallback, the LLM exception fallback) plus the field names from `wardrobe_schema.json` so it knows what to reference in the prompt. I expect it to produce: an `if not wardrobe["items"]` branch that calls the LLM with a general-advice prompt, an `else` branch that formats each wardrobe item by name and style tags then asks for specific outfit combinations, and a `try/except` around the LLM call returning the fallback string on failure. Before trusting it I'll check: (1) the empty-wardrobe branch never returns `""`, (2) the wardrobe branch actually names wardrobe items in the prompt rather than dumping a raw dict, (3) exceptions are caught and don't propagate. Then I'll call it once with `get_example_wardrobe()` and once with `get_empty_wardrobe()`.

*Tool 3 — `create_fit_card`:*
I'll give Claude the Tool 3 block from planning.md (both input parameters, the caption style requirements, the guard against empty `outfit`). I expect it to produce: an upfront `if not outfit.strip(): return "..."` guard before any LLM call, a prompt that includes the item's title, price, and platform and instructs the LLM to mention each once, and a Groq call with `temperature=0.9` or higher. Before trusting it I'll check: (1) passing `outfit=""` returns the error string without making an LLM call, (2) the prompt explicitly instructs the LLM to mention name, price, and platform once each, (3) running it twice on the same inputs produces noticeably different captions.

**Milestone 4 — Planning loop and state management:**

I'll give Claude the Planning Loop section (all five numbered steps with their exact branches), the State Management table, the Architecture diagram, and the `_new_session()` and `run_agent()` stubs from `agent.py`. I'll ask it to implement `run_agent()` only — not change any signatures or add new functions. I expect it to produce: an LLM call to parse the query into `description`/`size`/`max_price` stored in `session["parsed"]`, each tool called in order with its result written to the correct session key, an early `return session` after each failure check, and `session["selected_item"] = session["search_results"][0]` as the handoff from Step 2 to Step 3. Before trusting it I'll check: (1) `session["error"]` is `None` on a successful run and all output keys are populated, (2) if `search_results` is empty the function returns before calling `suggest_outfit`, (3) `selected_item` is taken from index `[0]` of `search_results`. Then I'll run both CLI test cases at the bottom of `agent.py` — the happy path and the no-results path — and confirm every session key matches the State Management table.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

FitFindr takes a natural-language request from the user and orchestrates three tools in sequence: it first searches secondhand listings to find a matching item, then uses the found item and the user's wardrobe to suggest a complete outfit, and finally generates a shareable fit card caption from that outfit. If `search_listings` returns no results, the agent stops immediately and asks the user to adjust their query — it never calls `suggest_outfit` or `create_fit_card` with empty input. If the wardrobe is empty, `suggest_outfit` falls back to a generic styling suggestion rather than failing.

**Step 1:**
The LLM parses the query and extracts: `description="vintage graphic tee"`, `size=None` (no size mentioned), `max_price=30.0`. These are stored in `session["parsed"]`. The agent then calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`. It filters `listings.json` by price ≤ 30 (size filter is skipped because `size=None`), scores remaining listings by keyword overlap with "vintage graphic tee" across `title`, `description`, and `style_tags`, drops zero-score listings, and returns results sorted by score. If the list is empty, the agent sets `session["error"]` and returns immediately — `suggest_outfit` is never called.

**Step 2:**
`search_listings` returned two matches; the agent picks the top result — e.g. `lst_002` ("Y2K Baby Tee — Butterfly Print", $18, depop, size S/M). The agent calls `suggest_outfit(new_item=lst_002, wardrobe=<example_wardrobe>)`. It reads the new item's `style_tags` (["y2k", "vintage", "graphic tee"]) and `colors` (["white", "pink", "purple"]), then finds complementary wardrobe items by matching style tags and color palettes — returning one or more complete outfit combinations (e.g. "Pair with baggy dark-wash jeans, chunky white sneakers, and the black crossbody bag").

**Step 3:**
The agent calls `create_fit_card(outfit=<suggestion from step 2>, new_item=lst_002)`. It generates a short, casual, Instagram-caption-style description of the full look — e.g. "thrifted this y2k butterfly tee for $18 off depop and it goes with literally everything in my closet 🦋 wide-legs + chunky sneaks = done." The output is intentionally varied each time based on the specific item and outfit details.

**Final output to user:**
The user sees all three results surfaced together: the listing details (title, price, platform, condition), the outfit suggestion with specific wardrobe pairings and styling notes, and the fit card caption ready to copy. If any step failed, the user sees a plain-language explanation of what went wrong and what to try instead.

## Implementation testing

Commands used to test Tool 1 - search_listing():

  # Test 1: multiple results, no filters
  python -c "from tools import search_listings; results = 
  search_listings('vintage graphic tee'); print([(r['id'], r['title'], 
  # Test 1: multiple results, no filters
  python -c "from tools import search_listings; results =
  search_listings('vintage graphic tee'); print([(r['id'], r['title'],
  r['price']) for r in results])"

  # Test 2: no results (impossible query)

  # Test 2: no results (impossible query)
  print(search_listings('designer ballgown', size='XXS', max_price=5.0))"

  # Test 3: size filter — 'M' should match 'S/M'
  python -c "from tools import search_listings; results =
  search_listings('tee', size='M'); print([(r['id'], r['title'], r['size'])
  for r in results])"

  # Test 4: price ceiling — nothing over $30
  python -c "from tools import search_listings; results =
  search_listings('vintage', max_price=30.0); print(all(r['price'] <= 30 for
   r in results), [r['price'] for r in results])"

Commands used to test Tool 2 - suggest_outfit():

  # Test 1: with example wardrobe — should name specific wardrobe pieces
  python -c "
  from tools import suggest_outfit, search_listings
  from utils.data_loader import get_example_wardrobe
  item = search_listings('vintage graphic tee', max_price=30.0)[0]
  print('Item:', item['title']) 
  print(suggest_outfit(item, get_example_wardrobe()))
  "
  
  # Test 2: empty wardrobe — should give general advice, not crash or return '' 
  python -c "
  from tools import suggest_outfit, search_listings
  from utils.data_loader import get_empty_wardrobe
  item = search_listings('vintage graphic tee', max_price=30.0)[0]
  result = suggest_outfit(item, get_empty_wardrobe())
  print('Non-empty?', bool(result))
  print(result)
  "
  
  # Test 3: LLM exception fallback — pass a bad API key to force failure
  python -c "
  import os; os.environ['GROQ_API_KEY'] = 'bad-key'
  from tools import suggest_outfit, search_listings
  from utils.data_loader import get_example_wardrobe
  item = search_listings('flannel', max_price=50.0)[0]
  result = suggest_outfit(item, get_example_wardrobe())
  print('Fallback returned?', 'color palette' in result)
  print(result)
  "

Commands used to test Tool 3 - create_fit_card(): 

  # Check 1: empty outfit guard — should return error string, no 
  LLM call
  python -c "
  from tools import create_fit_card, search_listings
  item = search_listings('vintage graphic tee', max_price=30.0)[0]
  print(create_fit_card('', item))
  "

  # Check 2: prompt includes name, price, platform — verify they 
  appear in output
  python -c "
  from tools import create_fit_card, suggest_outfit, 
  search_listings
  from tools import create_fit_card, suggest_outfit, search_listings
  from utils.data_loader import get_example_wardrobe
  item = search_listings('vintage graphic tee', max_price=30.0)[0]
  outfit = suggest_outfit(item, get_example_wardrobe())
  result = create_fit_card(outfit, item)
  print('Has title?   ', item['title'] in result)
  print('Has price?   ', str(item['price']) in result)
  print('Has platform?', item['platform'] in result)
  print()
  print(result)
  "

  # Check 3: same input, three runs — verify outputs differ
  python -c "
  from tools import create_fit_card, suggest_outfit, search_listings
  from utils.data_loader import get_example_wardrobe
  item = search_listings('vintage graphic tee', max_price=30.0)[0]
  outfit = suggest_outfit(item, get_example_wardrobe())
  runs = [create_fit_card(outfit, item) for _ in range(3)]
  for i, r in enumerate(runs, 1):
      print(f'Run {i}:', r)
      print()
  print('All different?', len(set(runs)) == 3)
  "