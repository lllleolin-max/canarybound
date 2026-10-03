"""Portable probe unchanged across correction 3's archive wheels."""
from decimal import Inexact, ROUND_DOWN, localcontext
import json
from canarybound import analyze, fingerprint
from canarybound.core import radius
from canarybound.experiments import demo_manifest, mc_interval

m = demo_manifest()
event = dict(type="assign", id="synthetic.x", arm="canary", stratum="primary",
             at="2026-01-01T00:01:00Z", manifest_id=fingerprint(m))
reference = (radius(37, "0.05", 2), radius(37, "1e-10000", 2),
             analyze(m, [event], "2026-01-01T00:03:00Z"), mc_interval(2, 100))
failures = []
with localcontext() as ctx:
    ctx.prec = 4
    ctx.Emax = 9
    ctx.Emin = -9
    ctx.rounding = ROUND_DOWN
    ctx.traps[Inexact] = True
    before = (ctx.prec, ctx.Emax, ctx.Emin, ctx.rounding, dict(ctx.traps), dict(ctx.flags))
    for index, call in enumerate((lambda: radius(37, "0.05", 2), lambda: radius(37, "1e-10000", 2),
                                  lambda: analyze(m, [event], "2026-01-01T00:03:00Z"), lambda: mc_interval(2, 100))):
        try:
            assert call() == reference[index]
        except Exception as exc:
            failures.append({"check": index, "exception": type(exc).__name__})
    after = (ctx.prec, ctx.Emax, ctx.Emin, ctx.rounding, dict(ctx.traps), dict(ctx.flags))
    if before != after:
        failures.append({"check": "operator-context", "exception": "mutated"})
print(json.dumps({"checks": 5, "failures": failures}, sort_keys=True))
raise SystemExit(bool(failures))
