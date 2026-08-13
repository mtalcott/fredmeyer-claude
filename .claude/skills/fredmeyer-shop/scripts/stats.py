#!/usr/bin/env python3
"""Per-item purchase statistics for the fredmeyer-shop skill (Phase 1b).

Reads the purchase-history CSV and emits, per item (grouped by UPC), the
deterministic signals the skill reasons over: recency, cadence, and a
"due score". This is intentionally small — no priors, no shrinkage, no model.
The LLM layer applies fuzzy user preferences and makes the final call; this
script only does the arithmetic the LLM shouldn't eyeball over 280+ items.

Design notes (see the 5-agent investigation that motivated this):
  * 64% of items are bought once and 73% <=2 times, so a per-item cadence is
    only trustworthy with >=3 purchases (>=2 intervals). Below that we report
    "insufficient data" rather than a confident-looking number.
  * Cadence uses the MEDIAN of consecutive intervals, not (last-first)/(n-1):
    the mean is corrupted by one-off adoption/abandonment gaps
    (e.g. an item bought once in Jan, then weekly from May).
  * due_ratio = days_since_last / median_interval. <0.5 = just bought
    (suppress); >1.3 = overdue (surface). This replaces the brittle single
    17-day staple/infrequent threshold as a *gate* — that label survives only
    as a soft display hint.
  * A coefficient-of-variation flag marks erratic items so the skill can offer
    them opt-in rather than auto-include.
  * Cadence (median_interval/interval_cv/due_ratio) prefers the last
    WINDOW_DAYS of purchases over full history: an item that ramped up
    irregularly when first adopted but has since settled into a steady
    weekly buy would otherwise show a permanently inflated CV from that
    early ramp-up, misclassifying a real staple as "erratic". When an item
    has fewer than MIN_PURCHASES dates inside the window (e.g. it hasn't
    been bought recently at all), cadence falls back to full history so
    "haven't bought in a while" detection for abandoned items still works.

Usage:
  python3 stats.py [--csv PATH] [--today YYYY-MM-DD] [--window-days N] [--json]

Default --csv is fred-meyer-purchases.csv in the current directory; default
--today is the system date; default --window-days is 60.
"""
import argparse
import csv
import datetime as dt
import json
import re
import statistics
from collections import defaultdict

# due_ratio thresholds (tunable; deliberately loose given small-n data)
JUST_BOUGHT = 0.5   # below this: bought too recently to re-suggest
OVERDUE = 1.3       # above this: past its usual cadence
ERRATIC_CV = 0.6    # interval CV above this: cadence is unreliable
MIN_PURCHASES = 3   # need >=3 buys (>=2 intervals) for a due_ratio
WINDOW_DAYS = 60    # cadence prefers purchases within this many days of --today


def parse_qty(raw):
    """Return (numeric_qty, is_weight). Quantity is '2', '4.96 lbs', etc."""
    if raw is None:
        return (None, False)
    s = raw.strip()
    is_weight = "lb" in s.lower()
    m = re.search(r"[-+]?\d*\.?\d+", s)
    return (float(m.group()) if m else None, is_weight)


def parse_date(s):
    return dt.date.fromisoformat(s.strip())


def load(csv_path):
    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            r["_date"] = parse_date(r["date"])
            r["_qty"], r["_weight"] = parse_qty(r.get("quantity"))
            rows.append(r)
    return rows


