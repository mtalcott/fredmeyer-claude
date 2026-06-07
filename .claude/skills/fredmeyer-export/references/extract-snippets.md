# Fred Meyer extract snippets

JavaScript and Python snippets used by the `fredmeyer-export` skill. Pass the JS to `chrome-devtools:evaluate_script` after navigating; the page is React/Next.js, so allow it to hydrate first.

## Page structure (discovered 2026-04-04)

- Order list page: `/mypurchases?page=N&tab=purchases`
  - Order links: `a[href*="/mypurchases/detail/"]` with text like `In-store March 22, 2026 $65.71`
- Order detail page: `/mypurchases/detail/{div}~{store}~{date}~{terminal}~{txnId}`
  - Items live in `aside[role="complementary"]` whose `h2` reads "Pickup Items" or "In-Store Items"
  - Each `li > a[href*="/p/"]` is an item; fee lines (Bev Excise, etc.) lack a `/p/` link and are skipped naturally
- Product URL format: `/p/{slug}/{upc13}` — the last segment is the 13-digit UPC

---

## Snippet 1 — Login check

Run after navigating to fredmeyer.com:

```javascript
() => document.body.innerText.includes('Sign In') ? 'signed-out' : 'signed-in'
```

## Snippet 2 — Order-list extractor

Run after navigating to `/mypurchases?page=N&tab=purchases` (wait ~1 second for React render). Returns `[{id, date, type, url}]` for every order on the page.

```javascript
() => {
  const orders = [];
  document.querySelectorAll('a[href*="/mypurchases/detail/"]').forEach(a => {
    const id = a.getAttribute('href').split('/detail/')[1];
    const text = a.innerText;
    const typeMatch = text.match(/^(In-store|Pickup)/i);
    const dateMatch = text.match(/(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d+),\s+(\d{4})/);
    if (!id || !dateMatch) return;
    const months = {January:'01',February:'02',March:'03',April:'04',May:'05',June:'06',
      July:'07',August:'08',September:'09',October:'10',November:'11',December:'12'};
    const date = `${dateMatch[3]}-${months[dateMatch[1]]}-${dateMatch[2].padStart(2,'0')}`;
    const type = typeMatch ? typeMatch[1].toLowerCase().replace('-','') : 'in-store';
    orders.push({ id, date, type, url: 'https://www.fredmeyer.com' + a.getAttribute('href') });
  });
  return orders;
}
```

## Snippet 3 — Item extractor (writes to localStorage)

Run after navigating to `/mypurchases/detail/{ID}`. Substitute `DATE`, `TYPE`, and `ID` with the order's values before sending. Returns the row count only — actual rows stay in `localStorage` to keep context small.

```javascript
async () => {
  const DATE = '2026-XX-XX';                  // e.g. '2026-03-22'
  const TYPE = 'in-store';                    // 'in-store' or 'pickup'
  const ID   = 'DIV~STORE~DATE~TERM~TXN';     // full order ID

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

  const rows = [];
  aside.querySelectorAll('li').forEach(li => {
    const link = li.querySelector('a[href*="/p/"]');
    if (!link) return;  // fee lines have no /p/ link
    const name = li.querySelector('h3')?.innerText?.trim() || '';
    const href = link.getAttribute('href');
    const upc  = href.split('/').pop();
    const url  = 'https://www.fredmeyer.com' + href;
    const text = li.innerText;
    const qty  = text.match(/Received:\s*([\d.]+ lbs|[\d.]+)/)?.[1] || '';
    const paid = '$' + (text.match(/Paid:\s*\$([\d.]+)/)?.[1] || '');

    // Size: first non-label text node after h3's parent
    const h3 = li.querySelector('h3');
    let size = '';
    if (h3) {
      let node = h3.parentElement?.nextSibling;
      while (node) {
        const t = (node.textContent || '').trim();
        if (t && !/^(Add to Cart|Delivery Only|Item|Received|Paid|Save|Buy|Coupon|Featured|Everyday|Price Cut|Discounted|Low Stock|Out of)/i.test(t)) {
          size = t; break;
        }
        node = node.nextSibling;
      }
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

```python
import csv, io, glob

all_rows = []
for path in glob.glob('.tmp/fm-order-*.csv'):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                all_rows.extend(csv.reader([line]))

# Sort: date descending, then item_name ascending
all_rows.sort(key=lambda r: (-int(r[0].replace('-', '')), r[2]))

header = ['date','order_type','item_name','size','quantity','price_paid','product_url','upc']
out = io.StringIO()
w = csv.writer(out, quoting=csv.QUOTE_MINIMAL)
w.writerow(header)
w.writerows(all_rows)

with open('fred-meyer-purchases.csv', 'w') as f:
    f.write(out.getvalue())

print(f'{len(all_rows)} rows written')
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
