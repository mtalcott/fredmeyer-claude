# Output templates

Templates for the prompts emitted by the `fredmeyer-shop` skill in Phases 2 and 3. Item names below are generic placeholders — substitute the user's actual items from the CSV.

## Phase 2 — Suggested list

The annotation in `[...]` is the **reason string** — built from the 1b stats so the
number shown is the number that drove the suggestion. Patterns:

- At-cadence buy: `[~7d cadence, last 18d ago — due]` / `[... — overdue]`
- Confidence caveat: append `· irregular` for `erratic` items.
- Abandoned (opt-in): `[~7d cadence, last 110d ago — haven't bought in a while]`
- Sparse (opt-in): `[bought 2× · last Mar 10]` (no cadence — don't invent one).
- Keep-sourced: `[from Keep]`. Substitution: `[→ substitution for previous]`.

```
SUGGESTED SHOPPING LIST
========================

── DUE NOW (✓ already in your order) ─────────────────────────────────

Protein:
  ✓ Creamy peanut butter (16 oz)                  qty: 2   [~7d cadence, last 9d ago — due, 87% of orders]
  ✓ Pasture-raised eggs (1 dozen)                 qty: 1   [~14d cadence, last 16d ago — overdue, 54% of orders]
Dairy / Alternatives:
  ✓ Vanilla oat milk (52 fl oz)                   qty: 5   [~9d cadence, last 11d ago — due, 92% of orders (incl. substitutions)]
Snacks / Sweets:
  ✓ Special K Original cereal (12 oz)             qty: 1   [from Keep]
Vegetables:
  ✓ Butterhead lettuce (9 oz)                     qty: 2   [~12d cadence, last 14d ago — due, 73% of orders]
Bread / Grains:
  ✓ Whole-grain sandwich bread                    qty: 1   [~15d cadence, last 20d ago — overdue, 61% of orders]

── MAYBE — add any you're running low on (·) ─────────────────────────

Protein:
  · Extra-firm tofu                               [~7d cadence, last 31d ago — haven't bought in a while]
  · Foster Farms chicken (per lb)                 [~7d cadence, last 19d ago · irregular]
Personal Care:
  · Body wash (18 fl oz)                          [bought 2× · last Mar 16]
  · Body wash, alternate brand (18 fl oz)         [bought 1× · last Mar 15 → substitution for previous]
Paper / Household:
  · Diaper-pail refill bags                       [bought 1× · last Mar 1]
Beverages:
  · Prebiotic soda                                [bought 2× · last Mar 17]
```

After printing the list, ask:

> Staples (✓) are already in your order. For infrequent items (·), reply with any you need.
>
> You can also:
> - Change a staple quantity: e.g. `peanut butter: 3`
> - Remove a staple: e.g. `remove oat milk`
> - Add an infrequent item: e.g. `body wash` or `body wash: 2`
> - Accept as-is: type `ok`
>
> Any changes?

## Phase 3 — Final order

```
FINAL ORDER — ready to add to cart
====================================
 1. Creamy peanut butter (16 oz)              x2
 2. Vanilla oat milk (52 fl oz)               x5
 3. Butterhead lettuce (9 oz)                 x2
 4. Pasture-raised eggs (1 dozen)             x1
 5. Whole-grain sandwich bread                x1
    [+ any infrequent items the user added]

Total: N items
```
