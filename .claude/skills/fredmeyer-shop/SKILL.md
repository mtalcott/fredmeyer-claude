---
name: fredmeyer-shop
description: Reviews Fred Meyer purchase history, builds a shopping list of staples and infrequently-bought items, confirms quantities with the user, and adds the order to the cart via the chrome-devtools MCP. Use when the user wants help building, refreshing, or submitting a Fred Meyer grocery order, asks what to buy this week from Fred Meyer, or wants to check whether household items are running low.
---

# Fred Meyer Shopping Assistant

Build a grocery order from purchase history, confirm it interactively with the user, and add it to the Fred Meyer cart via the cart API.

## Prerequisites

- `fred-meyer-purchases.csv` exists in the project directory. If not, ask the user to run the `fredmeyer-export` skill first.
- Chrome is launched with remote debugging and the user is signed in to fredmeyer.com.
- The `chrome-devtools` MCP server is configured.
- For the optional Google Keep merge (Phase 1d), the same Chrome should be signed in to the user's Google account. If it isn't, the skill skips Keep and builds the order from purchase history only.

## References

Read these once before starting:

- `../_shared/chrome-devtools-tips.md` — patterns this skill depends on (`chrome-devtools:evaluate_script` over `take_snapshot`, React render waits).
- `references/keep-snippets.md` — JS snippets for reading the user's Google Keep grocery note, the store-section rules, and quantity parsing.
- `references/cart-snippets.md` — JS snippets for cart-API discovery, replace-cart fetch, product status, DOM add-to-cart, and cart verification.
- `references/categories.md` — keyword tables used to classify items.
- `references/output-format.md` — exact templates for the suggested-list and final-order prompts.
- `scripts/stats.py` — run in Phase 1b to compute per-item recency/cadence/due-score (no need to read it; just run it).

---

## Phase 1: Analyze purchase history

### 1a. Read the CSV

Read `fred-meyer-purchases.csv`. Parse each row into:
`date, order_type, item_name, size, quantity, price_paid, product_url, upc`.

### 1b. Compute per-item statistics

Run the stats helper rather than computing by hand — it does the arithmetic over
all ~280 items deterministically and reproducibly:

```
python3 .claude/skills/fredmeyer-shop/scripts/stats.py --today <YYYY-MM-DD>
```

Use today's date for `--today` (omit to default to the system date). Add `--json`
for structured output. The script groups rows by `upc` (falling back to
`item_name` when upc is `unknown`), counts distinct order dates as `total_orders`,
and emits per item:

| Field | Meaning |
|------|------------|
| `purchase_count` | distinct orders the item appears in |
| `participation_pct` | `purchase_count / total_orders × 100` |
| `last_purchased`, `days_since_last` | recency |
| `median_interval` | **median** of consecutive purchase intervals (only when `purchase_count ≥ 3`). Median, not mean — so one adoption/abandonment gap doesn't distort the cadence. |
| `interval_cv` / `erratic` | interval variability; `erratic` flags an unreliable cadence (CV > 0.6) |
| `due_ratio` | `days_since_last / median_interval` — how far into its cycle the item is (only when `purchase_count ≥ 3`) |
| `state` | `recent` (due_ratio < 0.5), `due`, `OVERDUE` (> 1.3), or `insufficient` (< 3 purchases) |
| `typical_qty` | mode of historical quantity (raw — preference caps are applied later, see "Standing preferences") |
| `weight_based` | item is sold by weight (qty is a weight, e.g. bananas) |

`category` (per `references/categories.md`) and `replacement_for` (per 1c) are not
in the script output — infer those yourself from `item_name`.

**How to read the signals — this is the prediction logic that replaces the old
single-threshold rule:**

- **`due` / `OVERDUE` with a moderate ratio (~1–3):** at or just past its usual
  cadence — include by default.
- **Very high `due_ratio` (≳ 3–4):** the item is likely **abandoned**, not merely
  due (bought regularly for a while, then nothing for many cycles — `days_since_last`
  dwarfs the cadence). Do **not** auto-include these; surface them opt-in
  ("haven't bought this in a while — still want it?"). This is the abandoned-staple
  trap the old `avg_interval ≤ 17d` gate fell into.
- **`recent`:** bought within half a cycle — suppress; don't re-suggest something
  just purchased.
