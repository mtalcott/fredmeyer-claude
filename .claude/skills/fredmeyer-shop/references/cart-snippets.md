# Fred Meyer cart snippets

JavaScript snippets used in Phase 4 of the `fredmeyer-shop` skill. Pass them to `chrome-devtools:evaluate_script`.

## Cart endpoint (discovered 2026-04-04, verified 2026-06-27, corrected 2026-07-18)

`PUT /atlas/v1/carts/{cartId}` **merges/upserts, it does not replace the cart.** (Earlier notes said "replaces the entire cart" — confirmed wrong on 2026-07-18: a PUT with a lineItems array missing a previously-added gtin13 left that item in the cart.) The body is `{ lineItems: [...] }`. The response contains `data.carts.lineItemCount` and `data.carts.versionKey`.

Each lineItem keeps the `created` timestamp from when it was **first** added; a later PUT that resends the same `gtin13` only bumps `modified`/`quantity`, it does not move the item. This matters for Phase 4c's category-ordering trick: an item added once (e.g. during cart-ID discovery in 4b) stays pinned at its original position even if it's resent later inside its proper category batch. **Pick the discovery item from category 1** (the first category in display order) so this doesn't put something out of place; if that's not possible, expect that one item to sit out of order and mention it in the Phase 5 report.

There is no known way to remove or reorder a line item via this endpoint: `quantity: 0` returns **400**, and `DELETE /atlas/v1/carts/{cartId}/line-items/{id}` returns **404** (both tried 2026-07-18). If an item needs to come out, the user has to remove it in the UI.

The cart ID is **session-specific** and must be discovered fresh each run. Best method:

- Add one item via DOM click (snippet 3), wait ~2s, then read `performance.getEntriesByType('resource')` filtered to `.includes('carts')` — the entry with the full cart ID appears as `/atlas/v1/carts/{cartId}`.

Fallback / verification: `GET /atlas/v1/carts` needs an `x-kroger-channel: WEB` header or it 400s with `MISSING_CHANNEL` (this, not flakiness, is why earlier notes saw 400s). With the header it reliably returns `data.carts[0].lineItems` — use this to verify the final cart contents (see snippet 8) rather than scraping the `/cart` page DOM, which also renders "Buy it Again" / recommendation carousels using the same product-card markup and will over-match.

---

## Snippet 1 — Fulfillment-mode check

```javascript
() => document.querySelector('[data-testid*="fulfillment"], [aria-label*="fulfillment"], [class*="FulfillmentSelector"]')?.innerText?.trim() || 'unknown'
```

If the result is "Delivery" or unset, ask the user to set a pickup store before continuing.

## Snippet 2 — Product status check

Run after navigating to a `/p/` product URL. Allow ~3 seconds for React render before checking.

```javascript
async () => {
  await new Promise(r => setTimeout(r, 3000));
  return {
    title: document.querySelector('h1')?.innerText?.trim() || '',
    outOfStock: !!(document.body.innerText.match(/out of stock/i) && document.body.innerText.match(/pickup/i)),
    deliveryOnly: /delivery only/i.test(document.body.innerText),
    hasQtyInput: !!document.querySelector('input[aria-label*="Quantity" i], [role="spinbutton"]')
  };
}
```

## Snippet 3 — Set quantity and click Add to Cart

```javascript
(qty) => {
  const inp = document.querySelector('input[aria-label*="Quantity" i], [role="spinbutton"]');
  if (inp) {
    const nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    nativeSetter.call(inp, String(qty));
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
  }
  const btn = [...document.querySelectorAll('button')].find(b =>
    /add to cart/i.test(b.innerText) && !b.disabled
  );
  if (!btn) return 'no-button';
  btn.click();
  return 'clicked';
}
```

## Snippet 4 — Recent network resources

Run after a click to list candidate cart endpoints, then combine with `chrome-devtools:list_network_requests` to inspect POST bodies.

```javascript
() => performance.getEntriesByType('resource')
  .filter(e => e.name.includes('/api/') || e.name.includes('/atlas/') || e.name.includes('/cart'))
  .map(e => e.name)
  .slice(-10)
```

## Snippet 5 — Add items via fetch (call once per category, in display order)

`cartId` and the request shape come from step 4b. Substitute placeholders before running.

Call this **once per category** in Phase 4c, passing the **cumulative** ordered item list each time — i.e. after category N, `items` holds every item from categories 1..N, in category display order. This endpoint *upserts* (see the endpoint note above): resending an already-added gtin13 is harmless and just refreshes `modified`, it doesn't move the item. What actually keeps the cart sorted is that each category's items get their `created` timestamp on the call where they're *first* introduced, and the calls run in category order — so later categories end up with later `created` times. Await each call before the next.

```javascript
async () => {
  const cartId = 'YOUR_CART_ID';   // discovered fresh each session
  const items = [
    // cumulative, in category display order:
    // {upc: 'XXXXXXXXXXXXX', qty: 1, name: 'optional label'}
  ];

  const lineItems = items.map(i => ({
    gtin13: i.upc,
    modalityType: 'PICKUP',
    quantity: i.qty,
    channel: 'WEB',
    substitutionPolicy: 'SHOPPER_CHOICE'
  }));

  const resp = await fetch(`/atlas/v1/carts/${cartId}`, {
    method: 'PUT',
    credentials: 'include',
    headers: {
      'content-type': 'application/json',
      'accept': 'application/json, text/plain, */*',
      'x-kroger-channel': 'WEB',
    },
    body: JSON.stringify({ lineItems })
  });
  const data = await resp.json();
  return { status: resp.status, lineItemCount: data?.data?.carts?.lineItemCount };
}
```

## Snippet 6 — First product link from a search page

Navigate to `https://www.fredmeyer.com/search?query={url-encoded-name}` first.

```javascript
(name) => {
  const cards = [...document.querySelectorAll('article, [data-testid*="product"]')];
  const match = cards.find(c => c.innerText.toLowerCase().includes(name.toLowerCase().split(' ')[0]));
  return match?.querySelector('a[href*="/p/"]')?.getAttribute('href') || null;
}
```

## Snippet 7 — Cart count (no navigation)

```javascript
() => ({
  cartCount: document.querySelector('[data-testid*="cart-count"], [aria-label*="cart"]')?.innerText?.trim()
})
```

## Snippet 8 — Cart contents (authoritative, no navigation needed)

The old DOM-scraping approach (`[data-testid*="cart-item"] h2`) no longer matches anything, and the more permissive `a[href*="/p/"]` / `[data-testid="cart-page-item-description"]` selectors over-match: the `/cart` page renders "Buy it Again" and other recommendation carousels with the same product-card markup, so a scrape returns 100+ names instead of the real line-item count. Use the cart-list endpoint instead (needs the `x-kroger-channel` header — see endpoint note above):

```javascript
async () => {
  const resp = await fetch('/atlas/v1/carts', { credentials: 'include', headers: {'accept':'application/json', 'x-kroger-channel':'WEB'} });
  const data = await resp.json();
  const cart = data.data.carts[0];
  return { lineItemCount: cart.lineItemCount, items: cart.lineItems.map(li => ({gtin13: li.gtin13, qty: li.quantity})) };
}
```

Compare `items` against the expected `{upc, qty}` list built in Phase 4c to confirm every item and quantity landed correctly.
