"""Portable probe unchanged across correction 2's archive wheels."""
import json
from canarybound import analyze, fingerprint, make_manifest
from canarybound.core import MODEL, ENROLLMENT, FILTER

failures = []
for alpha in ("1e-5000", "1e-10000"):
    data = dict(name="synthetic-extreme", declared_at="2026-01-01T00:00:00Z", strata={"s": "1"},
                alpha=alpha, acceptable_margin="0.05", harmful_margin="0.10", model=MODEL,
                enrollment=ENROLLMENT, outcome_filter=FILTER)
    try:
        manifest = make_manifest(data)
        identity = fingerprint(manifest)
        result = analyze(manifest, [], "2026-01-01T00:01:00Z")
        assert len(identity) == 64 and result.manifest_id == identity
        assert result.population.lower == -1 and result.population.upper == 1
    except Exception as exc:
        failures.append({"alpha": alpha, "exception": type(exc).__name__})
print(json.dumps({"checks": 2, "failures": failures}, sort_keys=True))
raise SystemExit(bool(failures))
