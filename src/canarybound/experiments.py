"""Synthetic contrasts and repeated-look iid experiments, never safety validation."""
from __future__ import annotations
from collections import deque
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from fractions import Fraction
import math
import random
from .core import (CanaryBoundError, ENROLLMENT, FILTER, MODEL, MAX_EVENTS,
                   PRECISION, Interval, analyze, bound_context, fingerprint, make_manifest, radius)


def demo_manifest(strata=None):
    return make_manifest({"name": "synthetic-demo", "declared_at": "2026-01-01T00:00:00Z",
                          "strata": strata or {"primary": "1"}, "alpha": "0.05",
                          "acceptable_margin": "0.05", "harmful_margin": "0.10",
                          "model": MODEL, "enrollment": ENROLLMENT, "outcome_filter": FILTER})


def delayed_fixture(size=1000):
    if isinstance(size, bool) or not isinstance(size, int) or not 10 <= size <= MAX_EVENTS // 4:
        raise CanaryBoundError("fixture size must be integer 10..25000")
    manifest = demo_manifest()
    identity = fingerprint(manifest)
    events = []
    for arm in ("canary", "control"):
        for i in range(size):
            uid = f"{arm}.{i}"
            bad = int(i < size * (0.6 if arm == "canary" else 0.1))
            events.append({"type": "assign", "id": uid, "manifest_id": identity,
                           "arm": arm, "stratum": "primary", "at": "2026-01-01T00:01:00Z"})
            events.append({"type": "outcome", "id": uid, "manifest_id": identity, "bad": bad,
                           "at": "2026-01-02T00:00:00Z" if arm == "canary" and bad else "2026-01-01T00:02:00Z"})
    return manifest, events


def complete_data_baseline(manifest, events, at):
    result = analyze(manifest, events, at)
    if any(row[4] for row in result.cells if dict(manifest.strata)[row[0]] > 0):
        raise CanaryBoundError("complete-data baseline requires no pending target outcomes")
    return result


def contrast(size=1000):
    manifest, events = delayed_fixture(size)
    early = "2026-01-01T00:03:00Z"
    late = "2026-01-03T00:00:00Z"
    complete = analyze(manifest, events, late)
    baseline = complete_data_baseline(manifest, events, late)
    return {"synthetic": True, "size_per_arm": size,
            "shared_policy": {"weights": {"primary": "1"}, "alpha": "0.05",
                              "acceptable_margin": "0.05", "harmful_margin": "0.10"},
            "early": {method: analyze(manifest, events, early, method=method).as_dict()
                      for method in ("sequential-pending", "fixed-pending", "completed-only")},
            "late": complete.as_dict(),
            "all_observed_baseline_equal": complete.as_dict() == baseline.as_dict(),
            "disclosures": ["The same assignments, outcomes, target weights and margins feed every method.",
                            "completed-only deletes delayed adverse outcomes: this violates its sampling assumptions.",
                            "fixed-pending is a fixed-count Hoeffding ablation; repeated looks have no advertised coverage.",
                            "No incumbent performance or production rollout safety claim."]}


def mc_interval(violations, trials):
    if any(type(x) is not int for x in (violations, trials)) or not 1 <= trials <= 100000 or not 0 <= violations <= trials:
        raise CanaryBoundError("MC counts require 0 <= violations <= trials <= 100000")
    with bound_context() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = ROUND_CEILING
        eps = (Decimal(40).ln().next_plus() / Decimal(2 * trials)).sqrt().next_plus()
        ctx.rounding = ROUND_FLOOR
        low = max(Decimal(0), Decimal(violations) / Decimal(trials) - eps)
        ctx.rounding = ROUND_CEILING
        high = min(Decimal(1), Decimal(violations) / Decimal(trials) + eps)
    return Interval(low, high).as_dict()


