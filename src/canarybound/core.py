"""Fixed-stratum evidence. Every public entry point validates its inputs.

Bounds use 80-digit Decimal outward enclosures. Deterministic arithmetic is
exactly rational before directed rounding; ln/sqrt are correctly rounded by
Decimal and expanded one representable value. No platform libm is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, localcontext
from enum import Enum
from fractions import Fraction
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

MAX_EVENTS = 100_000
MAX_STRATA = 32
MAX_ID = 128
PRECISION = 80
MODEL = "iid-stationary-per-cell"
ENROLLMENT = "fixed-independent-of-outcomes"
FILTER = "all-assigned-no-outcome-filter"


class CanaryBoundError(ValueError):
    """Invalid evidence: no statistical result should be used."""


class Status(str, Enum):
    ACCEPTABLE = "ACCEPTABLE"
    HARMFUL = "HARMFUL"
    INCONCLUSIVE = "INCONCLUSIVE"


def number(value: Any, name: str) -> Fraction:
    """Interpret declared decimal numbers exactly, within explicit resource caps."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal, Fraction)):
        raise CanaryBoundError(f"{name}: expected a decimal number, never bool")
    if isinstance(value, Fraction):
        if max(value.numerator.bit_length(), value.denominator.bit_length()) > 34_000:
            raise CanaryBoundError(f"{name}: numeric resource limit")
        return value
    if isinstance(value, int) and value.bit_length() > 426:
        raise CanaryBoundError(f"{name}: integer resource limit")
    if isinstance(value, float) and not math.isfinite(value):
        raise CanaryBoundError(f"{name}: nonfinite number")
    if isinstance(value, str) and (len(value) > 256 or not re.fullmatch(
            r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value)):
        raise CanaryBoundError(f"{name}: invalid or oversized decimal")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except (ValueError, InvalidOperation, OverflowError) as exc:
        raise CanaryBoundError(f"{name}: invalid decimal") from exc
    if not dec.is_finite() or len(dec.as_tuple().digits) > 128 or abs(dec.as_tuple().exponent) > 10_000:
        raise CanaryBoundError(f"{name}: nonfinite or oversized decimal")
    return Fraction(dec)


def timestamp(value: Any, name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
            raise CanaryBoundError(f"{name}: timezone-aware timestamp required")
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as exc:
        raise CanaryBoundError(f"{name}: invalid aware ISO timestamp") from exc


def identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise CanaryBoundError(f"{name}: expected 1..128 ASCII ID characters")
    return value


def strict_keys(data: Any, required: set[str], name: str) -> Mapping:
    if not isinstance(data, Mapping) or set(data) != required:
        raise CanaryBoundError(f"{name}: fields must be {', '.join(sorted(required))}")
    return data


@dataclass(frozen=True)
class Manifest:
    name: str
    declared_at: datetime
    strata: tuple[tuple[str, Fraction], ...]
    alpha: Fraction
    acceptable_margin: Fraction
    harmful_margin: Fraction
    model: str = MODEL
    enrollment: str = ENROLLMENT
    outcome_filter: str = FILTER

    def as_dict(self) -> dict:
        return {"name": self.name, "declared_at": self.declared_at.isoformat(),
                "strata": {s: str(w.numerator) + "/" + str(w.denominator) for s, w in self.strata},
                "alpha": str(self.alpha), "acceptable_margin": str(self.acceptable_margin),
                "harmful_margin": str(self.harmful_margin), "model": self.model,
                "enrollment": self.enrollment, "outcome_filter": self.outcome_filter}


def _validated(manifest: Manifest) -> Manifest:
    if not isinstance(manifest, Manifest):
        raise CanaryBoundError("expected Manifest from make_manifest")
    try:
        name = identifier(manifest.name, "manifest name")
        declared_at = timestamp(manifest.declared_at, "declared_at")
        if not isinstance(manifest.strata, tuple) or not 1 <= len(manifest.strata) <= MAX_STRATA:
            raise CanaryBoundError("strata: expected 1..32 immutable entries")
        strata = tuple((identifier(s, "stratum"), number(w, "weight")) for s, w in manifest.strata)
        if len({s for s, _ in strata}) != len(strata) or any(w < 0 for _, w in strata) or sum(w for _, w in strata) != 1:
            raise CanaryBoundError("strata: unique names and exact nonnegative weights summing to 1 required")
        alpha = number(manifest.alpha, "alpha")
        a = number(manifest.acceptable_margin, "acceptable_margin")
        h = number(manifest.harmful_margin, "harmful_margin")
        if not 0 < alpha < 1 or not -1 <= a <= h <= 1:
            raise CanaryBoundError("require 0 < alpha < 1 and -1 <= acceptable <= harmful <= 1")
        if (manifest.model, manifest.enrollment, manifest.outcome_filter) != (MODEL, ENROLLMENT, FILTER):
            raise CanaryBoundError("unsupported sampling model, adaptive enrollment or outcome filter")
        return Manifest(name, declared_at, tuple(sorted(strata)), alpha, a, h)
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, CanaryBoundError):
            raise
        raise CanaryBoundError("malformed constructed Manifest") from exc


