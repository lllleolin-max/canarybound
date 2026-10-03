"""Rebuild the three direct-parent correction pairs using unchanged probes."""
import argparse
import json
from pathlib import Path
import subprocess
from verify_wheel import verify

PAIRS = [
    ("stream_types", "7d375b12b7eb5bc50120d03c44637a3c7b1c4db3", "71f6671bc59b931e40dafdd307777cf9dbe04b8f", "probe_stream_types.py", 43, 44),
    ("extreme_identity", "71f6671bc59b931e40dafdd307777cf9dbe04b8f", "11946879194600a1f397896e52989dca9761c69e", "probe_extreme_identity.py", 44, 45),
    ("decimal_context", "11946879194600a1f397896e52989dca9761c69e", "7a5ebeef06742abc3a5be27eb39bc5a0b196bf45", "probe_decimal_context.py", 45, 46),
]


def replay():
    root = Path(__file__).resolve().parent.parent
    results = []
    for name, parent, child, probe, before_count, after_count in PAIRS:
        actual_parent = subprocess.check_output(["git", "rev-parse", child + "^"], cwd=root, text=True).strip()
        if actual_parent != parent:
            raise AssertionError("correction is not a direct child")
        before = verify(parent, root / "tools" / probe)
        after = verify(child, root / "tools" / probe)
        assert before["suite_exit"] == after["suite_exit"] == 0
        assert (before["suite_count"], after["suite_count"]) == (before_count, after_count)
        assert before["probe"]["exit"] == 1 and after["probe"]["exit"] == 0
        assert before["probe"]["sha256"] == after["probe"]["sha256"]
        results.append({"name": name, "before": before, "after": after})
        print(json.dumps({"pair": name, "before_probe": "FAIL", "after_probe": "PASS"}), flush=True)
    return {"pairs": results, "all_passed": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="tmp/history-replay.json")
    args = parser.parse_args()
    result = replay()
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
