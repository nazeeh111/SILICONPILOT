# Learning which designs deserve a compile

SILICONPILOT implements an experimental cost-aware two-fidelity policy on top of
its own small HDL compiler. This is an implemented research artifact, not a claim
that surrogate-assisted FPGA design or multi-fidelity Bayesian optimization is
new. See [research.md](research.md) for related work and competing approaches.

## What the search knows

Before synthesis, a candidate exposes its network dimensions, precision,
accumulator width, multiplier parallelism, product-pipeline choice, input-buffer
capacity, analytic cycle count, and integer-reference **validation** accuracy.
Accuracy evaluation on the small held-out validation split is inexpensive and
requires no FPGA compilation. Test labels never enter the acquisition policy.
A synthesis query reveals Yosys LUT/FF utilization and wall-clock synthesis cost.
A routing query additionally reveals nextpnr's achieved-frequency estimate and
routing wall-clock cost. These are device estimates, not physical measurements.

The surrogate is a pinned scikit-learn random-forest ensemble trained on log LUT,
achieved clock frequency, synthesis cost and routing cost. Topology features
include all layer dimensions, MAC count and parameter count. Dispersion across
trees, with a 0.05 log-space floor, represents approximate uncertainty. It is not a
calibrated confidence guarantee. The saved metadata reports empirical held-out
90% interval coverage so narrow or inaccurate intervals remain visible.

## Policy

Three identically seeded initial routed designs initialize each learned policy.
For the remaining candidates, Monte Carlo draws approximate expected improvement
in the **three-dimensional dominated hypervolume** of the observed feasible
frontier: maximize validation accuracy, minimize core latency, and minimize LUTs.
Hypervolume is the volume of objective space dominated by the frontier, measured
inside a fixed unit box derived from the declared constraints. A target clock
miss is infeasible; the policy does not quietly run it at a slower clock.
The default accuracy/latency/LUT constraints are 90%, 15 microseconds and 3000 LUTs,
with a 25 MHz target clock; experiments save their exact selected values.

Acquisition is expected hypervolume gain plus a small, declared resource
information bonus, divided by predicted remaining compilation cost. A cheap
synthesis screen precedes routing when the LUT posterior is uncertain and
predicted synthesis costs less than routing. This is a practical screening
heuristic, not an optimal value-of-information calculation. Its parameters and
cold priors are in `search.py`; they are fixed before observing the replay result.
Once synthesized, a design uses its observed LUT count instead of a prediction.
The same `propose` interface drives offline replay and actual tool invocations.

## Baselines and ablations

Every policy receives the same finite candidate pool and validation scores.
Before any query, all policies equally exclude candidates whose known validation
accuracy or analytic cycles divided by the target clock cannot meet the declared
accuracy/latency constraint. Resources and routed timing remain unknown until a
paid query.
The comparison includes:

- **Fixed**: a predetermined conventional Q3.5/24-bit-accumulator ordering, serial
  first, followed by increasing parallelism. It reads no hardware outcomes.
- **Fixed serial / fixed parallel**: retain one lane or the maximum lane count,
  with no product pipeline and a one-vector buffer; sweep precision in the same
  predetermined order. They stop when their architecture subgroup is exhausted,
  even if budget remains. These quantify simple fixed hardware families.
- **Random**: seeded uniform choice among uncompiled designs passing both cheap feasibility checks.
- **GP EHVI**: conventional independent Matérn Gaussian-process posteriors and
  expected hypervolume improvement. It performs full routed evaluations and does
  not divide acquisition by evaluation cost.
- **Mean-only acquisition** (`no_uncertainty`): ensemble means replace acquisition
  draws; the same uncertainty-driven synthesis-screen rule is retained so the
  acquisition ablation does not also disable that separate mechanism.
- **No cost normalization** (`no_cost`): removes the acquisition cost denominator.
- **No low fidelity** (`no_low_fidelity`): performs only full routed evaluations.

