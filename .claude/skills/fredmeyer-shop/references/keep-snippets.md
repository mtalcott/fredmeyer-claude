# Google Keep grocery-list snippets

JS snippets for reading the user's grocery list from Google Keep via the
`chrome-devtools` MCP, plus the rules for turning a structured Keep note into a
clean Fred Meyer item list. Follow the conventions in
`../_shared/chrome-devtools-tips.md` (return minimal payloads, poll for render,
prefer `evaluate_script`).

**Keep is a React SPA with obfuscated CSS class names — selectors drift.** The
guaranteed contract is the paste fallback (snippet 4): if any step returns
nothing or the note isn't found, ask the user to paste the list and proceed
identically. Never block on the scraper.

The Chrome session is shared with the Fred Meyer flow. The user may have multiple
Google accounts; Keep opens at `https://keep.google.com` and may resolve to a
`/u/<n>/` path — that is expected.

---

## Snippet 1 — login check

Navigate to `https://keep.google.com` first, then:

```javascript
async () => {
  for (let i = 0; i < 16; i++) {
    if (/keep\.google\.com/.test(location.href) &&
        document.querySelectorAll('[aria-label]').length > 20) break;
    if (/accounts\.google\.com/.test(location.href)) break;
    await new Promise(r => setTimeout(r, 500));
  }
  return /accounts\.google\.com/.test(location.href) ? 'signed-out' : 'signed-in';
}
```

If `signed-out`, ask the user to sign in to Keep in the open Chrome window and
wait. Do not automate the Google login flow.

## Snippet 2 — find and open the grocery note by title

Note cards on the main grid render their title as the first line of text. Find the
card whose first line matches the configured title (default `"Groceries"`), then
click it to open the full editor — the grid card truncates and hides completed
items, so the editor is the source of truth.

```javascript
async (title) => {
  for (let i = 0; i < 16; i++) {
    if (document.querySelectorAll('[aria-label]').length > 20) break;
    await new Promise(r => setTimeout(r, 500));
  }
  // Candidate cards: obfuscated class today is .IZ65Hb-n0tgWb; fall back to any
  // focusable card-like container whose first text line equals the title.
  let cards = Array.from(document.querySelectorAll('.IZ65Hb-n0tgWb'));
  if (!cards.length) {
    cards = Array.from(document.querySelectorAll('div[aria-label][tabindex]'))
      .filter(c => c.querySelector('[role="checkbox"], [contenteditable]'));
  }
  const want = title.trim().toLowerCase();
  const card = cards.find(c => ((c.innerText || '').trim().split('\n')[0] || '')
    .trim().toLowerCase() === want);
  if (!card) return { opened: false };
  card.click();
  for (let i = 0; i < 16; i++) {
    if (location.hash.startsWith('#LIST') || document.querySelector('[role="dialog"]')) break;
    await new Promise(r => setTimeout(r, 400));
  }
  await new Promise(r => setTimeout(r, 800));
  return { opened: true };
}
```

If `opened` is false, use the paste fallback (snippet 4).

## Snippet 3 — extract unchecked items with nesting

