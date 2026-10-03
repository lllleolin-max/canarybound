# CanaryBound

Delayed binary outcomes can make a canary look reassuring because its adverse outcomes have not arrived. CanaryBound retains every assigned unit in its own arm/stratum denominator, computes every possible missing-outcome completion, and widens a conservative population confidence sequence around those completions. It emits separate `ACCEPTABLE`, `HARMFUL` or `INCONCLUSIVE` labels for the finite assigned cohort and the population model.

This is conditional statistical evidence for release analysts. It does not establish a causal treatment effect or certify operational rollout safety. Declare strata, exact target weights, alpha, margins and sampling assumptions before enrolling units. The population guarantee requires iid stationary Bernoulli outcomes per cell and enrollment independent of eventual outcomes. Revelation may depend arbitrarily on the outcomes, including permanent missingness.

## Quickstart

Python 3.11+; the runtime uses the standard library.

```sh
python -m pip install .
canarybound identity examples/manifest.json
canarybound analyze examples/manifest.json examples/events.jsonl --at 2026-01-01T00:03:00Z
canarybound compare --size 1000
canarybound simulate --trials 500 --steps 200 --seed 20261003
python -m unittest discover -s tests -v
```

The small file example is inconclusive. The size-1000 synthetic contrast uses identical assignments, target weights and margins: completed-only analysis labels early evidence `ACCEPTABLE`; retaining delayed adverse outcomes is `INCONCLUSIVE`; after all outcomes arrive it is `HARMFUL`. The all-observed complete-data baseline equals the main method. The fixed-count and completed-only methods are disclosed ablations, not advertised sequential guarantees.

```python
import json
from canarybound import make_manifest, analyze
from canarybound.io import read_events

with open("examples/manifest.json", encoding="utf-8") as f:
    manifest = make_manifest(json.load(f))
report = analyze(manifest, read_events("examples/events.jsonl"), "2026-01-01T00:03:00Z")
print(report.population_status.value)
print(report.finite_completion.as_dict())
```

Events are strict JSONL `assign` or `outcome` records carrying the manifest fingerprint. Each unit has a stable pseudonymous ID. Assignments carry `arm`, `stratum` and an aware `at`; outcomes carry integer `bad` 0/1 and an aware observation `at`. File ordering does not define time. Duplicate IDs, earlier outcomes, unknown streams, naive times, changed manifests and undeclared model/filter policies are errors. Future labels never enter a current look. Permanently pending records remain pending.

Margins concern weighted adverse canary minus control. `upper <= acceptable_margin` is acceptable; `lower > harmful_margin` is harmful; all other intervals are inconclusive. Margins may coincide. Input errors exit 2; valid evidence exits 0 regardless of label. `--output` and `--stdout` are mutually exclusive. Output contains aggregates, not unit IDs.

## 中文说明

**做什么：**面向发布分析人员，处理金丝雀与对照组中延迟或永久缺失的二元不良结果。先按固定分层及目标权重计算已分配队列所有可能补全的确定性区间，再在明确的抽样模型下计算保守的总体置信序列，两类结果单独呈现。

**怎么用：**安装后先填写 `examples/manifest.json`，在采集结果前固定分层、权重、容忍边界、alpha 与抽样声明。使用 `canarybound identity` 得到指纹，写入每条分配和结果记录。运行 `analyze ... --at 带时区的时间` 获取当时证据；运行 `compare` 重现有信息延迟下的对照；运行 `simulate` 查看模型内的覆盖率试验。

**为什么做：**只看已经返回的结果，可能漏掉延迟的不良结果并错误建议继续。这里保留全部已分配单位，缺失仍计入分母，输出“不确定”供分析人员继续核查。它不承诺上线安全，不证明因果效果，也不能识别未写入日志的分配记录。试验是合成数据；采用、客户、收入与付费意愿未知。

See [the proof](docs/MATH.md), [architecture and limits](docs/ARCHITECTURE.md), [pilot and comparison](docs/PILOT.md), [security](SECURITY.md), [contributing](CONTRIBUTING.md), and [correction history](docs/ITERATIONS.md). The documented method is a simple Hoeffding union construction, not Howard et al.'s tighter mixture algorithm and not a new statistical invention. Argo Rollouts already implements analysis thresholds, delays and inconclusive results.
