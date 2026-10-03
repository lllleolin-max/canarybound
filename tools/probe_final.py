"""Composite final installed-SDK probe, independent of archive test discovery."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
failures = []
for name in ("probe_stream_types.py", "probe_extreme_identity.py", "probe_decimal_context.py"):
    result = subprocess.run([sys.executable, str(root / name)], capture_output=True, text=True)
    if result.returncode:
        failures.append({"probe": name, "exit": result.returncode})
print(json.dumps({"checks": "all three unchanged historical probes", "failures": failures}, sort_keys=True))
raise SystemExit(bool(failures))
