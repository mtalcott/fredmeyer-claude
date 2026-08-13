# Fred Meyer extract snippets

JavaScript and Python snippets used by the `fredmeyer-export` skill. Pass the JS to `chrome-devtools:evaluate_script` after navigating; the page is React/Next.js, so allow it to hydrate first.

## Page structure (updated 2026-06-14)

- Order list page: `/mypurchases?page=N&tab=purchases`
  - Order links: `a[href*="/mypurchases/detail/"]`. Only the first (hydrated) anchor reliably has text like `Pickup June 7, 2026 $208.13`; the rest render with empty `innerText`. **Parse the date from the order ID itself** (3rd `~`-delimited field, format `DIV~STORE~DATE~TERM~TXN`) rather than from anchor text. Multiple anchors point to the same order — dedupe by ID.
- Order detail page: `/mypurchases/detail/{div}~{store}~{date}~{terminal}~{txnId}`
  - Items live in `aside[role="complementary"]` whose `h2` now reads just "Items" (no longer "Pickup Items"/"In-Store Items").
  - Order type comes from the page heading `"{Pickup|In-Store|Delivery} Order Details"`, not the aside `h2`.
  - Each `li > a[href*="/p/"]` is an item; fee lines (Bev Excise, etc.) lack a `/p/` link and are skipped naturally.
  - Inside each `li` the lines run: name (`h3`), a `SNAP EBT` badge, then the **size** (e.g. `36 oz`), then price. Extract size by matching a size/unit pattern on the `li`'s text lines (the old "first non-label sibling" walk grabs the `SNAP EBT` badge instead).
  - **Both pickup and in-store orders list items** (in-store heading reads "In-Store Order Details"). The extractor auto-detects type from the heading, so the same snippet handles both. Caveat: some in-store receipts are **non-itemized** — the page renders only "Purchase Details" (no items section), and the extractor correctly returns 0 for those. In-store product links also carry a `?fulfillment=` query suffix, so strip it before taking the UPC.
- Product URL format: `/p/{slug}/{upc13}` — the last segment is the 13-digit UPC

---

## Snippet 1 — Login check

Run after navigating to fredmeyer.com:

```javascript
() => document.body.innerText.includes('Sign In') ? 'signed-out' : 'signed-in'
```

## Snippet 2 — Order-list extractor

Run after navigating to `/mypurchases?page=N&tab=purchases` (wait ~1 second for React render). Returns `[{id, date, type, url}]` for every order on the page. The date is parsed from the order ID (field 3) because anchor text is unreliable; `type` comes from anchor text when present (only the hydrated first anchor has it) and is otherwise `''` — the item extractor (snippet 3) detects the real type from the detail-page heading.

```javascript
() => {
  const seen = new Set();
  const orders = [];
  document.querySelectorAll('a[href*="/mypurchases/detail/"]').forEach(a => {
    const id = a.getAttribute('href').split('/detail/')[1];
    if (!id || seen.has(id)) return;
    seen.add(id);
    const date = (id.split('~')[2]) || '';            // DIV~STORE~DATE~TERM~TXN
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
    const typeMatch = (a.innerText || '').match(/(In-?store|Pickup|Delivery)/i);
    const type = typeMatch ? typeMatch[1].toLowerCase().replace('-','') : '';
    orders.push({ id, date, type, url: 'https://www.fredmeyer.com' + a.getAttribute('href') });
  });
  return orders;
}
```

## Snippet 3 — Item extractor (writes to localStorage)

Run after navigating to `/mypurchases/detail/{ID}`. Substitute `DATE` and `ID` with the order's values before sending; order **type is auto-detected** from the detail-page heading. Returns the row count only — actual rows stay in `localStorage` to keep context small.