def make_manifest(data: Mapping) -> Manifest:
    fields = {"name", "declared_at", "strata", "alpha", "acceptable_margin", "harmful_margin",
              "model", "enrollment", "outcome_filter"}
    strict_keys(data, fields, "manifest")
    if not isinstance(data["strata"], Mapping):
        raise CanaryBoundError("strata: expected object")
    return _validated(Manifest(data["name"], data["declared_at"], tuple(data["strata"].items()),
                               data["alpha"], data["acceptable_margin"], data["harmful_margin"],
                               data["model"], data["enrollment"], data["outcome_filter"]))


def fingerprint(manifest: Manifest) -> str:
    canonical = _validated(manifest).as_dict()
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _decimal(value: Fraction, rounding: str) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = rounding
        return Decimal(value.numerator) / Decimal(value.denominator)


@dataclass(frozen=True)
class Interval:
    lower: Decimal
    upper: Decimal

    def as_dict(self) -> dict[str, str]:
        return {"lower": str(self.lower), "upper": str(self.upper)}

    def contains(self, value: Any) -> bool:
        v = number(value, "value")
        return Fraction(self.lower) <= v <= Fraction(self.upper)


def _ratio_interval(s: int, m: int, n: int) -> Interval:
    if n == 0:
        return Interval(Decimal(0), Decimal(1))
    return Interval(_decimal(Fraction(s, n), ROUND_FLOOR), _decimal(Fraction(s + m, n), ROUND_CEILING))


def radius(n: int, alpha: Any, streams: int, *, sequential: bool = True) -> Decimal:
    """An outward upper enclosure of the Hoeffding radius, without huge products."""
    _counts(n=n, s=0, m=0)
    if isinstance(streams, bool) or not isinstance(streams, int) or not 1 <= streams <= 2 * MAX_STRATA:
        raise CanaryBoundError("streams: expected integer 1..64")
    a = number(alpha, "alpha")
    if not 0 < a < 1:
        raise CanaryBoundError("alpha must lie strictly between 0 and 1")
    if n == 0:
        return Decimal(1)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = ROUND_CEILING
        # Decimal ln and sqrt are correctly rounded nearest even, regardless of
        # context rounding. next_plus provides a conservative upper enclosure.
        alpha_lower = _decimal(a, ROUND_FLOOR)
        minus_log_alpha = (-alpha_lower.ln().next_minus()).next_plus()
        terms = [Decimal(2 * streams).ln().next_plus(), minus_log_alpha]
        if sequential:
            terms += [Decimal(n).ln().next_plus(), Decimal(n + 1).ln().next_plus()]
        log_upper = sum(terms, Decimal(0))
        square_upper = log_upper / Decimal(2 * n)
        return square_upper.sqrt().next_plus()


def _counts(*, n: int, s: int, m: int) -> None:
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_EVENTS for v in (n, s, m)):
        raise CanaryBoundError("counts: integers in 0..100000 required")
    if s + m > n:
        raise CanaryBoundError("observed adverse plus pending exceeds assigned count")


def stream_bounds(n: int, s: int, m: int, alpha: Any, streams: int,
                  *, sequential: bool = True) -> tuple[Interval, Interval]:
    """(finite assigned-cohort completion, population confidence) enclosures."""
    _counts(n=n, s=s, m=m)
    epsilon = radius(n, alpha, streams, sequential=sequential)
    finite = _ratio_interval(s, m, n)
    if not n:
        return finite, finite
    with localcontext() as ctx:
        ctx.prec = PRECISION
        ctx.rounding = ROUND_FLOOR
        lower = max(Decimal(0), finite.lower - epsilon)
        ctx.rounding = ROUND_CEILING
        upper = min(Decimal(1), finite.upper + epsilon)
    return finite, Interval(lower, upper)


def _weighted_difference(cells: Mapping, strata: tuple, field: str) -> Interval:
    low = Fraction(0)
    high = Fraction(0)
    for stratum, weight in strata:
        if weight == 0:
            continue
        ca, co = cells[(stratum, "canary")][field], cells[(stratum, "control")][field]
        low += weight * (Fraction(ca.lower) - Fraction(co.upper))
        high += weight * (Fraction(ca.upper) - Fraction(co.lower))
    return Interval(_decimal(low, ROUND_FLOOR), _decimal(high, ROUND_CEILING))


def _status(bounds: Interval, manifest: Manifest) -> Status:
    if Fraction(bounds.upper) <= manifest.acceptable_margin:
        return Status.ACCEPTABLE
    if Fraction(bounds.lower) > manifest.harmful_margin:
        return Status.HARMFUL
    return Status.INCONCLUSIVE