With the note open, return the **unchecked** rows in document order, each with its
indent level (top-level vs. subitem). Checked/completed items are skipped. Keep
opens notes as a full-page editor (URL `#LIST/...`), not a dialog, and the grid
cards stay in the DOM behind it — **including a truncated preview card of the
same note**, which also has a title element matching the note title. Scoping by
"find the title element, climb to an ancestor with checkboxes" is unreliable: if
`querySelectorAll` happens to return the grid-card title before the open editor's
title (DOM order isn't guaranteed to favor the editor), the climb lands on a
grid container that mixes in checkboxes from other notes entirely — confirmed
2026-08-13, where this returned 40 rows blended from ~6 unrelated notes instead
of the true 2 unchecked items in a single note.

**Robust scope-finding:** every note — each grid card *and* the open editor —
has exactly one "Background options" button. Climb from each to the nearest
ancestor with more than a handful of checkboxes, then take the one with the
**highest** checkbox count. The open editor always shows the complete note
(unchecked + checked), so it strictly dominates any grid card's truncated
preview or other notes' containers.

```javascript
async () => {
  const bgBtns = [...document.querySelectorAll('[aria-label="Background options"]')];
  let scope = null, bestCount = 0;
  for (const btn of bgBtns) {
    let node = btn.parentElement;
    for (let i = 0; i < 8 && node; i++) {
      const cb = node.querySelectorAll ? node.querySelectorAll('[role="checkbox"]').length : 0;
      if (cb > 5) { if (cb > bestCount) { bestCount = cb; scope = node; } break; }
      node = node.parentElement;
    }
  }
  if (!scope) return { count: 0, rows: [] };

  const boxes = Array.from(scope.querySelectorAll('[role="checkbox"]'))
    .filter(b => b.getAttribute('aria-checked') === 'false');
  const rows = [];
  for (const b of boxes) {
    const row = b.closest('li') || b.parentElement?.parentElement;
    if (!row) continue;
    const el = row.querySelector('[contenteditable], [role="textbox"], textarea');
    const text = (el ? (el.innerText || el.value) : row.innerText || '').trim();
    if (!text) continue;
    // Subitems are indented ~25px per level via marginLeft on the row element.
    const indent = parseInt(getComputedStyle(row).marginLeft, 10) || 0;
    rows.push({ text, level: indent >= 12 ? 1 : 0 });
  }
  return { count: rows.length, rows, scopeCheckboxTotal: bestCount };
}
```

Sanity check: `scopeCheckboxTotal` should roughly equal unchecked + checked items
in the note (visible in Keep's UI as an unchecked count plus a "N checked items"
toggle). If it's wildly higher than that sum, the scope is still wrong — fall
back to the paste fallback (snippet 4) rather than trust the result.

The order and `level` are what the section rules below depend on, so preserve
them. Item data stays small; it is fine to return inline.

## Snippet 4 — paste fallback (wording)

When snippets 2/3 yield nothing, ask:

> I couldn't read your Google Keep grocery note automatically. Paste your list
> here (one item per line), or reply "skip" to build the order from purchase
> history only.

Feed the pasted lines through the same section rules and quantity parsing below.

---

## Turning the note into Fred Meyer items

The user's grocery note mixes Fred Meyer items with other stores. Apply these
rules (confirmed with the user):

**Section rule — include only the Fred Meyer section.**
- Walk the unchecked rows in order. The list starts in the **Fred Meyer** section
  (the flat items at the top belong to Fred Meyer by default).
- A top-level row (`level === 0`) is a **store-section header** if it is a bare
  store name, has indented subitems (`level === 1`) beneath it, or matches a
  `Store: a, b, c` inline pattern. A header is not itself a shopping item.
- A header matching `/^fred ?meyer/i` (re)starts the **Fred Meyer** section.
- Any other store header starts a non-Fred-Meyer section; skip that header, its
  subitems, and any inline items after its colon, until the next Fred Meyer
  header or the end of the list.
- **Include** every item in a Fred Meyer section; **exclude** everything in a
  non-Fred-Meyer section.
- If the Fred-Meyer-vs-other boundary is ambiguous, list the top-level rows back
  to the user and ask where the Fred Meyer section ends. The Phase 2 confirmation
  is the final safety net regardless.

Worked example for the current note:
```
Special K                                             → Fred Meyer (flat top)
potstickers                                           → Fred Meyer (flat top)
Fred Meyer                                            → header, FM section (no subitems)
Asian grocery: lime leaves, mae ploy red curry paste → other store → EXCLUDE
Central market                                        → header, other store
   Creamer                                            → subitem → EXCLUDE
```
Result: `Special K`, `potstickers`.

**Quantity parsing.** Pull a quantity from each included item; default to 1.
- Leading: `^(\d+)\s*[x×]?\s+` — "2 avocados", "3 x eggs"
- Trailing: `[x×]\s*(\d+)\s*$` or `\((\d+)\)\s*$` — "milk x3", "bananas (2)"
Strip the matched quantity token from the item text before resolution.