def simulate(trials=500, steps=200, seed=20261003):
    """Every trial checks every stream and weighted difference at every look.

    Enrollment is fixed: one iid draw from each of four stationary Bernoulli
    streams per step. Good outcomes reveal immediately; bad outcomes reveal
    after 7 steps, except each fifth bad ID remains permanently pending.
    """
    if type(trials) is not int or type(steps) is not int or not 1 <= trials <= 10000 or not 1 <= steps <= 2000 or trials * steps > 2_000_000:
        raise CanaryBoundError("simulation limit: trials 1..10000, steps 1..2000, product <= 2000000")
    if type(seed) is not int or seed.bit_length() > 128:
        raise CanaryBoundError("seed must be integer with at most 128 bits")
    rng = random.Random(seed)
    probabilities = (Fraction(1, 10), Fraction(3, 10), Fraction(3, 5), Fraction(1, 5))
    weights = (Fraction(1, 4), Fraction(3, 4))
    theta = sum(weights[i] * (probabilities[2 * i] - probabilities[2 * i + 1]) for i in range(2))
    radii = {method: [radius(n, "0.05", 4, sequential=(method == "sequential-pending"))
                     for n in range(steps + 1)]
             for method in ("sequential-pending", "fixed-pending", "completed-only")}
    violations = {method: {"any_stream": 0, "weighted_difference": 0} for method in radii}
    look_count = 0
    for _ in range(trials):
        observed = [0] * 4
        pending = [0] * 4
        scheduled = [deque() for _ in probabilities]
        failed_streams = {m: False for m in radii}
        failed_diff = {m: False for m in radii}
        for n in range(1, steps + 1):
            for i, p in enumerate(probabilities):
                bad = rng.random() < float(p)
                if bad:
                    pending[i] += 1
                    if n % 5:
                        scheduled[i].append(n + 7)
            # Two wall-clock looks at each enrollment count: before and after
            # scheduled revelation. This includes unresolved past looks.
            for phase in (0, 1):
                if phase:
                    for i in range(4):
                        while scheduled[i] and scheduled[i][0] <= n:
                            scheduled[i].popleft()
                            pending[i] -= 1
                            observed[i] += 1
                look_count += 1
                for method in radii:
                    intervals = []
                    for i in range(4):
                        dn, dm = (n - pending[i], 0) if method == "completed-only" else (n, pending[i])
                        if dn == 0:
                            interval = (Fraction(0), Fraction(1))
                        else:
                            eps = Fraction(radii[method][dn])
                            interval = (max(Fraction(0), Fraction(observed[i], dn) - eps),
                                        min(Fraction(1), Fraction(observed[i] + dm, dn) + eps))
                        intervals.append(interval)
                        if not interval[0] <= probabilities[i] <= interval[1]:
                            failed_streams[method] = True
                    low = sum(weights[i] * (intervals[2 * i][0] - intervals[2 * i + 1][1]) for i in range(2))
                    high = sum(weights[i] * (intervals[2 * i][1] - intervals[2 * i + 1][0]) for i in range(2))
                    if not low <= theta <= high:
                        failed_diff[method] = True
        for method in radii:
            violations[method]["any_stream"] += failed_streams[method]
            violations[method]["weighted_difference"] += failed_diff[method]
    return {"synthetic": True, "seed": seed, "trials": trials, "enrollment_steps_per_stream": steps,
            "wall_clock_looks_total": look_count, "alpha": "0.05", "streams": 4,
            "probabilities": [str(p) for p in probabilities], "weights": [str(w) for w in weights],
            "population_difference": str(theta),
            "model": "fixed enrollment; independent stationary Bernoulli per stream; outcome-dependent/permanent delays",
            "methods": {method: {metric: {"violations": count, "trials": trials,
                                           "mc_95_hoeffding_interval": mc_interval(count, trials)}
                                  for metric, count in values.items()} for method, values in violations.items()},
            "disclosure": "Seeded simulation is not a proof. Completed-only is assumption-violating here; fixed-pending is not time-uniform."}
