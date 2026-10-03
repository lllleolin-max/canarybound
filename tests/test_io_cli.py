from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from canarybound import CanaryBoundError
from canarybound.cli import main
from canarybound.io import loads, protect_output, read_events, read_manifest
from canarybound.experiments import demo_manifest
from canarybound.core import ENROLLMENT, FILTER, MODEL


def manifest_data():
    return dict(name="synthetic-demo", declared_at="2026-01-01T00:00:00Z", strata={"primary": "1"},
                alpha="0.05", acceptable_margin="0.05", harmful_margin="0.10",
                model=MODEL, enrollment=ENROLLMENT, outcome_filter=FILTER)


class IOTests(unittest.TestCase):
    def test_duplicate_json_fields(self):
        with self.assertRaises(CanaryBoundError):
            loads('{"alpha": .1, "alpha": .2}')

    def test_oversized_integer(self):
        with self.assertRaises(CanaryBoundError):
            loads('{"alpha": ' + '1' * 5000 + '}')

    def test_nonfinite_json(self):
        with self.assertRaises(CanaryBoundError):
            loads('{"alpha": NaN}')

    def test_log_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "log.jsonl"
            path.write_text("1" * 5000, encoding="utf-8")
            with self.assertRaises(CanaryBoundError):
                list(read_events(path))

    def test_output_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.json"
            path.write_text("source", encoding="utf-8")
            for output in [path, path.parent / "." / path.name]:
                with self.assertRaises(CanaryBoundError):
                    protect_output(output, [path])
            hard = path.parent / "hard.json"
            os.link(path, hard)
            with self.assertRaises(CanaryBoundError):
                protect_output(hard, [path])

    def test_actual_cli_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            events = Path(tmp) / "events.jsonl"
            path.write_text(json.dumps(manifest_data()), encoding="utf-8")
            events.write_text("", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["analyze", str(path), str(events), "--at", "2026-01-01T00:03:00Z"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["population"]["status"], "INCONCLUSIVE")

    def test_error_cli(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["identity", "nonexistent.json"]), 2)


if __name__ == "__main__":
    unittest.main()
