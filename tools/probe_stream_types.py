"""Portable probe unchanged across correction 1's archive wheels."""
import json
from canarybound import CanaryBoundError, analyze, fingerprint
from canarybound.experiments import demo_manifest

manifest = demo_manifest()
failures = []
for field, value in [("stratum", []), ("stratum", {}), ("arm", []), ("arm", {})]:
    event = dict(type="assign", id="synthetic.x", arm="canary", stratum="primary",
                 at="2026-01-01T00:01:00Z", manifest_id=fingerprint(manifest))
    event[field] = value
    try:
        analyze(manifest, [event], "2026-01-01T00:03:00Z")
    except CanaryBoundError:
        continue
    except Exception as exc:
        failures.append({"field": field, "value_type": type(value).__name__, "exception": type(exc).__name__})
    else:
        failures.append({"field": field, "value_type": type(value).__name__, "exception": "accepted"})
print(json.dumps({"checks": 4, "failures": failures}, sort_keys=True))
raise SystemExit(bool(failures))
