# Post-synthesis differential verification

SILICONPILOT verifies post-synthesis logic against the independently calculated integer outputs in `expected.hex`. This check executes real Icarus Verilog simulation, including output backpressure, reset, feature serialization and score ordering. It uses the saved testbench and vectors rather than deriving expected answers from a netlist.

Run a build and independent RTL verification into the same directory, then:

```sh
python -m siliconpilot.netlist path/to/build
```

The verifier checks that build, manifest and passing RTL verification all identify the exact saved `design.v` SHA-256. It also verifies the saved synthesized JSON and Verilog against build hashes. Netlist simulation runs separately under `netlist-check/`, preserving the RTL logs/waveforms. The report is `netlist-verification.json` and records input, expected-output, testbench, netlist and behavioral-library hashes, commands, tools and sample counts. Any wrong output bit, unexpected transaction, unstable stalled output, timeout or missing completion fails the check.

## Trusted primitive boundary

The pinned Yosys ECP5 library provides executable upstream models for LUT4, PFUMX, L6MUX21, CCU2C and TRELLIS_FF. Exact mapped simulation is enabled only when every mapped primitive belongs to this supported set. No blackbox file is accepted as a behavioral model.

The pinned toolchain declares `MULT18X18D` in `ecp5/cells_bb.v`, with no functional implementation. Simulating that declaration would leave outputs undriven and would not validate a multiplier. The project does not invent a DSP model or claim that such a blackbox is verified. For DSP-containing designs, the report explicitly marks mapped simulation unavailable and separately synthesizes the same RTL into generic gates, then runs the independent vectors on that generic netlist. A passing generic result establishes that separately synthesized logic's functional behavior, while leaving the ECP5 DSP mapping unverified by this particular check.

Primary implementation references: [Yosys ECP5 behavioral library](https://github.com/YosysHQ/yosys/blob/main/techlibs/lattice/cells_sim_ecp5.v), [blackbox declarations](https://github.com/YosysHQ/yosys/blob/main/techlibs/lattice/cells_bb_ecp5.v). The report records the installed library bytes used, since source layout changes between releases.

## Fully simulated ECP5 implementation

The open `synth_ecp5 -nodsp` option implements multiplication in LUT/carry logic, allowing the actual mapped netlist to execute entirely with upstream behavioral models. This is a distinct hardware implementation, with separate resource and timing results. It must not inherit the DSP design's LUT count or timing estimate.

To create a fresh separate logic-only build from already verified RTL, synthesize it, optionally route it, and simulate its exact mapped netlist:

```sh
python -m siliconpilot.netlist benchmarks/mapped-logic-verified \
  --logic-only-from benchmarks/netlist-reference --route
```

The destination must not exist. The original DSP build remains intact. The new directory receives its own Yosys synthesis log, mapped JSON/Verilog, build manifest and hashes, and, when routing is requested, nextpnr report, configuration and constraints. The explicit mapping policy is `synth_ecp5 -nodsp`.

Routing targets LFE5U-25F, CABGA256, speed grade 6, 25 MHz and seed 1. Pin placement is automatic and external I/O delays are unspecified. These are device-level FPGA research artifacts requiring board-specific electrical/pin constraints before programming hardware.

## Limits

Every simulation here is a zero-delay digital functional check of retained test vectors. It is not exhaustive equivalence, delay-annotated routed simulation, electrical validation, or a physical FPGA measurement. Place-and-route timing is a separate tool estimate. The small bounded formal proof documented elsewhere covers only its representative tiny circuit.

The tests include a real mapped logic-only circuit, a DSP case with the explicitly labeled generic fallback, deliberate corruption of an expected output, and rejection of altered synthesis bytes. Checking an intentionally wrong answer is essential: a simulator that merely launches or produces a waveform has not established output correctness.

## Retained real-classifier results

The release includes two distinct post-synthesis checks on the real 4→8→2 banknote classifier and all 353 retained vectors, comprising 78 boundary/random vectors and 275 real dataset rows.

| Implementation | Functional evidence | Resource/timing evidence |
| --- | --- | --- |
| Default DSP mapping, `benchmarks/netlist-reference` | Separately synthesized generic-gate netlist passes 353/353; exact ECP5 DSP simulation explicitly unavailable | Original DSP ECP5 synthesis/routing retained; no generic-netlist resource claim |
| Logic-only ECP5 mapping, `benchmarks/mapped-logic-verified` | Exact mapped ECP5 LUT/carry/FF netlist passes 353/353, including 227 output backpressure cycles | 1,954 mapped LUT4 equivalents (1,342 logic + 612 carry), 405 FF, 0 DSP, 0 BRAM; nextpnr routed at 25 MHz, internal fmax estimate 43.7828369 MHz |

The logic-only build's RTL hash is `e4cf0ed5bb1cbbfcb3a070bc98fd0541d17f80541cc163f9ccee55a451c6c13b`; its exact mapped Verilog hash is `ea4466f271d7ac2e25fb327867abf60948248cc1edc9f8e60e3b67f7bc41cc42`. It is a real synthesized and routed accelerator with independent mapped functional simulation. It remains a device-level research build, with no physical FPGA test or delay-annotated routed simulation claim.
