"""Verify an ordinary wheel from a clean Git archive in a fresh environment.

Run from a working checkout: python tools/verify_wheel.py REV [--probe PATH]
The probe is kept outside the archive so identical code can test parent/fix.
Reports omit private local paths and raw pip output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile


def run(cmd, cwd):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    process = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    return process.returncode, process.stdout, process.stderr


def verify(revision, probe=None):
    checkout = Path(__file__).resolve().parent.parent
    sha = subprocess.check_output(["git", "rev-parse", revision], cwd=checkout, text=True).strip()
    with tempfile.TemporaryDirectory(prefix="canarybound-verify-") as tmp:
        root = Path(tmp)
        archive = root / "source.zip"
        subprocess.run(["git", "archive", "--format=zip", f"--output={archive}", sha], cwd=checkout, check=True)
        source = root / "source"
        with zipfile.ZipFile(archive) as package:
            package.extractall(source)
        envdir = root / "env"
        subprocess.run([sys.executable, "-m", "venv", str(envdir)], check=True, capture_output=True)
        python = envdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        wheels = root / "wheels"
        wheels.mkdir()
        code, _, err = run([str(python), "-m", "pip", "wheel", str(source), "--no-deps", "--wheel-dir", str(wheels)], root)
        if code:
            raise RuntimeError("normal isolated wheel build failed")
        wheel = next(wheels.glob("*.whl"))
        code, _, _ = run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)], root)
        if code:
            raise RuntimeError("normal wheel installation failed")
        identity_code = """
import json,sysconfig,importlib.metadata,canarybound
from pathlib import Path
d=importlib.metadata.distribution('canarybound')
script=Path(sysconfig.get_path('scripts'))/('canarybound.exe' if __import__('os').name=='nt' else 'canarybound')
print(json.dumps({'module_root':str(Path(canarybound.__file__).parent),'script':str(script),
                 'entry_points':{e.name:e.value for e in d.entry_points},'python':__import__('platform').python_version()}))
"""
        code, out, _ = run([str(python), "-c", identity_code], root)
        if code:
            raise RuntimeError("installed package import failed")
        identity = json.loads(out)
        installed = Path(identity["module_root"])
        association = {}
        with zipfile.ZipFile(wheel) as package:
            for name in package.namelist():
                if name.startswith("canarybound/") and name.endswith(".py"):
                    relative = name.removeprefix("canarybound/")
                    content = package.read(name)
                    association[name] = hashlib.sha256(content).hexdigest()
                    if (installed / relative).read_bytes() != content or (source / "src" / name).read_bytes() != content:
                        raise RuntimeError(f"byte association failed: {name}")
        if identity["entry_points"].get("canarybound") != "canarybound.cli:main":
            raise RuntimeError("wrong registered console entry point")
        script = identity["script"]
        tests_code, tests_out, tests_err = run([str(python), "-m", "unittest", "discover", "-s", str(source / "tests"), "-v"], root)
        suite = tests_out + tests_err
        count = int(re.search(r"Ran (\d+) tests?", suite).group(1))
        cli_code, cli_out, cli_err = run([script, "compare", "--size", "1000"], root)
        if cli_code:
            raise RuntimeError("installed console contrast failed")
        contrast = json.loads(cli_out)
        examples_code, examples_out, examples_err = run([script, "analyze", str(source / "examples/manifest.json"),
                            str(source / "examples/events.jsonl"), "--at", "2026-01-01T00:03:00Z"], root)
        report = {"sha": sha, "python": identity["python"], "normal_archive_wheel": True,
                  "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                  "installed_module_byte_association": association,
                  "registered_cli": "target sysconfig Scripts/bin canarybound; actual executed entry point",
                  "suite_count": count, "suite_exit": tests_code,
                  "console_contrast": {"exit": cli_code,
                       "early": {k:v["population"]["status"] for k,v in contrast["early"].items()},
                       "late": contrast["late"]["population"]["status"],
                       "all_observed_equal": contrast["all_observed_baseline_equal"]},
                  "example_exit": examples_code}
        if probe:
            probe = Path(probe).resolve()
            pc, po, pe = run([str(python), str(probe)], root)
            # Avoid path-bearing tracebacks: portable probe emits concise JSON.
            report["probe"] = {"sha256": hashlib.sha256(probe.read_bytes()).hexdigest(), "exit": pc,
                               "stdout": po.strip(), "stderr_nonempty": bool(pe.strip())}
        if tests_code:
            report["suite_failures"] = [line.strip() for line in suite.splitlines() if line.startswith(("FAIL:", "ERROR:"))]
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("revision")
    parser.add_argument("--probe")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = verify(args.revision, args.probe)
    text = json.dumps(result, indent=2) + "\n"
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if result["suite_exit"] == 0 else 1)
