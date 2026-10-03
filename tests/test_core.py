import copy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import itertools
import math
import unittest

from canarybound import CanaryBoundError, Manifest, Status, analyze, fingerprint, make_manifest, stream_bounds
from canarybound.core import MAX_EVENTS, radius
from canarybound.experiments import complete_data_baseline, contrast, delayed_fixture, demo_manifest, mc_interval, simulate


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.m = demo_manifest()
        self.identity = fingerprint(self.m)
        self.at = "2026-01-01T00:03:00Z"

    def assignment(self, uid="a", arm="canary", stratum="primary", at="2026-01-01T00:01:00Z"):
        return dict(type="assign", id=uid, arm=arm, stratum=stratum, at=at, manifest_id=self.identity)

    def outcome(self, uid="a", bad=1, at="2026-01-01T00:02:00Z"):
        return dict(type="outcome", id=uid, bad=bad, at=at, manifest_id=self.identity)

    def test_empty(self):
        r = analyze(self.m, [], self.at)
        self.assertEqual(r.population_status, Status.INCONCLUSIVE)
        self.assertEqual((r.finite_completion.lower, r.finite_completion.upper), (-1, 1))

    def test_pending_retained(self):
        r = analyze(self.m, [self.assignment()], self.at)
        self.assertEqual(r.cells[0][2:5], (1, 0, 1))

    def test_past_look_retains_unresolved(self):
        events = [self.assignment(), self.outcome(at="2026-01-02T00:00:00Z")]
        self.assertEqual(analyze(self.m, events, self.at), analyze(self.m, events[:1], self.at))

    def test_future_assignment_excluded(self):
        self.assertEqual(analyze(self.m, [self.assignment(at="2026-01-02T00:00:00Z")], self.at),
                         analyze(self.m, [], self.at))

    def test_future_label_invariance(self):
        a = [self.assignment(), self.outcome(bad=0, at="2026-01-02T00:00:00Z")]
        b = [self.assignment(), self.outcome(bad=1, at="2026-01-02T00:00:00Z")]
        self.assertEqual(analyze(self.m, a, self.at), analyze(self.m, b, self.at))

    def test_reveal_order_invariance(self):
        events = [self.assignment(), self.outcome()]
        self.assertEqual(analyze(self.m, events, self.at), analyze(self.m, events[::-1], self.at))

    def test_permanent_missing(self):
        r = analyze(self.m, [self.assignment()], "2099-01-01T00:00:00Z")
        self.assertEqual(r.cells[0][4], 1)

    def test_duplicate_assignments(self):
        for second in [self.assignment(), self.assignment(arm="control")]:
            with self.assertRaises(CanaryBoundError):
                analyze(self.m, [self.assignment(), second], self.at)

    def test_duplicate_outcomes(self):
        for bad in (0, 1):
            with self.assertRaises(CanaryBoundError):
                analyze(self.m, [self.assignment(), self.outcome(), self.outcome(bad=bad)], self.at)

    def test_outcome_without_assignment(self):
        with self.assertRaises(CanaryBoundError):
            analyze(self.m, [self.outcome()], self.at)

    def test_outcome_before_assignment(self):
        with self.assertRaises(CanaryBoundError):
            analyze(self.m, [self.assignment(), self.outcome(at="2026-01-01T00:00:30Z")], self.at)

    def test_unknown_stream(self):
        for event in [self.assignment(arm="blue"), self.assignment(stratum="absent")]:
            with self.assertRaises(CanaryBoundError):
                analyze(self.m, [event], self.at)

    def test_stream_container_types_rejected(self):
        for field in ("stratum", "arm"):
            for value in ([], {}, 10 ** 5000, True):
                event = self.assignment()
                event[field] = value
                with self.assertRaises(CanaryBoundError):
                    analyze(self.m, [event], self.at)

    def test_aware_utc(self):
        utc = analyze(self.m, [self.assignment()], self.at)
        offset = analyze(self.m, [self.assignment()], "2026-01-01T08:03:00+08:00")
        self.assertEqual(utc, offset)

    def test_naive_timestamp_rejected(self):
        for at in ["2026-01-01T00:03:00", datetime(2026, 1, 1)]:
            with self.assertRaises(CanaryBoundError):
                analyze(self.m, [], at)

    def test_manifest_identity_immutable(self):
        changed = copy.copy(self.m)
        object.__setattr__(changed, "acceptable_margin", Fraction(1, 4))
        with self.assertRaises(CanaryBoundError):
            analyze(changed, [self.assignment()], self.at)

    def test_inputs_not_mutated(self):
        events = [self.assignment(), self.outcome()]
        before = copy.deepcopy(events)
        analyze(self.m, events, self.at)
        self.assertEqual(events, before)

    def test_no_control(self):
        result = analyze(self.m, [self.assignment(), self.outcome(bad=0)], self.at)
        self.assertEqual(result.population_status, Status.INCONCLUSIVE)

    def test_unequal_denominators(self):
        events = [self.assignment("a"), self.outcome("a"), self.assignment("b"), self.assignment("c", "control"), self.outcome("c", 0)]
        result = analyze(self.m, events, self.at)
        self.assertEqual(result.finite_completion.lower, Decimal("0.5"))
        self.assertEqual(result.finite_completion.upper, Decimal(1))

    def test_exact_threshold_convention(self):
        # finite canary-control = 0.05; equality is acceptable, harmful is strict.
        finite, _ = stream_bounds(20, 1, 0, "0.05", 2)
        self.assertEqual(finite.lower, Decimal("0.05"))
        from canarybound.core import _status, Interval
        self.assertEqual(_status(Interval(Decimal("0.05"), Decimal("0.05")), self.m), Status.ACCEPTABLE)
        self.assertEqual(_status(Interval(Decimal("0.10"), Decimal("0.10")), self.m), Status.INCONCLUSIVE)

    def test_manifest_time_before_data(self):
        with self.assertRaises(CanaryBoundError):
            analyze(self.m, [self.assignment(at="2025-01-01T00:00:00Z")], self.at)

    def test_predeclared_model_only(self):
        for field, value in [("model", "drifting"), ("enrollment", "adaptive"), ("outcome_filter", "completed")]:
            changed = copy.copy(self.m)
            object.__setattr__(changed, field, value)
            with self.assertRaises(CanaryBoundError):
                analyze(changed, [], self.at)

    def test_constructed_model_bypass(self):
        empty = object.__new__(Manifest)
        with self.assertRaises(CanaryBoundError):
            analyze(empty, [], self.at)

    def test_bad_bool(self):
        with self.assertRaises(CanaryBoundError):
            analyze(self.m, [self.assignment(), self.outcome(bad=True)], self.at)


