# Output templates

Templates for the prompts emitted by the `fredmeyer-shop` skill in Phases 2 and 3. Item names below are generic placeholders — substitute the user's actual items from the CSV.

## Phase 2 — Suggested list

```
SUGGESTED SHOPPING LIST
========================

── STAPLES (avg interval ≤ 17 days — already in your order) ──────────

Protein:
  ✓ Creamy peanut butter (16 oz)                  qty: 2   [every 7d, 87% of orders]
  ✓ Pasture-raised eggs (1 dozen)                 qty: 1   [every 14d, 54% of orders]
Dairy / Alternatives:
  ✓ Vanilla oat milk (52 fl oz)                   qty: 5   [every 9d, 92% of orders (incl. substitutions)]
Snacks / Sweets:
  ✓ Special K Original cereal (12 oz)             qty: 1   [from Keep]
Vegetables:
  ✓ Butterhead lettuce (9 oz)                     qty: 2   [every 12d, 73% of orders]
Bread / Grains:
  ✓ Whole-grain sandwich bread                    qty: 1   [every 15d, 61% of orders]

── INFREQUENT — add any you're running low on ────────────────────────

Personal Care (last bought):
  · Body wash (18 fl oz)                          Mar 16
  · Body wash, alternate brand (18 fl oz)         Mar 15   [→ substitution for previous]
Paper / Household:
  · Diaper-pail refill bags                       Mar 1
Protein:
  · Extra-firm tofu                               Mar 10
Beverages:
  · Prebiotic soda                                Mar 17
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