The finite pool is generated and compiled independently of these policies. It
covers precision, accumulator width, multiplier reuse, buffering and pipelining;
it is not an exhaustive search of FPGA architectures. The held-out network
widths never join the training-topology replay pool. A separately saved surrogate
fits only the documented training topology and is evaluated on the other network
configurations. The mean-predictor baseline, per-design predictions, absolute
errors and empirical uncertainty coverage remain in `surrogate_metadata.json`.

## Equal measured-cost replay

`python scripts/collect.py --root . --output benchmarks/reproduced --workers 2`
creates a fresh measured corpus while preserving the retained release evidence.
Then `python scripts/experiment.py benchmarks/reproduced/corpus.json --output
benchmarks/reproduced/search` trains and saves `surrogate.joblib`, `surrogate_metadata.json`, and
`experiments.json`. The latter includes every query, fidelity, charged duration,
seed, cumulative hypervolume, and common budget. Every policy receives the same
maximum budget, not a requirement to waste an identical consumed duration; fixed
families can exhaust their subgroup early. The default budget is 45% of the
measured total compilation cost of the training-topology pool.

Replay reveals no hidden LUT or timing label before the corresponding query.
Synthesis costs are charged once; promotion from a synthesized candidate charges
only its measured routing cost. If a noninterruptible query would finish beyond
the common time cutoff, that query is censored, its labels remain hidden, and the
run ends without trying a cheaper alternative. All reported improvements use
only completed queries within the budget. This is offline evaluation on measured
compiler outcomes; it does not establish online wall-clock speedup on unknown
networks. Acquisition CPU time is measured separately and is not included in the
matched FPGA-tool budget. Fixed ordering is deterministic, so repeating it does
not create independent evidence.

Results may favor a baseline or show negligible differences. Small finite pools,
one sensor dataset, a single device/speed grade, and a small number of topology
families limit inference. Report the measured outcome and its uncertainty; do not
turn this artifact into a broad performance-superiority claim.

## Actual tool-driven optimization

`optimize(model, configs, root, output_dir, ...)` evaluates quantized validation
accuracy, calls `propose`, independently verifies each selected RTL design, and
runs the actual Yosys/nextpnr toolchain at the selected fidelity. It writes
`live-search.json` after each completed query, with all failures and artifacts
preserved. Live accounting includes failed tool-attempt wall time and separates
successful compilation durations from total attempted build-call time. After verification, the remaining wall budget is checked again before
synthesis. The toolchain checks its remaining budget between synthesis and
routing; if it is exhausted, the synthesis result survives and routing is
explicitly skipped. Verification-only jobs are saved when verification consumes
the deadline. It stops launching work at its wall-clock limit; a noninterruptible
invocation can overrun, and the exact overrun is reported. `max_evaluations` bounds
all fidelity queries, including cheap synthesis screens. An `accuracy_fn`
callback supports user-provided validation data for another supported model.

The publication comparison was specified before the final corpus finished: 10
seeds, validation accuracy at least 98%, at most 2000 mapped LUT4s, at most 2
microseconds core latency at 25 MHz, and the common 45%-of-pool compilation
budget. Feasibility-cardinality sensitivity at 90%, 98% and 100% accuracy is saved
without retuning the acquisition or selecting a favorable reported constraint.

## Independent-review protocol correction

The first replay screened cheap accuracy but omitted the equally cheap analytic
latency filter. Review identified that this unnecessarily weakened all policies,
including the baselines. The release reruns all 90 comparisons with a common
accuracy-and-latency filter, under the unchanged previously declared constraints,
seeds and measured-cost budget. This is protocol revision
`known_accuracy_and_analytic_latency_screen_v2`. The superseded first result,
plots and source are retained in `benchmarks/search-unpruned` for provenance, and
do not supply release performance claims. The 40-design measurement corpus was
not changed by this correction. Replay is conditioned on successful retained
builds, so it does not evaluate compile-failure prediction or failed-build costs.
Live execution separately records and charges failed attempts.
