"""Generate a SYNTHETIC usage CSV for audit.py (standard library, fixed seed).

Every value is invented: products, durations and ids are not taken from any real account.
The output file name carries SYNTHETIC on purpose.

    python generate_synthetic.py            -> sample_usage_SYNTHETIC.csv
"""
import csv
import random
from datetime import datetime, timedelta

from audit import expected_billed

SEED = 20260928
# product -> (rounding rule, number of legs, share of 0-second legs, typical duration range)
PRODUCTS = {
    "voice_outbound": ("per_minute", 600, 0.20, (5, 420)),
    "voice_inbound": ("6s_blocks", 200, 0.05, (10, 600)),
    "recording": ("per_minute", 300, 0.00, (20, 420)),
    "voice_intl": ("60_6", 80, 0.10, (15, 300)),
}
MISBILLED = 3   # a few legs billed off-rule on purpose, so the audit has something to find


def generate(path="sample_usage_SYNTHETIC.csv", seed=SEED):
    rng = random.Random(seed)
    start = datetime(2026, 1, 1)
    rows = []
    for product, (rule, n, zero_share, (lo, hi)) in PRODUCTS.items():
        for _ in range(n):
            real = 0 if rng.random() < zero_share else rng.randint(lo, hi)
            rows.append({"call_id": "", "product": product,
                         "started_at": (start + timedelta(minutes=rng.randint(0, 30 * 24 * 60))).isoformat(),
                         "real_seconds": real, "billed_seconds": expected_billed(real, rule), "rounding_rule": rule})
    rng.shuffle(rows)
    for r in rng.sample([r for r in rows if r["real_seconds"] > 0], MISBILLED):
        r["billed_seconds"] += 60
    for i, r in enumerate(rows, 1):
        r["call_id"] = f"SYN-{i:05d}"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


if __name__ == "__main__":
    print("written:", generate())