class MathTests(unittest.TestCase):
    def test_independent_formula_values(self):
        # Independent 120-digit complete product formula, not production log-sum.
        with localcontext() as ctx:
            ctx.prec = 120
            for n, j, alpha in [(1, 2, "0.05"), (37, 4, "0.01"), (100000, 64, "1e-1000")]:
                expected = (Decimal(2 * j * n * (n + 1) / 1) / Decimal(alpha)).ln()
                expected = (expected / Decimal(2 * n)).sqrt()
                actual = radius(n, alpha, j)
                self.assertGreaterEqual(actual, expected)
                self.assertLess(actual - expected, Decimal("1e-70"))

    def test_error_allocation_telescopes(self):
        alpha = Fraction(1, 20)
        j, counts = 4, 10000
        total = j * sum((alpha / (j * n * (n + 1)) for n in range(1, counts + 1)), Fraction())
        self.assertEqual(total, alpha * counts / (counts + 1))

    def test_exhaustive_missing_completions(self):
        for n in range(1, 7):
            for observed in itertools.product((0, 1, None), repeat=n):
                s = sum(x == 1 for x in observed)
                m = observed.count(None)
                finite, _ = stream_bounds(n, s, m, "0.05", 2)
                for completion in itertools.product((0, 1), repeat=m):
                    self.assertTrue(finite.contains(Fraction(s + sum(completion), n)))

    def test_alpha_extremes(self):
        for alpha in ["1e-10000", "0.999999999999999999999999999999999999999999999999999999999999"]:
            self.assertGreater(radius(100000, alpha, 2), 0)
        for alpha in [True, 0, 1, -1, float("inf"), float("nan"), 10 ** 5000, "1e999999"]:
            with self.assertRaises(CanaryBoundError):
                radius(1, alpha, 2)

    def test_count_resource_and_bool(self):
        for n in [True, -1, MAX_EVENTS + 1, 10 ** 5000, 1.0]:
            with self.assertRaises(CanaryBoundError):
                stream_bounds(n, 0, 0, "0.05", 2)

    def test_zero_weight_strata(self):
        m = demo_manifest({"primary": "1", "excluded": "0"})
        empty = analyze(m, [], "2026-01-01T00:00:01Z")
        self.assertEqual(empty.population.lower, -1)
        self.assertEqual(len(empty.cells), 4)

    def test_strata_fixed_weighting_not_pooling(self):
        m = demo_manifest({"low": "0.25", "high": "0.75"})
        identity = fingerprint(m)
        events = []
        for stratum, n, canary_bad, control_bad in [("low", 2, 0, 1), ("high", 8, 1, 0)]:
            for arm, bad in [("canary", canary_bad), ("control", control_bad)]:
                for i in range(n):
                    uid = f"{stratum}.{arm}.{i}"
                    events += [dict(type="assign", id=uid, arm=arm, stratum=stratum, at="2026-01-01T00:01:00Z", manifest_id=identity),
                               dict(type="outcome", id=uid, bad=bad, at="2026-01-01T00:02:00Z", manifest_id=identity)]
        result = analyze(m, events, "2026-01-01T00:03:00Z")
        self.assertEqual(result.finite_completion.lower, Decimal("0.50"))
        self.assertEqual(result.finite_completion.upper, Decimal("0.50"))

    def test_weights_exact(self):
        for weights in [{"a": ".1", "b": ".8999999999999999"}, {"a": -1, "b": 2}, {"a": True}]:
            with self.assertRaises(CanaryBoundError):
                demo_manifest(weights)

    def test_informative_delay_counterexample(self):
        result = contrast(1000)
        self.assertEqual(result["early"]["completed-only"]["population"]["status"], "ACCEPTABLE")
        self.assertEqual(result["early"]["sequential-pending"]["population"]["status"], "INCONCLUSIVE")
        self.assertEqual(result["late"]["population"]["status"], "HARMFUL")
        self.assertTrue(result["all_observed_baseline_equal"])

    def test_complete_baseline_rejects_pending(self):
        m, events = delayed_fixture(10)
        with self.assertRaises(CanaryBoundError):
            complete_data_baseline(m, events, "2026-01-01T00:03:00Z")

    def test_mc_interval_independent(self):
        out = mc_interval(3, 20)
        eps = math.sqrt(math.log(40) / 40)
        self.assertAlmostEqual(float(out["upper"]), min(1, .15 + eps), places=14)
        with self.assertRaises(CanaryBoundError):
            mc_interval(True, 20)

    def test_seeded_simulation_reproducible(self):
        a = simulate(3, 10, 42)
        self.assertEqual(a, simulate(3, 10, 42))
        self.assertEqual(a["wall_clock_looks_total"], 60)
        self.assertEqual(a["methods"]["sequential-pending"]["any_stream"]["violations"], 0)

    def test_simulation_resource_limits(self):
        for args in [(True, 1, 1), (1, 0, 1), (10000, 2000, 1), (1, 1, 10 ** 5000)]:
            with self.assertRaises(CanaryBoundError):
                simulate(*args)


if __name__ == "__main__":
    unittest.main()