```javascript
async () => {
  const DATE = '2026-XX-XX';                  // e.g. '2026-03-22'
  const ID   = 'DIV~STORE~DATE~TERM~TXN';     // full order ID

  // Type from the "{Pickup|In-Store|Delivery} Order Details" heading
  let TYPE = 'in-store';
  const th = [...document.querySelectorAll('h1,h2,h3')]
    .map(h => h.innerText || '').find(t => /Order Details/i.test(t));
  const tm = th && th.match(/(Pickup|In-?store|Delivery)/i);
  if (tm) TYPE = tm[1].toLowerCase().replace('-', '');

  let aside = null;
  for (let i = 0; i < 10; i++) {
    aside = [...document.querySelectorAll('aside,[role="complementary"]')]
      .find(a => {
        const h = a.querySelector('h2')?.innerText || '';
        return h.includes('Items') && !h.includes('Out of Stock');
      });
    if (aside && aside.querySelectorAll('li').length > 0) break;
    await new Promise(r => setTimeout(r, 500));
  }
  if (!aside) { localStorage.setItem('fm_' + ID, ''); return 0; }

  const esc = s => {
    s = String(s);
    return (s.includes(',') || s.includes('"')) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };

  // Size sits on its own line inside the li (after the SNAP EBT badge), e.g. "36 oz", "2 lb", "30 Count"
  const SIZE_RE = /^[\d.]+\s?(fl\s?oz|oz|lbs|lb|ct|count|pk|pack|gallon|gal|kg|g|ml|liter|l|each|ea|qt|pt|dozen)\b/i;

  const rows = [];
  aside.querySelectorAll('li').forEach(li => {
    const link = li.querySelector('a[href*="/p/"]');
    if (!link) return;  // fee lines have no /p/ link
    const name = li.querySelector('h3')?.innerText?.trim() || '';
    const href = link.getAttribute('href').split('?')[0];  // in-store links carry ?fulfillment=
    const upc  = href.split('/').pop();
    const url  = 'https://www.fredmeyer.com' + href;
    const text = li.innerText;
    const qty  = text.match(/Received:\s*([\d.]+ lbs|[\d.]+)/)?.[1] || '';
    const paid = '$' + (text.match(/Paid:\s*\$([\d.]+)/)?.[1] || '');

    let size = '';
    for (const line of text.split('\n').map(s => s.trim())) {
      if (SIZE_RE.test(line)) { size = line; break; }
    }
    rows.push([DATE, TYPE, name, size, qty, paid, url, upc].map(esc).join(','));
  });

  localStorage.setItem('fm_' + ID, rows.join('\n'));
  return rows.length;
}
```

## Snippet 4 — Read back localStorage

Run once after every order has been processed. Returns `{ orderId: "csv_rows_string" }` and clears the keys.

```javascript
() => {
  const keys = Object.keys(localStorage).filter(k => k.startsWith('fm_'));
  const result = {};
  keys.forEach(k => { result[k.slice(3)] = localStorage.getItem(k); });
  keys.forEach(k => localStorage.removeItem(k));
  return result;
}
```

## Snippet 5 — Python merge + sort

Run after writing all `.tmp/fm-order-*.csv` files. Use Python (not bash `sort`) so quoted CSV fields are handled correctly.

**This merge is cumulative — it never overwrites prior history.** It loads the
existing `fred-meyer-purchases.csv` first, then layers the freshly-crawled temp
rows on top, deduping by `(date, upc, item_name)` so a re-crawled order replaces
its old rows (e.g. with improved size data) instead of duplicating them. The
output is the union of all orders ever exported, re-sorted. `fredmeyer-shop`
depends on this full history for cadence analysis, so the per-run incremental
export must accumulate rather than replace.

```python
import csv, io, glob, os

OUTPUT = 'fred-meyer-purchases.csv'
header = ['date','order_type','item_name','size','quantity','price_paid','product_url','upc']

# Dedup key: same item, same order date. Later assignment wins, so process the
# existing CSV first and let the freshly-crawled temp rows overwrite.
merged = {}
def key(r):
    return (r[0], r[7] if len(r) > 7 else '', r[2])

# 1. Existing history (skip header if present)
if os.path.exists(OUTPUT):
    with open(OUTPUT) as f:
        for i, row in enumerate(csv.reader(f)):
            if i == 0 and row[:1] == ['date']:
                continue
            if row:
                merged[key(row)] = row

# 2. Newly-crawled temp rows (win on conflict)
for path in glob.glob('.tmp/fm-order-*.csv'):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            for row in csv.reader([line]):
                merged[key(row)] = row

all_rows = list(merged.values())
# Sort: date descending, then item_name ascending
all_rows.sort(key=lambda r: (-int(r[0].replace('-', '')), r[2]))

out = io.StringIO()
w = csv.writer(out, quoting=csv.QUOTE_MINIMAL)
w.writerow(header)
w.writerows(all_rows)

with open(OUTPUT, 'w') as f:
    f.write(out.getvalue())

print(f'{len(all_rows)} rows written (cumulative)')
```

## Snippet 6 — Purchase-history API (rate-limited)

Alternative to DOM extraction. Returns clean JSON per order, but Akamai rate-limits direct fetches after ~5 calls. Use only when the order count is small. Requires active fredmeyer.com cookies.

```javascript
async () => {
  // Substitute the actual order ID from Phase 1
  const [divisionNumber, storeNumber, transactionDate, terminalNumber, transactionId] =
    'DIV~STORE~DATE~TERM~TXN'.split('~');

  const resp = await fetch('/atlas/v1/purchase-history/v2/details', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'content-type': 'application/json',
      'accept': 'application/json, text/plain, */*',
      'x-kroger-channel': 'WEB'
    },
    body: JSON.stringify([{ divisionNumber, storeNumber, transactionDate, terminalNumber, transactionId }])
  });
  return await resp.json();
  // Response shape: data.purchaseHistoryDetails[0].items[].purchasedData
  //   .displayInfo.description, .customerFacingSize
  //   .pricingInfo.totalPricePaid
  //   .quantityInfo.received
  //   .isWeighted
  //   .upc
}
```