def compute(rows, today, window_days=WINDOW_DAYS):
    total_orders = len({r["_date"] for r in rows})
    window_start = today - dt.timedelta(days=window_days)

    groups = defaultdict(list)
    for r in rows:
        key = r["upc"].strip() if r.get("upc", "").strip() not in ("", "unknown") else r["item_name"].strip()
        groups[key].append(r)

    items = []
    for key, grp in groups.items():
        dates = sorted({r["_date"] for r in grp})
        count = len(dates)
        last = dates[-1]
        days_since = (today - last).days

        # Prefer recent-window dates for cadence; fall back to full history
        # when the window doesn't have enough purchases to be trustworthy
        # (this keeps "haven't bought in a while" working for items with no
        # recent purchases at all, instead of just going "insufficient").
        window_dates = [d for d in dates if d >= window_start]
        cadence_dates = window_dates if len(window_dates) >= MIN_PURCHASES else dates

        intervals = [(cadence_dates[i + 1] - cadence_dates[i]).days for i in range(len(cadence_dates) - 1)]
        median_int = statistics.median(intervals) if intervals else None
        cv = (statistics.pstdev(intervals) / statistics.mean(intervals)
              if len(intervals) >= 2 and statistics.mean(intervals) else None)

        # due_ratio only when cadence is trustworthy (>=3 purchases)
        if count >= MIN_PURCHASES and median_int:
            due_ratio = round(days_since / median_int, 2)
            if due_ratio < JUST_BOUGHT:
                state = "recent"
            elif due_ratio > OVERDUE:
                state = "OVERDUE"
            else:
                state = "due"
        else:
            due_ratio = None
            state = "insufficient"

        qtys = [r["_qty"] for r in grp if r["_qty"] is not None]
        is_weight = any(r["_weight"] for r in grp)
        typical_qty = None
        if qtys:
            try:
                typical_qty = statistics.mode([round(q) for q in qtys])
            except statistics.StatisticsError:
                typical_qty = round(statistics.median(qtys))

        # pick a representative row (latest) for display fields
        rep = max(grp, key=lambda r: r["_date"])
        items.append({
            "item_name": rep["item_name"],
            "size": rep.get("size", ""),
            "upc": rep.get("upc", ""),
            "product_url": rep.get("product_url", ""),
            "purchase_count": count,
            "participation_pct": round(100 * count / total_orders, 1),
            "last_purchased": last.isoformat(),
            "days_since_last": days_since,
            "median_interval": median_int,
            "interval_cv": round(cv, 2) if cv is not None else None,
            "erratic": (cv is not None and cv > ERRATIC_CV),
            "due_ratio": due_ratio,
            "state": state,
            "typical_qty": typical_qty,
            "weight_based": is_weight,
        })

    # sort: actionable items by due_ratio desc, insufficient-data last by recency
    def sort_key(it):
        has_ratio = it["due_ratio"] is not None
        return (0 if has_ratio else 1,
                -(it["due_ratio"] or 0),
                -it["days_since_last"])

    items.sort(key=sort_key)
    return total_orders, items


def fmt_table(total_orders, items, today):
    lines = [
        f"# Purchase stats  (today={today.isoformat()}, orders={total_orders}, items={len(items)})",
        f"# due_ratio = days_since_last / median_interval; "
        f"<{JUST_BOUGHT} recent, >{OVERDUE} OVERDUE. "
        f"'insufficient' = <{MIN_PURCHASES} purchases, no reliable cadence.",
        "",
    ]
    for it in items:
        name = (it["item_name"][:42]).ljust(42)
        cad = f"~{it['median_interval']}d" if it["median_interval"] else "n/a"
        due = f"due={it['due_ratio']}" if it["due_ratio"] is not None else "due=—"
        erratic = " ERRATIC" if it["erratic"] else ""
        wt = " wt" if it["weight_based"] else ""
        lines.append(
            f"{it['state']:>12} | {name} | n={it['purchase_count']:>2} "
            f"part={it['participation_pct']:>5}% | last {it['last_purchased']} "
            f"({it['days_since_last']}d ago) | int {cad} | {due} | "
            f"qty~{it['typical_qty']}{wt}{erratic} | {it['upc']}"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="fred-meyer-purchases.csv")
    ap.add_argument("--today", default=None, help="reference date YYYY-MM-DD (default: system today)")
    ap.add_argument("--window-days", type=int, default=WINDOW_DAYS,
                     help=f"cadence window in days (default: {WINDOW_DAYS})")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a text table")
    args = ap.parse_args()

    today = parse_date(args.today) if args.today else dt.date.today()
    rows = load(args.csv)
    total_orders, items = compute(rows, today, args.window_days)

    if args.json:
        print(json.dumps({"today": today.isoformat(), "total_orders": total_orders, "items": items}, indent=2))
    else:
        print(fmt_table(total_orders, items, today))


if __name__ == "__main__":
    main()
