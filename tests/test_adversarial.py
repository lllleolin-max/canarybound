import copy
import itertools
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest

from canarybound import CanaryBoundError, analyze, fingerprint, make_manifest
from canarybound.core import MAX_EVENTS
from canarybound.experiments import demo_manifest
from canarybound.io import loads, read_manifest


class AdversarialTests(unittest.TestCase):
    def test_event_limit_boundary(self):
        m = demo_manifest()
        mid = fingerprint(m)
        def events(n):
            for i in range(n):
                yield dict(type="assign", id=f"synthetic.{i}", arm="canary", stratum="primary",
                           manifest_id=mid, at="2026-01-01T00:01:00Z")
        result = analyze(m, events(MAX_EVENTS), "2026-01-01T00:02:00Z")
        self.assertEqual(result.cells[0][2], MAX_EVENTS)
        with self.assertRaises(CanaryBoundError):
            analyze(m, events(MAX_EVENTS + 1), "2026-01-01T00:02:00Z")

    def test_manifest_byte_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "m.json"
            p.write_bytes(b" " * (65536 + 1))
            with self.assertRaises(CanaryBoundError):
                read_manifest(p)

    def test_deep_json_not_manifest(self):
        with self.assertRaises(CanaryBoundError):
            make_manifest(loads("[" * 2000 + "0" + "]" * 2000))

    def test_constructed_manifest_revalidated(self):
        m = demo_manifest()
        for field, value in [("alpha", True), ("alpha", 10 ** 5000), ("alpha", Decimal("Infinity")),
                             ("strata", (("primary", -1),)), ("strata", (("primary", True),)),
                             ("acceptable_margin", float("nan")), ("harmful_margin", float("inf"))]:
            bad = copy.copy(m)
            object.__setattr__(bad, field, value)
            with self.assertRaises(CanaryBoundError):
                analyze(bad, [], "2026-01-01T00:02:00Z")

    def test_large_rational_fixed_weight_identity(self):
        m = demo_manifest()
        tiny = Fraction(1, 10 ** 10000)
        object.__setattr__(m, "strata", (("tiny", tiny), ("main", 1 - tiny)))
        result = analyze(m, [], "2026-01-01T00:02:00Z")
        self.assertEqual(result.population.lower, -1)
        self.assertEqual(result.population.upper, 1)

    def test_weighted_missing_completion_oracle(self):
        m = demo_manifest({"a": "0.25", "b": "0.75"})
        mid = fingerprint(m)
        events = []
        pending = []
        for stratum in ("a", "b"):
            for arm in ("canary", "control"):
                for i in range(2):
                    uid = f"{stratum}.{arm}.{i}"
                    events.append(dict(type="assign", id=uid, arm=arm, stratum=stratum,
                                       manifest_id=mid, at="2026-01-01T00:01:00Z"))
                    if i:
                        pending.append((uid, stratum, arm))
                    else:
                        events.append(dict(type="outcome", id=uid, bad=int(stratum == "a" and arm == "canary"),
                                           manifest_id=mid, at="2026-01-01T00:02:00Z"))
        bounded = analyze(m, events, "2026-01-01T00:03:00Z").finite_completion
        possible = []
        for completion in itertools.product((0, 1), repeat=len(pending)):
            full = events + [dict(type="outcome", id=uid, bad=bad, manifest_id=mid, at="2026-01-01T00:02:00Z")
                             for (uid, _, _), bad in zip(pending, completion)]
            finite = analyze(m, full, "2026-01-01T00:03:00Z").finite_completion
            self.assertLessEqual(bounded.lower, finite.lower)
            self.assertGreaterEqual(bounded.upper, finite.upper)
            possible.append(finite.lower)
        self.assertEqual(bounded.lower, min(possible))
        self.assertEqual(bounded.upper, max(possible))


if __name__ == "__main__":
    unittest.main()
