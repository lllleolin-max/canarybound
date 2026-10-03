# Review and correction record

Builder: GPT-6.1 SOL / Ultra. Verification environment: Windows, Python 3.14.3, 2026-10-03. These are builder self-review corrections, not an independent acceptance or score. Initial implementation: `7d375b12b7eb5bc50120d03c44637a3c7b1c4db3`, 43 passing tests.

Every pair below uses ordinary `git archive` source, isolated `pip wheel` builds and fresh venv installs. No editable imports or transplanted old probes are used. The same current portable probe is external to both archives; its SHA-256 is recorded on each side. Every archived existing suite passed; the independent added probe exposed a previously untested defect. Every correction is its before commit's direct child. All installed package `.py` bytes are associated with archive source and wheel payload. The actual registered console executable is found from the target interpreter's `sysconfig.get_path('scripts')` and executed. Logs omit private paths.

| Correction | Before SHA / suite | Direct child SHA / suite | Unchanged probe | Observed result |
|---|---|---|---|---|
| 1 stream type validation | `7d375b12b7eb5bc50120d03c44637a3c7b1c4db3` / 43 | `71f6671bc59b931e40dafdd307777cf9dbe04b8f` / 44 | `tools/probe_stream_types.py` | BEFORE exit 1, AFTER exit 0 |
| 2 extreme-alpha identity | `71f6671bc59b931e40dafdd307777cf9dbe04b8f` / 44 | `11946879194600a1f397896e52989dca9761c69e` / 45 | `tools/probe_extreme_identity.py` | BEFORE exit 1, AFTER exit 0 |
| 3 caller numeric context | `11946879194600a1f397896e52989dca9761c69e` / 45 | `7a5ebeef06742abc3a5be27eb39bc5a0b196bf45` / 46 | `tools/probe_decimal_context.py` | BEFORE exit 1, AFTER exit 0 |

1. New malformed-object review found list/dict arm and stratum values raised raw `TypeError` during set membership. SDK users received an inconsistent exception and the CLI could print a traceback. The correction validates stream scalar IDs before membership. Four unchanged list/dict cases failed in the parent and all rejected with `CanaryBoundError` in the child; regression coverage also includes bool and a 5000-digit integer. [Before](round1-before.json), [after](round1-after.json).
2. Extreme-number review found `make_manifest` and the radius accepted alpha `1e-5000` and `1e-10000`, but manifest identity tried decimal integer-to-string conversion of the exact rational denominator and hit Python's global digit guard. This broke the supported principal workflow. Canonical rational identity now uses bounded hexadecimal numerator/denominator values without changing any process-global guard. Both unchanged accepted-alpha workflows failed in the parent and produced stable 64-character fingerprints and empty evidence in the child. The example identity was regenerated because the canonical representation changed. [Before](round2-before.json), [after](round2-after.json).
3. Library integration review set a caller Decimal context to precision 4, narrow exponent range and an `Inexact` trap. The bound code inherited traps/exponents in its local contexts and raised `Inexact` for ordinary supported inputs. Dedicated explicit contexts now isolate precision, rounding, exponents, traps and flags for bounds and Monte Carlo uncertainty. The unchanged probe checks ordinary/extreme radii, actual assigned-cohort analysis, Monte Carlo intervals and preservation of caller context. Four computations failed in the parent; all five checks pass in the child. [Before](round3-before.json), [after](round3-after.json).

Reproduce one pair:

```sh
python tools/verify_wheel.py 7d375b12b7eb5bc50120d03c44637a3c7b1c4db3 --probe tools/probe_stream_types.py
python tools/verify_wheel.py 71f6671bc59b931e40dafdd307777cf9dbe04b8f --probe tools/probe_stream_types.py
```

Rebuild all six archived wheels and check direct parentage, exact suite counts and matching probe digests:

```sh
python tools/replay_history.py --report tmp/history-replay.json
```

Remaining limitations are documented in ARCHITECTURE and MATH: source completeness and sampling attestations cannot be audited from these logs; bounds are conservative; permanently pending evidence may stay inconclusive. Documentation/evidence recording commits are not counted as correction cycles. CI configuration exists, but remote execution is unknown until the root publishes and checks it.
