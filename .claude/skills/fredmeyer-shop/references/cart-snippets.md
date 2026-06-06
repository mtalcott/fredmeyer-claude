# Fred Meyer cart snippets

JavaScript snippets used in Phase 4 of the `fredmeyer-shop` skill. Pass them to `chrome-devtools:evaluate_script`.

## Cart endpoint (discovered 2026-04-04)

`PUT /atlas/v1/carts/{cartId}` replaces the entire cart. The body is `{ lineItems: [...] }`. The response contains `data.carts.lineItemCount` and `data.carts.versionKey`.

The cart ID is **session-specific** and must be discovered fresh each run. Two ways to find it:

- Add one item via DOM click (snippet 3) and inspect the resulting PUT request — its URL contains the cart ID.
- `GET /atlas/v1/carts` may return `data.carts[0].id`, but can be empty.

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

## Snippet 5 — Replace the cart via fetch (call once per category, in display order)

`cartId` and the request shape come from step 4b. Substitute placeholders before running.

Call this **once per category** in Phase 4c, passing the **cumulative** ordered item list each time — i.e. after category N, `items` holds every item from categories 1..N, in category display order. Because this endpoint *replaces* the whole cart, the cumulative array keeps the cart sorted (and the sequential calls give each category a later add-time). The final call therefore contains the complete order in preview order. Await each call before the next.

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

## Snippet 8 — Cart item names (after navigating to /cart)

```javascript
() => [...document.querySelectorAll('[data-testid*="cart-item"] h2, [class*="CartItem"] h2')]
  .map(h => h.innerText.trim())
```
