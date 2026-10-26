# Independent implementation review

Reviewed 25 October 2026 from source, generated RTL and retained tool logs. This review did not treat builder descriptions as evidence and did not edit compiler/reference/toolchain code. The review found and reported resource-accounting and verification-coverage defects; the source fixes below were then inspected.

## Findings and disposition

1. **Correct total LUT accounting before making resource or Pareto claims.** The initial `toolchain.py` counted only `LUT4` cells. The first actual routed build reported 633 logic LUTs plus 586 carry LUTs, totaling 1,219 LUT4 equivalents (`work/first-build/routing.log`, lines 28–30). The carry contribution is twice the 293 `CCU2C` cells in the saved Yosys netlist. Routed `TRELLIS_COMB` utilization is a separate 1,311-cell packing metric. Source correction inspected at `src/siliconpilot/toolchain.py`, lines 62–64 and 94: the main `lut` includes logic and carry, with separate component counts and routed combinational utilization. **Release check:** regenerate or migrate retained build reports, benchmark corpus, surrogate targets and Pareto calculations consistently; changing the source alone does not repair old records.

2. **Label throughput as a core estimate and preserve the serial-shell boundary.** The original numeric `throughput_per_s` was calculated from the core initiation-interval formula despite synthesis targeting the serial shell. Independent continuous-input/continuous-ready Icarus probes confirmed the core formula on ten configurations, but also established a supported counterexample: a 16-input, one-output dense layer at parallelism 16 has core II 3 and serial-shell output-vector II 17. The main 4→8→2 model at parallelism 1 has II 34 for both interfaces; parallelism 4 gives II 10 for both. Source correction inspected at `toolchain.py`, lines 72–74: the field is now `core_throughput_estimate_per_s`, with explicit serialization/stall/physical-I/O exclusions. **Release check:** remove or explicitly scope old throughput fields in exported records and UI. Do not present these as measured board throughput.

3. **Execute the direct reset assertion.** The initial testbench gated the reset-clear assertion with `active`, while every reset occurred before `active` became true. Thus that direct assertion never ran. The source now checks output-valid after every reset rising edge and includes both a short in-flight reset and a reset after an actual stalled output has been reached (`verification.py`, lines 65–78 and 109). Subsequent real sample comparison remains important to catch queued work leaking past reset. The tiny formal proof checks only its documented initial-reset sequence, not arbitrary reset timing.

## Arithmetic and interface inspection

The reference accumulates in Python integers, wraps modulo the configured signed accumulator width, performs Python's negative-infinity right shift, saturates to the signed activation range, then applies ReLU. The RTL separately sign-extends signed products into an accumulator-width temporary, allowing modular wrap, and applies a signed arithmetic shift followed by signed saturation. The modulo arithmetic is associative, so changing accumulation grouping through parallel lanes preserves the reference sum. Pipelined products are captured before use; their lack of a reset value does not affect a valid computation after reset.

Output data remains held while output-valid is stalled. Each dense stage refuses a new vector while busy or holding output, producing the two-cycle overhead in `max(stage_compute_cycles) + 2`. Input-ready remains high in some reset states, but the synchronous reset discards transfers; this exception is explicitly documented in the interface contract. The serial shell captures features and emits scores in ascending index order. These observations are bounded by the inspected code and simulation cases, not a universal formal proof of arbitrary networks.

The independent throughput probe covered the main 4→8→2 classifier and a 16→1 network with `(parallelism, buffering, pipeline)` of `(1,1,false)`, `(4,1,false)`, `(4,2,false)`, `(4,2,true)` and `(16,1,false)`. Each run completed at least 40 output vectors. The last 20 output-vector intervals were constant and matched the reported core values. Parent-task scratch retains the probe script and logs; production tests should preserve an equivalent interface-throughput regression if numeric shell throughput is added.

## What the retained first build establishes

The saved synthesis and routing artifacts correspond to generated RTL SHA-256 `e4cf0ed5bb1cbbfcb3a070bc98fd0541d17f80541cc163f9ccee55a451c6c13b`. The retained independent RTL verification report has the same hash and compares 353 vectors, including 275 real dataset rows, through the core and serial shell. This links functional RTL verification to the synthesized design source.

The actual first route targeted LFE5U-25F, CABGA256, speed grade 6, at 25 MHz with nextpnr seed 1. It reported an achieved internal clock estimate of 44.3203468 MHz, 453 flip-flops and 2 DSP multipliers. Clock frequency is constrained, while the physical clock pin and data/control pins are automatically placed. External input/output delays and a board oscillator are unspecified. The source/report disclosures correctly identify a device-level research route, not a board-ready programming image or a physical performance measurement.

The existing verification executes the generated RTL. It does not execute the mapped ECP5 netlist or a delay-annotated routed netlist. Claims should say “RTL independently simulated; that RTL synthesized and routed with retained hashes,” rather than implying post-route functional or electrical validation. The bounded Yosys SAT log reports success for the tiny 2→2→1, 3-bit proof over all 64 input patterns through its finite depth. That result does not prove the sensor classifier, arbitrary generated models or physical timing.

## Reviewed source fingerprints

Fingerprints were captured after the above source fixes were visible. Subsequent modifications require a scoped recheck of the affected conclusions.

| Source | SHA-256 |
| --- | --- |
| `compiler.py` | `14c05b40221ec6ec6ef0657ea8a6de03b94522ca556926f4d2c1feb9ce072c86` |
| `reference.py` | `9f225f13936285e5d65da05d320a9a2034f6749c9cd89b20af0cf1c2544ba7f2` |
| `model.py` | `6de10971b081f3e3cb42bc70cce9cca2de03466e475ec9307e8df1026b0337b4` |
| `verification.py` | `d961a8a9612f2caadaaea5ec461f320faba0086bddcdeb8a5983960c14e4cecb` |
| `toolchain.py` | `6a492681023b21765fe8af2002812d542d0b5f6e60b87d82022c6f8fa3e4882d` |
| `formal.py` | `b7721050680eed6a4f1a699523ad5410cff7fee8e2890fef7ce721fc78bbdead` |

## Follow-up mapped implementation evidence

After the initial review, `src/siliconpilot/netlist.py` added hash-linked post-synthesis differential checks. The default DSP design passed separately synthesized generic-gate simulation over all 353 vectors. Because the installed ECP5 DSP is a blackbox declaration, that result is explicitly scoped to the generic netlist.

A separate real-classifier ECP5 variant, synthesized with `synth_ecp5 -nodsp`, then passed exact mapped LUT/carry/FF simulation over all 353 vectors, with 227 backpressure cycles. It was also actually routed for the documented device/package at 25 MHz; nextpnr estimated 43.7828369 MHz. Its recorded utilization is 1,954 mapped LUT4 equivalents, 405 FF and no DSP/BRAM. See [netlist.md](netlist.md) and `benchmarks/mapped-logic-verified/` for exact hashes, commands, primitive-library provenance and limitations. This resolves the absence of a fully simulated mapped implementation for that explicitly named logic-only variant, without asserting DSP-model verification.
