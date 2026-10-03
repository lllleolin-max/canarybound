# Contributing

Use Python 3.11+ and `python -m pip install .`; run `python -m unittest discover -s tests -v` against an installed wheel. Add a minimal synthetic failure and independent expected value for changes to bounds or temporal semantics. Never expand the statistical model merely by accepting a new declaration string: provide a proof and executable counterexample/coverage checks. Keep finite completion and population evidence separate. Do not add automatic rollout actions to a statistical label.

The CI matrix checks Ubuntu and Windows on 3.11 and 3.14. A checked-in workflow is not evidence of remote success. Installation verification must use the target interpreter's registered console script from sysconfig, particularly on Windows, where Scripts need not be the executable's parent.

CI builds a single local wheel and runs `python tools/ci_verify.py --wheel-dir dist`. That script installs its explicit pathname with indexes disabled, rejects multiple wheels, associates all package module bytes with canonical Git/source/wheel/site-packages, runs the installed suite outside the checkout and checks the actual registered console against the SDK. Do not replace this step with a package-name install or a source PYTHONPATH test.
