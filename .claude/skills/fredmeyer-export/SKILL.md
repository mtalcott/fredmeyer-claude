---
name: fredmeyer-export
description: Crawls Fred Meyer purchase history via the chrome-devtools MCP and exports the last 3 months of items to a CSV with dates, product URLs, and UPC codes. Use when the user wants to export, archive, or analyze their Fred Meyer order history, or as a prerequisite for building a shopping list with the fredmeyer-shop skill.
---

# Fred Meyer Purchase History Export

Crawl the last 3 months of purchase history on fredmeyer.com and write all items to `fred-meyer-purchases.csv`.

## Prerequisites

- Chrome launched with remote debugging (see project README).
- The `chrome-devtools` MCP server configured.
- The user signed in to fredmeyer.com.

Read `../_shared/chrome-devtools-tips.md` once before starting — it covers the patterns this skill depends on (`evaluate_script` over `take_snapshot`, React render waits, localStorage accumulation).

The reusable JS and Python snippets — order-list extractor, item extractor, localStorage read-back, the API alternative, the merge step — live in `references/extract-snippets.md`. Read that file before Phase 1 so the snippets are in context when the loop starts.

## Architecture

Run in four phases:

0. **Skip phase**: Load `fred-meyer-processed-orders.txt` to build the set of already-processed order IDs.
1. **Crawl phase**: Verify login, paginate the order list, collect order detail URLs that fall within the 3-month window and aren't already processed.
2. **Extraction phase**: Visit each order detail page, extract items via `chrome-devtools:evaluate_script`, accumulate rows into `localStorage`.
3. **Merge phase**: Read all `localStorage` data back in one call, write temp CSVs, sort, write final output, record processed IDs.

---

## Phase 0: Load processed order history

Read `fred-meyer-processed-orders.txt` (one order ID per line, format `DIV~STORE~DATE~TERM~TXN`). Treat a missing or empty file as an empty set — every in-window order will be fetched.

---

## Phase 1: Crawl

### Step 1 — Check login

Navigate to `https://www.fredmeyer.com/mypurchases`. Run snippet 1 (login check) from `references/extract-snippets.md`. If signed out, ask the user to sign in and wait.

### Step 2 — Compute the cutoff date

```bash
date -d "3 months ago" +%Y-%m-%d
```

Only collect orders on or after this date.

### Step 3 — Collect order URLs

Paginate through `https://www.fredmeyer.com/mypurchases?page={N}&tab=purchases`. For each page, run the order-list extractor (snippet 2 in `references/extract-snippets.md`) via `chrome-devtools:evaluate_script`. Wait ~1 second after navigation before running.

For each returned order:
- If date < cutoff: stop paginating.
- If order ID is in `already_processed`: skip.
- Otherwise: record `{ url, date, type, id }`.

If no orders appear on a page that should have orders, retry up to 5 times — React hydration can lag.

---

## Phase 2: Sequential extraction with localStorage accumulation

### Step 4 — Process each order

For each order URL:

1. Navigate to the detail page with `chrome-devtools:navigate_page`.
2. Run the item extractor (snippet 3 in `references/extract-snippets.md`), substituting `DATE` and `ID` with the order's values (order type is auto-detected from the detail-page heading).

The extractor writes CSV rows to `localStorage['fm_' + ID]` and returns the row count only — item data stays out of context. Items without `/p/` links (fee lines like "Bev Excise") are skipped automatically.

### Step 5 — Read back all localStorage data

Run the read-back snippet (snippet 4 in `references/extract-snippets.md`). It returns `{ orderId: "csv_rows" }` for every accumulated key and clears them.

Write each order's rows to `.tmp/fm-order-{ID}.csv` (the project-local temp dir; create it with `mkdir -p .tmp` first). It's gitignored — keeping temp files in-project means a single Write/Bash approval covers the whole run instead of one per `/tmp` write.

---

## Phase 3: Merge and sort

### Step 6 — Merge and sort with Python

Run the merge script (snippet 5 in `references/extract-snippets.md`). Python (not bash `sort`) handles CSV-quoted fields correctly. The script is **cumulative**: it loads the existing `fred-meyer-purchases.csv`, layers the freshly-crawled temp rows on top (deduping by `(date, upc, item_name)` so a re-crawl replaces rather than duplicates), then sorts by date descending and item name ascending and writes the full history back with the header row. It never discards previously-exported orders — `fredmeyer-shop` relies on the complete 3-month history for cadence analysis.

### Step 7 — Record processed order IDs

Append the newly processed order IDs to `fred-meyer-processed-orders.txt`, one per line.

### Step 8 — Clean up and report

Remove the temp files (`rm -f .tmp/fm-order-*.csv`) and summarize:

- Date range covered (oldest → newest)
- Number of new orders processed (and how many were skipped as already-processed)
- Number of unique UPCs (across the full cumulative CSV)
- Total rows in `fred-meyer-purchases.csv` (cumulative), and how many were newly added this run
- Output path: `fred-meyer-purchases.csv`

---

## Notes

- The purchase-history JSON API (`POST /atlas/v1/purchase-history/v2/details`) returns clean data, but Akamai rate-limits direct fetches after ~5 calls. DOM extraction is more reliable for a full crawl. Snippet 6 documents the API for cases where ~5 orders is sufficient.
- localStorage survives navigation within the same origin, so accumulation across order pages works correctly.
