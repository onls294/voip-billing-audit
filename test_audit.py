"""Hand-computed cases for audit.py (standard library unittest).

    python -m unittest -v
"""
import csv
import os
import tempfile
import unittest

import audit
import generate_synthetic


def _csv(rows, header=audit.REQUIRED):
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


class Rounding(unittest.TestCase):
    def test_per_minute(self):
        self.assertEqual(audit.expected_billed(1, "per_minute"), 60)
        self.assertEqual(audit.expected_billed(60, "per_minute"), 60)
        self.assertEqual(audit.expected_billed(61, "per_minute"), 120)

    def test_6_second_blocks(self):
        self.assertEqual(audit.expected_billed(1, "6s_blocks"), 6)
        self.assertEqual(audit.expected_billed(13, "6s_blocks"), 18)
        self.assertEqual(audit.expected_billed(18, "6s_blocks"), 18)

    def test_60_then_6(self):
        self.assertEqual(audit.expected_billed(5, "60_6"), 60)
        self.assertEqual(audit.expected_billed(61, "60_6"), 66)

    def test_zero_second_leg_is_not_billed(self):
        for rule in audit.RULES:
            self.assertEqual(audit.expected_billed(0, rule), 0, rule)

    def test_unknown_rule_is_rejected(self):
        with self.assertRaises(ValueError):
            audit.expected_billed(10, "per_hour")


class Summary(unittest.TestCase):
    def test_hand_computed_summary(self):
        path = _csv([["a", "voice", "2026-01-01T00:00:00", 61, 120, "per_minute"],
                     ["b", "voice", "2026-01-01T00:01:00", 0, 0, "per_minute"],
                     ["c", "voice", "2026-01-01T00:02:00", 30, 60, "per_minute"],
                     ["d", "rec", "2026-01-01T00:03:00", 13, 18, "6s_blocks"]])
        s = audit.summarize(audit.load(path))
        os.remove(path)
        self.assertEqual(s["voice"]["calls"], 3)
        self.assertEqual((s["voice"]["real_seconds"], s["voice"]["billed_seconds"]), (91, 180))
        self.assertEqual(s["voice"]["difference_seconds"], 89)
        self.assertAlmostEqual(s["voice"]["billed_over_real"], 180 / 91)
        self.assertEqual(s["rec"]["difference_seconds"], 5)
        self.assertEqual(s["voice"]["rule_mismatches"], 0)

    def test_product_without_calls_is_reported(self):
        s = audit.summarize([], products=["voice_intl"])
        self.assertEqual(s["voice_intl"]["calls"], 0)
        self.assertIsNone(s["voice_intl"]["billed_over_real"])

    def test_billing_off_rule_is_flagged(self):
        path = _csv([["a", "voice", "2026-01-01T00:00:00", 61, 180, "per_minute"]])
        s = audit.summarize(audit.load(path))
        os.remove(path)
        self.assertEqual(s["voice"]["rule_mismatches"], 1)


class Validation(unittest.TestCase):
    def test_negative_missing_columns_are_rejected(self):
        path = _csv([["a", "voice", 61, 120]], header=("call_id", "product", "real_seconds", "billed_seconds"))
        with self.assertRaises(ValueError) as e:
            audit.load(path)
        os.remove(path)
        self.assertIn("started_at", str(e.exception))
        self.assertIn("rounding_rule", str(e.exception))

    def test_negative_non_numeric_seconds_are_rejected(self):
        path = _csv([["a", "voice", "2026-01-01T00:00:00", "sixty", 60, "per_minute"]])
        with self.assertRaises(ValueError):
            audit.load(path)
        os.remove(path)

    def test_cli_exit_code_on_bad_input(self):
        path = _csv([["a"]], header=("call_id",))
        self.assertEqual(audit.main([path, "--out", path + ".out.csv"]), 2)
        os.remove(path)


class SyntheticData(unittest.TestCase):
    def test_generator_is_deterministic_and_finds_the_planted_errors(self):
        d = tempfile.mkdtemp()
        p1 = generate_synthetic.generate(os.path.join(d, "a_SYNTHETIC.csv"))
        p2 = generate_synthetic.generate(os.path.join(d, "b_SYNTHETIC.csv"))
        with open(p1, encoding="utf-8") as f1, open(p2, encoding="utf-8") as f2:
            self.assertEqual(f1.read(), f2.read())
        s = audit.summarize(audit.load(p1))
        self.assertEqual(sum(x["rule_mismatches"] for x in s.values()), generate_synthetic.MISBILLED)
        self.assertTrue(all(x["billed_seconds"] >= x["real_seconds"] for x in s.values()))


if __name__ == "__main__":
    unittest.main()