- **`erratic`:** noisy cadence — offer opt-in rather than auto-include, even if `due`.
- **`insufficient` (< 3 purchases — ~73% of items):** no reliable cadence. Don't
  fabricate one. Treat as infrequent/opt-in ordered by recency, and lean on the
  Google Keep list (1d) and the user's own additions for intent.
- **`weight_based`:** `typical_qty` is a count of units (bunches/each), not a
  weight — relevant to quantity caps (e.g. bananas).

There is **no hard staple/infrequent threshold** anymore. Present items with their
evidence and let due-state plus standing preferences drive inclusion.

### 1c. Replacement detection

Identify likely substitutions so the same logical item under different brands isn't double-counted:

1. For any two item groups whose `item_name` values share ≥ 2 significant words (ignoring brand, size, and filler like "organic", "oz", "fl", "pack"), flag them as related.
2. Among related pairs, the item with fewer purchases is likely a replacement for the one with more. Set its `replacement_for` to the more-frequent item's UPC.
3. When reading `participation_pct` for the more-frequent item, also count orders where its replacement appeared. Annotate with `(incl. substitutions)` if replacements were found.

### 1d. Merge the Google Keep grocery list

Read `references/keep-snippets.md` before starting this step. Pull the user's
Keep grocery note and merge its Fred Meyer items in as additional candidate lines.

1. Navigate to `https://keep.google.com` and run snippet 1 (login check). If
   `signed-out`, ask the user to sign in and wait; if they decline, skip 1d.
