# voip-billing-audit

How to audit a voice provider's bill: separate the seconds a call really lasted from the
seconds the provider billed, per product, and check that every call was billed by its
declared rounding rule. Standard-library Python only.

> **Every data file in this repo is synthetic.** `generate_synthetic.py` invents every product,
> duration and id with a fixed seed. No real account, amount or call is included. The only real
> figure is the voicemail hang-up rate quoted in "Two lessons", as it was measured.

## How to run

Tested with **Python 3.13.2**, standard library only (no packages to install).

```bash
python generate_synthetic.py                      # -> sample_usage_SYNTHETIC.csv
python audit.py sample_usage_SYNTHETIC.csv --out audit_summary_SYNTHETIC.csv
python -m unittest -v                             # hand-computed test cases
```

Output on the synthetic sample (seed 20260928):

| product | calls | real s | billed s | diff s | billed / real | off-rule |
|---|---|---|---|---|---|---|
| recording | 300 | 66,993 | 76,080 | 9,087 | 1.136 | 1 |
| voice_inbound | 200 | 57,408 | 57,996 | 588 | 1.010 | 2 |
| voice_intl | 80 | 11,079 | 11,604 | 525 | 1.047 | 0 |
| voice_outbound | 600 | 103,139 | 117,480 | 14,341 | 1.139 | 0 |

Synthetic numbers: they show what the audit finds, not what any real bill looks like. The
3 off-rule calls were planted by the generator on purpose.

## Input

`audit.py` reads a **CSV file** with one row per call leg. It does not call any provider API:
export the usage data first, then map its columns to this schema.

| column | meaning |
|---|---|
| `call_id` | unique id of the leg |
| `product` | product as the provider names it (voice, recording, international...) |
| `started_at` | ISO-8601 timestamp |
| `real_seconds` | duration measured by the provider |
| `billed_seconds` | duration the provider billed |
| `rounding_rule` | `per_second`, `per_minute`, `6s_blocks` or `60_6` (first minute, then 6 s blocks) |

A missing column or a non-numeric duration stops the run with exit code 2. A product passed
with `--products` is reported even when it had no calls, so a silent product is visible.

## How to audit, step by step

1. **Define the event and the denominator before any number.** What is one "call": a leg, a
   connected call, a conversation? Which legs belong to the lead and which to the agent? Write
   the definition down, with the table, the filter and the date window.
2. **Get both durations from the provider's usage data.** Check whether it already reports real
   and billed seconds. If it does, there is nothing to reverse-engineer: map both fields.
3. **Split by product.** Rounding differs per product. A per-minute product turns a 5-second
   leg into 60 billed seconds; a 6-second-block product turns it into 6.
4. **Check each call against its rule** (`rule_mismatches`). The gap between real and billed is
   usually expected rounding. An off-rule call is the thing to raise with the provider.
5. **Look at the ratio, then at the volume.** `billed / real` tells you where rounding hurts;
   the seconds tell you where the money is. A product with a bad ratio and little volume
   matters less than a mild ratio on most of the traffic.
6. **Measure again before you report.** A figure that was right when measured can be stale a
   few hours later.

## Two lessons from doing this on a real account

**A baseline can be wrong in its denominator, not in its indicator.** The project's own
baseline for "minutes per conversation" counted the agent's legs as conversations instead of
the lead's. The denominator was inflated, so the indicator looked far lower
than it was. With that denominator, switching a feature off would have lowered the
"conversations" count without losing a single real conversation. The fix was step 1 above:
define the event first, then count.

**Watch the rate, not the count.** Voicemail hang-ups went from **3.50 to 3.06 per 100 calls**
between the fortnight before and the fortnight after a change in voicemail detection on
7 September 2026 (fortnights aligned to 21 September, measured 24 September). The raw count fell
much more, because call volume also fell in the same fortnight. A threshold written as an
absolute number would have fired on a volume change, not on a failure. So write alarm
thresholds per 100 calls, with the exact window they were measured on.

## Files

| file | what |
|---|---|
| `audit.py` | loads and validates the CSV, applies the rounding rules, writes the per-product summary |
| `generate_synthetic.py` | synthetic usage CSV, fixed seed, file names marked `SYNTHETIC` |
| `test_audit.py` | per-minute rounding, 6-second blocks, a 0-second call, a product with no calls, missing columns |
| `sample_usage_SYNTHETIC.csv`, `audit_summary_SYNTHETIC.csv` | generated sample and its summary |

## Limits

- The four rounding rules cover the common cases; a provider with a minimum charge, setup fee
  or per-call fee needs a new rule.
- The audit checks seconds, not prices. Turning billed seconds into money needs the provider's
  price list for each product.
