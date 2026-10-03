# Reproducible validation and evidence boundary

At code correction SHA `7a5ebeef06742abc3a5be27eb39bc5a0b196bf45`, all three direct-parent archive pairs reproduced their expected FAIL→PASS portable probes. Each side also passed its existing full suite (43/44, 44/45, 45/46). [ITERATIONS](ITERATIONS.md) and six per-side JSON logs record actual SHAs, suite counts, matching probe hashes, normal isolated wheels, installed module byte association and actual registered console execution. The replay driver reruns all pairs and records [history-replay.json](history-replay.json).

The final suite adds six checks for the actual 100000-event limit, 64-KiB manifest limit, deep invalid manifest shapes, constructed-model bypass with malformed numeric values, large exact-rational weights and a four-stream weighted missing-completion oracle. This brings the full suite to 52 tests. Exhaustive binary missing completion enumeration and independent 120-digit formula values remain included. Tests run against a fresh installed wheel in final verification; editable/source imports are not accepted as install evidence.

```sh
python tools/verify_wheel.py HEAD --probe tools/probe_final.py --experiments --report tmp/final-verification.json
python tools/replay_history.py --report tmp/history-replay.json
```

The first command archives exact HEAD, builds a normal wheel through isolated setuptools, installs into a fresh venv, checks every installed package `.py` against wheel and archive bytes, runs the full archived suite, executes the target-sysconfig registered console contrast/file example, runs the unchanged probes, executes 500-trial coverage via the actual console script and compares SDK/console contrast JSON. It deliberately writes the latest exact-HEAD result to ignored `tmp/` because a tracked report cannot contain its own future Git SHA. Raw pip output and private interpreter/temp paths are not stored in public evidence.

[coverage-experiment.json](coverage-experiment.json) and [contrast-experiment.json](contrast-experiment.json) are measured synthetic source-run artifacts from the named code SHA. SDK/console execution is checked separately. The completed-only arm is intentionally assumption-violating under informative delays. The repeated fixed-count method has no advertised repeat-look confidence guarantee. The all-observed complete-data baseline is identical to the main method. No synthetic benchmark establishes incumbent superiority, production safety, causal effects, customers, revenue, adoption or willingness to pay. Current commercial validation remains unknown.

The GitHub Actions matrix covers Ubuntu/Windows and Python 3.11/3.14. Local evidence here is Windows 3.14.3. Remote jobs have not been run by the builder; root publication and actual CI checks remain necessary. No repository is published by this builder and no acceptance score is asserted.
