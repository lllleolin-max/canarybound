"""Install the sole freshly built local wheel and verify actual installed code.

CI: python tools/ci_verify.py --wheel-dir dist
Optional source/repo/ref/python parameters support exact-archive local QA.
No index selection, editable import or source PYTHONPATH is accepted.
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


def run(command, cwd):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        # Useful routine test output, but no raw install logs are persisted.
        if "unittest" in command:
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError("installed-wheel verification command failed")
    return result.stdout, result.stderr


def verify(args):
    source = Path(args.source or Path(__file__).resolve().parent.parent).resolve()
    repo = Path(args.repo or source).resolve()
    wheels = list(Path(args.wheel_dir).resolve().glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("exactly one freshly built wheel is required")
    wheel = wheels[0]
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", args.ref], text=True).strip()
    expected = {}
    for file in sorted((source / "src/canarybound").glob("*.py")):
        name = "canarybound/" + file.name
        blob = subprocess.check_output(["git", "-C", str(repo), "show", sha + ":src/" + name])
        if file.read_bytes() != blob:
            raise RuntimeError("checked-out/archive source differs from canonical Git blob: " + name)
        expected[name] = blob
    if len(expected) != 6:
        raise RuntimeError("expected all six CanaryBound modules")
    with zipfile.ZipFile(wheel) as package:
        names = {name for name in package.namelist() if name.startswith("canarybound/") and name.endswith(".py")}
        if names != set(expected) or any(package.read(name) != blob for name, blob in expected.items()):
            raise RuntimeError("fresh wheel differs from canonical checked-out source")
    with tempfile.TemporaryDirectory(prefix="canarybound-ci-check-") as temporary:
        outside = Path(temporary)
        python = args.python or sys.executable
        # An explicit filepath is installed; --no-index prevents name/version
        # resolution through configured indexes. Reinstall defeats stale copies.
        run([python, "-m", "pip", "install", "--no-index", "--no-deps", "--force-reinstall", wheel], outside)
        metadata_code = """
import canarybound,hashlib,importlib.metadata,json,os,sysconfig
from pathlib import Path
root=Path(canarybound.__file__).resolve().parent
distribution=importlib.metadata.distribution('canarybound')
print(json.dumps({'root':str(root),'purelib':sysconfig.get_path('purelib'),
 'console':str(Path(sysconfig.get_path('scripts'))/('canarybound.exe' if os.name=='nt' else 'canarybound')),
 'entry_points':{e.name:e.value for e in distribution.entry_points},
 'modules':{'canarybound/'+p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.py')}}))
"""
        stdout, _ = run([python, "-I", "-c", metadata_code], outside)
        metadata = json.loads(stdout)
        installed = Path(metadata["root"])
        if installed != (Path(metadata["purelib"]).resolve() / "canarybound"):
            raise RuntimeError("CanaryBound import is not in target interpreter site-packages")
        hashes = {name: hashlib.sha256(blob).hexdigest() for name, blob in expected.items()}
        if metadata["modules"] != hashes:
            raise RuntimeError("installed module inventory/hashes differ from fresh wheel and Git")
        if any((installed / name.removeprefix("canarybound/")).read_bytes() != blob for name, blob in expected.items()):
            raise RuntimeError("installed bytes differ from fresh wheel and Git")
        if metadata["entry_points"].get("canarybound") != "canarybound.cli:main":
            raise RuntimeError("incorrect registered console entry point")
        console = Path(metadata["console"])
        if not console.is_file():
            raise RuntimeError("target-sysconfig registered console does not exist")
        _, suite = run([python, "-I", "-m", "unittest", "discover", "-s", source / "tests", "-v"], outside)
        count = int(re.search(r"Ran (\d+) tests?", suite).group(1))
        manifest, events = source / "examples/manifest.json", source / "examples/events.jsonl"
        identity, _ = run([console, "identity", manifest], outside)
        cli, _ = run([console, "analyze", manifest, events, "--at", "2026-01-01T00:03:00Z"], outside)
        sdk, _ = run([python, "-I", "-c",
            "from canarybound import *;from canarybound.io import *;import json,sys; m=make_manifest(read_manifest(sys.argv[1]));print(json.dumps(analyze(m,read_events(sys.argv[2]),sys.argv[3]).as_dict()))",
            manifest, events, "2026-01-01T00:03:00Z"], outside)
        if json.loads(cli) != json.loads(sdk) or identity.strip() != json.loads(cli)["manifest_id"]:
            raise RuntimeError("actual registered CLI and installed SDK disagree")
        cli_contrast, _ = run([console, "compare", "--size", "1000"], outside)
        sdk_contrast, _ = run([python, "-I", "-c", "import json;from canarybound.experiments import contrast;print(json.dumps(contrast(1000)))"], outside)
        contrast = json.loads(cli_contrast)
        if contrast != json.loads(sdk_contrast) or not contrast["all_observed_baseline_equal"]:
            raise RuntimeError("installed SDK/console contrast failed")
        smoke, _ = run([console, "simulate", "--trials", "20", "--steps", "40", "--seed", "42"], outside)
        return {"sha": sha, "wheel_name": wheel.name,
                "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "install": "explicit single local wheel path; --no-index --no-deps --force-reinstall",
                "all_six_git_blob_source_wheel_site_packages_equal": True, "module_sha256": hashes,
                "ordinary_site_packages": True, "suite_tests": count, "suite_exit": 0,
                "actual_target_sysconfig_console": True, "file_identity_sdk_cli_equal": True,
                "sdk_cli_contrast_equal": True,
                "contrast": {"early": {method:row["population"]["status"] for method,row in contrast["early"].items()},
                             "late": contrast["late"]["population"]["status"]},
                "console_mc_smoke_looks": json.loads(smoke)["wall_clock_looks_total"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel-dir", required=True)
    parser.add_argument("--source")
    parser.add_argument("--repo")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--python")
    parser.add_argument("--report")
    args = parser.parse_args()
    result = verify(args)
    content = json.dumps(result, indent=2) + "\n"
    if args.report:
        destination = Path(args.report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    print(content, end="")
