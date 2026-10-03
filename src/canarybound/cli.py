"""Registered console command. Domain/input errors exit 2; evidence exits 0."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .core import CanaryBoundError, analyze, fingerprint, make_manifest
from .io import protect_output, read_events, read_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(prog="canarybound")
    sub = parser.add_subparsers(dest="command", required=True)
    identity = sub.add_parser("identity", help="print immutable predeclared manifest fingerprint")
    identity.add_argument("manifest")
    run = sub.add_parser("analyze", help="emit population and finite completion evidence")
    run.add_argument("manifest")
    run.add_argument("events")
    run.add_argument("--at", required=True, help="aware ISO wall-clock look")
    destination = run.add_mutually_exclusive_group()
    destination.add_argument("--output", help="write aggregate JSON; may not alias sources")
    destination.add_argument("--stdout", action="store_true", help="emit to stdout (default)")
    compare = sub.add_parser("compare", help="run synthetic informative-delay and complete-data contrasts")
    compare.add_argument("--size", type=int, default=1000)
    simulate = sub.add_parser("simulate", help="seeded repeated-look iid coverage experiment")
    simulate.add_argument("--trials", type=int, default=500)
    simulate.add_argument("--steps", type=int, default=200)
    simulate.add_argument("--seed", type=int, default=20261003)
    args = parser.parse_args(argv)
    try:
        if args.command == "identity":
            print(fingerprint(make_manifest(read_manifest(args.manifest))))
        elif args.command == "analyze":
            manifest = make_manifest(read_manifest(args.manifest))
            destination = protect_output(args.output, [args.manifest, args.events]) if args.output else None
            result = analyze(manifest, read_events(args.events), args.at).as_dict()
            content = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
            if destination:
                destination.write_text(content, encoding="utf-8")
            else:
                print(content, end="")
        elif args.command == "compare":
            from .experiments import contrast
            print(json.dumps(contrast(args.size), indent=2))
        else:
            from .experiments import simulate
            print(json.dumps(simulate(args.trials, args.steps, args.seed), indent=2))
        return 0
    except (CanaryBoundError, OSError, UnicodeError) as exc:
        print(f"canarybound: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