@dataclass(frozen=True)
class Evidence:
    manifest_id: str
    method: str
    at: datetime
    finite_completion: Interval
    population: Interval
    finite_status: Status
    population_status: Status
    cells: tuple[tuple[str, str, int, int, int, Interval, Interval], ...]

    def as_dict(self) -> dict:
        return {"schema": "canarybound-evidence-v1", "manifest_id": self.manifest_id,
                "method": self.method,
                "coverage": "time-uniform under declared model" if self.method == "sequential-pending" else
                            "ablation only: no repeat-look or informative-delay guarantee",
                "at": self.at.isoformat(), "estimand": "fixed-target-weighted-adverse-canary-minus-control",
                "finite_completion": {**self.finite_completion.as_dict(), "status": self.finite_status.value},
                "population": {**self.population.as_dict(), "status": self.population_status.value,
                               "conditional_on": [MODEL, ENROLLMENT, FILTER]},
                "cells": [{"stratum": s, "arm": arm, "assigned": n, "observed_adverse": bad,
                           "pending": pending, "finite_completion": finite.as_dict(), "population": pop.as_dict()}
                          for s, arm, n, bad, pending, finite, pop in self.cells],
                "interpretation": "Statistical evidence only; no causal effect or operational rollout safety claim."}


def analyze(manifest: Manifest, events: Iterable[Mapping], at: Any,
            *, method: str = "sequential-pending") -> Evidence:
    """Analyze an immutable snapshot; log ordering does not define event times.

    `method` is for explicit ablations. `fixed-pending` spends alpha at each
    fixed sample and has no repeat-look guarantee. `completed-only` discards
    pending outcomes and is invalid for arbitrary informative revelation.
    """
    manifest = _validated(manifest)
    manifest_id = fingerprint(manifest)
    look = timestamp(at, "look")
    if look < manifest.declared_at:
        raise CanaryBoundError("look precedes manifest declaration")
    if method not in {"sequential-pending", "fixed-pending", "completed-only"}:
        raise CanaryBoundError("unknown analysis method")
    assignments: dict[str, tuple[str, str, datetime]] = {}
    outcomes: dict[str, tuple[int, datetime]] = {}
    strata_names = {s for s, _ in manifest.strata}
    for index, raw in enumerate(events):
        if index >= MAX_EVENTS:
            raise CanaryBoundError("event resource limit: at most 100000 events")
        if not isinstance(raw, Mapping):
            raise CanaryBoundError("event must be an object")
        kind = raw.get("type")
        keys = {"type", "id", "manifest_id", "at"} | ({"arm", "stratum"} if kind == "assign" else {"bad"})
        strict_keys(raw, keys, "event")
        if raw["manifest_id"] != manifest_id:
            raise CanaryBoundError("manifest identity mismatch; predeclared policy cannot change")
        uid = identifier(raw["id"], "event id")
        time = timestamp(raw["at"], "event time")
        if time < manifest.declared_at:
            raise CanaryBoundError("event precedes manifest declaration")
        if kind == "assign":
            if uid in assignments:
                raise CanaryBoundError("duplicate assignment ID")
            stratum = identifier(raw["stratum"], "stratum")
            arm = identifier(raw["arm"], "arm")
            if stratum not in strata_names or arm not in {"canary", "control"}:
                raise CanaryBoundError("unknown arm/stratum stream")
            assignments[uid] = (stratum, arm, time)
        elif kind == "outcome":
            if uid in outcomes:
                raise CanaryBoundError("duplicate outcome ID")
            if type(raw["bad"]) is not int or raw["bad"] not in (0, 1):
                raise CanaryBoundError("bad must be integer 0 or 1")
            outcomes[uid] = (raw["bad"], time)
        else:
            raise CanaryBoundError("unknown event type")
    for uid, (_, observed_at) in outcomes.items():
        if uid not in assignments:
            raise CanaryBoundError("outcome has no assignment")
        if observed_at < assignments[uid][2]:
            raise CanaryBoundError("outcome precedes assignment")
    counts = {(s, arm): [0, 0, 0] for s, _ in manifest.strata for arm in ("canary", "control")}
    for uid, (stratum, arm, assigned_at) in assignments.items():
        if assigned_at > look:
            continue
        count = counts[(stratum, arm)]
        count[0] += 1
        outcome = outcomes.get(uid)
        if outcome is None or outcome[1] > look:
            count[2] += 1
        else:
            count[1] += outcome[0]
    streams = 2 * sum(w > 0 for _, w in manifest.strata)
    cells = {}
    rows = []
    for (stratum, arm), (n, s, m) in counts.items():
        # Zero-weight cells are reported but do not consume the union budget.
        calc_n, calc_m = (n - m, 0) if method == "completed-only" else (n, m)
        finite, pop = stream_bounds(calc_n, s, calc_m, manifest.alpha, streams,
                                    sequential=method == "sequential-pending")
        cells[(stratum, arm)] = {"finite": finite, "population": pop}
        rows.append((stratum, arm, n, s, m, finite, pop))
    finite = _weighted_difference(cells, manifest.strata, "finite")
    population = _weighted_difference(cells, manifest.strata, "population")
    return Evidence(manifest_id, method, look, finite, population, _status(finite, manifest),
                    _status(population, manifest), tuple(rows))
