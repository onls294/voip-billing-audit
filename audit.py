"""Audit a voice provider's usage export: real vs. billed seconds, per product.

Standard library only. Input: a per-call usage CSV with the generic schema below. Output: a
per-product summary (printed and written to a CSV) and a check that every call was billed as
its declared rounding rule says.

Input schema (all columns required; extra columns are ignored):

    call_id          unique id of the call leg
    product          product name as the provider reports it (e.g. voice_outbound, recording)
    started_at       ISO-8601 timestamp (only used for the period covered)
    real_seconds     duration the provider measured, in whole seconds (>= 0)
    billed_seconds   duration the provider billed, in whole seconds (>= 0)
    rounding_rule    how the product is billed, one of RULES below

Usage:
    python audit.py usage.csv --out summary.csv [--products voice_outbound,recording]
"""
import argparse
import csv
import math
import sys

REQUIRED = ("call_id", "product", "started_at", "real_seconds", "billed_seconds", "rounding_rule")


def per_second(s):
    return s


def per_minute(s):
    """Rounded up to the next full minute; a 0-second leg is not billed."""
    return 60 * math.ceil(s / 60)


def block_6s(s):
    """Rounded up to the next 6-second block; a 0-second leg is not billed."""
    return 6 * math.ceil(s / 6)


def minute_then_6s(s):
    """First 60 seconds billed in full, then 6-second blocks ("60/6"); 0 seconds is not billed."""
    return 0 if s == 0 else (60 if s <= 60 else 60 + block_6s(s - 60))


RULES = {"per_second": per_second, "per_minute": per_minute, "6s_blocks": block_6s, "60_6": minute_then_6s}


def expected_billed(real_seconds, rule):
    if rule not in RULES:
        raise ValueError(f"unknown rounding_rule {rule!r}; expected one of {sorted(RULES)}")
    return RULES[rule](real_seconds)


def load(path):
    """Read and validate the usage CSV. Raises ValueError on a missing column or a bad value."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing required column(s): {', '.join(missing)}")
        rows = []
        for i, r in enumerate(reader, 2):
            try:
                real, billed = int(r["real_seconds"]), int(r["billed_seconds"])
            except ValueError:
                raise ValueError(f"line {i}: real_seconds and billed_seconds must be whole numbers") from None
            if real < 0 or billed < 0:
                raise ValueError(f"line {i}: negative seconds")
            rows.append({**r, "real_seconds": real, "billed_seconds": billed})
    return rows


def summarize(rows, products=()):
    """Per product: calls, real and billed seconds, difference, billed/real ratio, and how many
    calls were billed differently from their declared rounding rule. Products listed in
    `products` appear even with no calls (ratio is None when real seconds are 0)."""
    out = {p: {"calls": 0, "real_seconds": 0, "billed_seconds": 0, "rule_mismatches": 0} for p in products}
    for r in rows:
        s = out.setdefault(r["product"], {"calls": 0, "real_seconds": 0, "billed_seconds": 0, "rule_mismatches": 0})
        s["calls"] += 1
        s["real_seconds"] += r["real_seconds"]
        s["billed_seconds"] += r["billed_seconds"]
        s["rule_mismatches"] += expected_billed(r["real_seconds"], r["rounding_rule"]) != r["billed_seconds"]
    for s in out.values():
        s["difference_seconds"] = s["billed_seconds"] - s["real_seconds"]
        s["billed_over_real"] = s["billed_seconds"] / s["real_seconds"] if s["real_seconds"] else None
    return dict(sorted(out.items()))


def write_csv(summary, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["product", "calls", "real_seconds", "billed_seconds", "difference_seconds",
                    "billed_over_real", "rule_mismatches"])
        for p, s in summary.items():
            ratio = "" if s["billed_over_real"] is None else f"{s['billed_over_real']:.4f}"
            w.writerow([p, s["calls"], s["real_seconds"], s["billed_seconds"], s["difference_seconds"],
                        ratio, s["rule_mismatches"]])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Real vs. billed seconds per product from a usage CSV.")
    ap.add_argument("usage_csv")
    ap.add_argument("--out", default="audit_summary.csv")
    ap.add_argument("--products", default="", help="comma-separated products to report even with no calls")
    a = ap.parse_args(argv)
    try:
        rows = load(a.usage_csv)
    except ValueError as e:
        print(f"invalid input: {e}", file=sys.stderr)
        return 2
    summary = summarize(rows, [p for p in a.products.split(",") if p])
    write_csv(summary, a.out)
    print(f"{'product':<18}{'calls':>7}{'real s':>10}{'billed s':>10}{'diff s':>9}{'billed/real':>13}{'mismatch':>10}")
    for p, s in summary.items():
        ratio = "–" if s["billed_over_real"] is None else f"{s['billed_over_real']:.3f}"
        print(f"{p:<18}{s['calls']:>7}{s['real_seconds']:>10}{s['billed_seconds']:>10}"
              f"{s['difference_seconds']:>9}{ratio:>13}{s['rule_mismatches']:>10}")
    print(f"\nwritten: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
