# Independent search and experiment audit

Reviewed source, tests, the 40-record measured corpus, and the saved ten-seed experiment artifacts on 25 October 2026. The review did not use implementation descriptions as evidence. It inspected `search.py`, `tests/test_search.py`, `scripts/experiment.py`, `benchmarks/search/experiments.json` and `surrogate_metadata.json`, and independently recomputed the numeric results.

## Information boundary

No use of unrevealed hardware labels was found in acquisition. `public_candidate` supplies only candidate/model identity, configuration, dimensions, integer-reference validation accuracy and analytic core cycles. `features` reads these public quantities. Paid synthesis reveals LUT/FF and synthesis duration; paid routing additionally reveals fmax and routing duration. The random-forest target fits select observations with that target actually revealed, so a synthesis-only observation cannot train timing or routing cost.

The saved fully trained surrogate is a separate artifact, not a pretrained oracle injected into replay. Each learned replay policy starts from its own paid observations. Training uses the 24 width-8 records; the 16 width-4/width-12 records evaluate topology generalization and remain outside the replay candidate pool. The train and held-out IDs are disjoint, and all reported held-out actual values match the measured corpus. No test-set classification accuracy enters acquisition or the reported objective.

This is nevertheless a **success-conditioned finite-pool study**: `normalize_record` accepts only verified, successfully routed records. It does not evaluate how a policy discovers synthesis errors, routing failures or unsupported networks in an initially unknown design space. The live optimizer records failures separately. The cost of collecting the complete corpus is outside each replay budget.

## Budget and numerical audit

The audited comparison uses a common 630.7071294-second FPGA-tool budget, 98% minimum validation accuracy, 2,000 mapped LUT4 equivalents and 2 microseconds maximum core latency at 25 MHz. Every strategy receives the same maximum budget. A fixed family can exhaust its candidate subgroup early; it need not consume time merely to match another strategy's expenditure. Search/acquisition CPU time is separately measured and excluded from the common FPGA-tool budget.

An independent checker reconstructed all **90 replay runs**, every charged query, every checkpoint hypervolume, every censored finishing time and every summary mean/sample standard deviation. Charges were exactly synthesis duration for a synthesis screen, routing duration for promotion, and synthesis plus routing for a direct full query. A query exceeding the cutoff reveals no labels and ends the run. No duplicate completed route or double charge for promoted synthesis was found.

Hypervolume was independently calculated by inclusion-exclusion over the union of objective-space boxes, rather than calling the implementation's hypervolume function. All recorded checkpoint values agreed within `1e-12`. A separate 120-case random-point comparison also passed. The first three paid route queries matched between the learned strategies and random search under the same seed; fixed conventional orderings intentionally use their specified architecture order.

## Results and what they establish

The final `known_accuracy_and_analytic_latency_screen_v2` results recover the following mean fractions of the measured finite-pool reference hypervolume:

| Strategy | Mean fraction |
| --- | ---: |
| Fixed architecture sweep | 100.00% |
| Full cost-aware two-fidelity policy | 98.00% |
| Mean-only acquisition | 94.91% |
| No cost normalization | 93.57% |
| Gaussian-process EHVI | 80.59% |
| Route-only RF acquisition | 80.12% |
| Random search | 70.30% |
| Fixed parallel family | 27.19% |
| Fixed serial family | 8.08% |

The full policy exceeds random, GP and the scoped ablations in mean recovery in this experiment, while the conventional fixed sweep wins. The full policy's sample standard deviation is 2.40 percentage points of reference hypervolume; random search's is 28.13 points. These ten-seed, one-pool results do not establish broad superiority, calibrated uncertainty or a general live speedup. Fixed order is deterministic, so ten repetitions do not constitute ten independent fixed-sweep observations.

Held-out LUT prediction MAE is 176.65 versus 378.16 for the training-mean baseline, and fmax MAE is 6.69 MHz versus 9.98 MHz. Routing-cost MAE is 27.02 seconds versus 26.80 seconds for that mean baseline, so this target does not improve on the baseline. Nominal 90% ensemble intervals cover only 50% of held-out fmax and routing-cost labels. Approximate ensemble spread is useful acquisition machinery, not a calibrated uncertainty guarantee. Training on one width also leaves topology features constant during fitting; this is a narrow extrapolation test, not broad cross-network training evidence.

The ablations have explicitly bounded scope. `no_uncertainty` replaces acquisition draws with their mean but retains uncertainty-dependent synthesis screening. `no_cost` removes acquisition normalization but retains cost-dependent fidelity selection. The documentation correctly labels these as mean-only acquisition and no cost normalization. Neither removes all uncertainty or cost information from the algorithm.

## Consequential issues reported

1. The original live loop could start synthesis after verification exhausted the wall budget, and its build call could start routing after synthesis exhausted the remaining allowance. Source corrections now recheck after verification and between tool stages. The last noninterruptible invocation can still overrun, and reports explicitly disclose that behavior.
2. The original live `compile_seconds` omitted failed tool attempts. Source corrections now retain successful stage duration, failed-attempt wall time, attempted-build-call wall time and verification time separately. Failure cases survive in the saved history instead of disappearing.
3. The initial acquisition screened known low accuracy but did not prefilter known-infeasible analytic latency. A candidate whose `latency_cycles / target_clock` already exceeds the latency limit cannot become feasible through routing. The final source applies this exact cheap screen equally to all nine policies (`search.py`, lines 235–238). All policies were rerun under the same constraints, seeds and budget. Independent checking confirmed that every paid query in all 90 final histories obeys both cheap constraints, and that all six stochastic policies share their first three route observations for every seed. The superseded source/results remain in `benchmarks/search-unpruned/`; the table and fingerprints here refer to the final corrected protocol.

## Final artifact fingerprints

These identify the final corrected numerical results independently checked above. Later changes require a scoped recheck.

| Artifact | SHA-256 |
| --- | --- |
| `experiments.json` | `7cd6be5d0ddb0bbaddd7ec9d89ab73a2cf3b615de92eb88810262609f796b1b8` |
| `surrogate_metadata.json` | `74685063e56b1914b5a48d15b4b8ea161641b27365a4e8e9f0564777f5f29280` |
| `src/siliconpilot/search.py` | `ac887019ae4e45549354021d311ac5863749570b087c594bed50cba24fd9d362` |