2. Run snippet 2 to find and open the grocery note by title (default `"Groceries"`
   — ask the user once if it isn't found). Run snippet 3 to get the **unchecked**
   rows with their nesting levels.
3. Apply the **store-section rules** in `references/keep-snippets.md`: keep only
   items in the Fred Meyer section (the flat items at the top plus anything under a
   `Fred Meyer` header); exclude any other store header and its sub/inline items.
   If the boundary is ambiguous, list the top-level rows and ask the user.
4. If snippet 2 or 3 returns nothing, use the paste fallback (snippet 4).
5. Parse a quantity from each kept item (default 1) per the parsing rules.
6. Resolve each item against the CSV using the **same significant-word matching as
   1c** (≥ 2 shared significant words, ignoring brand/size/filler). A confident
   match inherits that product's real `upc`, `product_url`, `item_name`, and
   `size`. Items with no CSV match keep only their freeform text and parsed qty —
   they have **no UPC** and are routed to the Phase 4d search path.
7. Tag every Keep-sourced line `source: keep` so Phase 2 can annotate it.

**Never fabricate a UPC.** A cart line is only valid with a real `gtin13` from the
CSV or from a Phase 4d search result. An item that resolves to neither is reported
as unresolved in Phase 5 — it is never guessed into the cart.

### Standing preferences (applied at this layer, by judgment)

Standing user preferences — quantity caps (e.g. bananas ≤ 2 bunches), brand
switches (prefer the cheaper brand and suppress the old one), and the like — live
in user memory and apply automatically during resolution and quantity reasoning.
Do not hard-code them here.

**Precedence when signals conflict:** standing preference > your judgment > the
deterministic `due_ratio`/stats. A preference always wins over the script's
numbers — a qty cap overrides `typical_qty`; a brand switch suppresses the old
UPC even when it shows `OVERDUE`.

**Do not persist one-off edits.** Removing an item or changing a quantity for a
single run is *not* a standing preference — never write it to memory. Persist a
new preference only when the user signals it should stick ("always", "from now
on", "remember", "we've switched"). One-off removals stay one-off, so the
assistant never silently suppresses something the user still wants.

---

## Phase 2: Build the suggested shopping list

Render the suggested list using the template in `references/output-format.md`,
grouped by category, in a single prompt. Inclusion follows the 1b due-state, not a
frequency threshold:

- **Included by default (✓):** items that are `due`/`OVERDUE` with a moderate
  ratio and not `erratic` — the reliable, at-cadence buys.
- **Opt-in (·):** `insufficient`-data items, `erratic` items, and likely-abandoned
  ones (very high `due_ratio`). `recent` items are suppressed (omitted unless the
  user asks).

Every suggested line carries a one-line reason built from the real numbers (see
`references/output-format.md`) so the user can see *why* it's there.

Keep-sourced items (from 1d) appear in the list annotated `[from Keep]`, included
by default (✓), and show the matched **product name + size** so the user can catch
a wrong-brand or wrong-size match. If a Keep item is already present as a staple,
merge them (the Keep qty wins) rather than listing it twice. Keep items resolve
through the normal edit/remove grammar and the Phase 3 gate before anything is
added — never auto-add a Keep item silently.

Category display order (omit any with no items):
Protein → Dairy/Alternatives → Fruit → Vegetables → Bread/Grains → Beverages → Snacks/Sweets → Condiments/Pantry → Frozen → Personal Care → Medications/Supplements → Cleaning Supplies → Paper/Household → Baby/Child → Pet → Other.

Wait for user input. Apply changes (qty edits, removals, infrequent additions). When the user accepts ("ok") or has no further changes, move to Phase 3.

---

## Phase 3: Final confirmation

Show the complete final order using the FINAL ORDER template in `references/output-format.md`. Then ask:

> Ready to add these to your cart? (yes / no / [further changes])

If "no" or further changes, return to Phase 2. If "yes", proceed.

---

## Phase 4: Add items to cart

Read `references/cart-snippets.md` before starting. Use `chrome-devtools:evaluate_script` for everything in this phase — never `chrome-devtools:take_snapshot`. Snapshots cost ~800 tokens each; small JS payloads cost ~20.

### 4a. Verify fulfillment mode

Run snippet 1 (fulfillment-mode check) from `references/cart-snippets.md`. If the mode is "Delivery" or unset, ask the user to set their preferred pickup store before proceeding.

### 4b. Discover the cart API

The cart ID is session-specific — discover it fresh each run.

1. Navigate to the first item's `product_url`.
2. Run snippet 2 (product status). If `outOfStock` or `deliveryOnly`, record the item as unavailable and move to the next one.
3. Run snippet 3 (set quantity + click Add to Cart) to add the item via the DOM.
4. Capture the cart endpoint:
   - Run snippet 4 (recent network resources) to list candidate `/api/`, `/atlas/`, or `/cart` requests.
   - Use `chrome-devtools:list_network_requests` to inspect POSTs that fired after the click. Save the URL, headers, and body shape as `cart_api`.

### 4c. Add items category by category (preserves preview order)

The cart should display items in the **same category order the user previewed** in Phase 2/3 (Protein → Dairy/Alternatives → Fruit → … → Other). To achieve this, add items **one category at a time, in that display order**, rather than in one undifferentiated batch.

With `cart_api` known:

1. Group the final order's items by `category` and order the groups by the Phase 2 category display order. Within each category, keep the Phase 2 row order.
2. Add the categories **sequentially**, one cart call per category (snippet 5 in `references/cart-snippets.md`), waiting for each to return before starting the next so the categories get distinct, increasing add-times. Snippet 5 takes the **cumulative** ordered item list (all categories added so far, in order) so the cart array stays sorted regardless of whether Fred Meyer renders the cart by array order or by add-time.
3. Items go in as `{upc, qty}` pairs. Every `upc` must be a real `gtin13` from the CSV or a Phase 4d search result — never a guessed value.

**Iteration direction — confirm once per environment in 4e:** if the cart shows the **most recently added item at the top**, iterate categories in **reverse** display order (add Other first, Protein last) so the first display category ends up on top; if it shows newest at the **bottom**, iterate in forward display order. Default to forward; if 4e shows the order inverted, re-run with the categories reversed.

If the cart API cannot be discovered (no clear POST captured), fall back to per-item navigate + DOM add (snippets 2 + 3), still visiting items grouped by category in the same order — still no snapshots.

### 4d. Items without a `product_url`

Navigate to `https://www.fredmeyer.com/search?query={url-encoded-item-name}`. Run snippet 6 (first product link from search results), then continue with snippets 2 + 3.

Keep-sourced items (from 1d) that had no CSV match arrive here with only a name —
resolve them through this same search path to obtain a real `product_url` and UPC.
If search finds no product, report the item as unresolved in Phase 5; never add it
with a guessed UPC.

### 4e. Verify the cart

Run snippet 7 (cart count, no navigation) or navigate to `https://www.fredmeyer.com/cart` and run snippet 8 (cart item names) to confirm.

---

## Phase 5: Report

If every item went in:

> All N items added — your cart is ready at https://www.fredmeyer.com/cart

Otherwise:

```
Your Fred Meyer cart is ready for review!
→ https://www.fredmeyer.com/cart

Added: N items
Could not add (M items):
  - {item}: out of stock for pickup
  - {item}: product page not found
```
