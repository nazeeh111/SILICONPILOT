# One classifier, two clocked circuits

This case was executed on 17 November 2026 against current main [`6e2bbbe`](https://github.com/nazeeh111/SILICONPILOT/tree/6e2bbbe2faca1f10eb4a2a1e71a8aa858c56ffd1). It follows the packaged model through quantization, generated RTL, independent integer-reference checking and one ECP5 synthesis. Both choices use the current compiler; this is not a historical backend before/after comparison.

[Download actual generated circuits and verification artifacts](compiled-example.zip) · [Execution record](execution.json) · [Exact clock table](schedule.csv) · [Editable SVG](schedule.svg)

## What changed, and what stayed equal

The input is [`models/banknote_4x8x2.json`](../../models/banknote_4x8x2.json): four standardized features, eight hidden ReLU neurons, two fixed-point scores. The circuit does not accept camera frames or choose a class internally. Model weights and arithmetic remain identical. The choices below change multiplier lanes and product registration.

| Current compiler choice | Dense 4 → 8 | Handoff | Dense 8 → 2 | First output | Sustained output interval |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 lane, direct products | 32 | 1 | 16 | **49 clocks** | **34 clocks** |
| 2 lanes, registered products | 17 | 1 | 9 | **27 clocks** | **19 clocks** |

The figure's stage lengths are manifest clock accounting on a shared zero-based scale. The first-output endpoint and every consecutive output interval are independently checked at the public RTL ports. This is not a waveform reconstruction. Core clocks exclude the serial shell, input/output transfer time and downstream stalls. The separate serial-shell tests observed first-result availability after 50 and 28 clocks respectively; external sustained throughput additionally depends on transfer rates.

Both circuits passed all **78 vectors per core and serial-shell run**: 14 signed extrema/zero/impulse cases plus 64 random vectors with seed 1729. Output-backpressure stimulus is also deterministic. A separate continuous-traffic run checked 12 transactions, exact output values, every interval and silence after draining. Reset with in-flight work and stalled outputs was checked. The expected-vector files are byte-identical across both configurations, as are the input-vector files. This is finite digital verification, not universal equivalence.

Arithmetic is signed W8/F5/A24: ties-to-even input/weight quantization; A-bit modular accumulation; arithmetic right shift by F; signed saturation; hidden ReLU. Overflow wraps inside the accumulator. See the authoritative [arithmetic and handshake contract](../arithmetic.md). A deliberate temporary mutation that zeroed one registered product still compiled, but the real checker rejected it at sample zero (`got=07f8`, `expected=f10e`). The delivered circuits are unmodified.

## Generate and verify it yourself

The [main README](../../README.md#generate-your-first-verilog-without-installing) gives the dependency-free first compile. Simulation additionally needs Icarus Verilog and `vvp` on PATH. From a source checkout, choose new output directories:

```sh
PYTHONPATH=src python3 -m siliconpilot.cli verify models/banknote_4x8x2.json \
  --out work/direct-proof
PYTHONPATH=src python3 -m siliconpilot.cli verify models/banknote_4x8x2.json \
  --parallelism 2 --pipeline --out work/overlapped-proof
```

Each directory includes `design.v`, quantized `weights.json`, `manifest.json`, independent expected vectors, self-checking testbenches, logs, `verification.json`, and genuine VCD traces. Repeated compilation can replace these generated files; use stable inputs and separate output directories. The recorded run used Python 3.14.7 and Icarus 14.0-devel (`s20260301-670-g2b8d42dc0-dirty`). No dataset rows, training service or provider were used in this fresh case.

## Reopen the saved circuit, independently of Python

Download and extract [`compiled-example.zip`](compiled-example.zip) into a new directory. It contains both generated choices, their quantized weights, source testbenches, input/expected vectors, actual simulation logs and VCDs, plus the project's Apache-2.0 license and retained third-party/dataset notices. It contains no tool executables. From the extracted `overlapped/` directory:

```sh
iverilog -g2012 -s tb -o reopened-sim design.v tb_core.v
vvp reopened-sim
```

Repeat inside `direct/`. Both extracted circuits were recompiled and passed all 78 vectors in a separate process in the recorded run. The VCD is genuine simulator output; open it in a compatible waveform viewer. Use `tb_streaming.v` for the serial shell or `tb_schedule.v` for continuous-traffic schedule checking. `weights.json` and `manifest.json` explain the exact generated circuit, while the source model and compiler remain linked above.

## Synthesis is a separate stage

One fresh synthesis of the two-lane/registered configuration used Yosys `0.70+219`, commit `5053d0e26`, targeting ECP5 `LFE5U-25F`, speed 6, package CABGA256:

| Mapped resource | Actual count |
| --- | ---: |
| Logic LUT4 | 784 |
| Carry LUT4 equivalents (2 × 406 CCU2C) | 812 |
| **Total LUT4 equivalents** | **1,596** |
| TRELLIS_FF | 585 |
| MULT18X18D | 4 |
| DP16KD | 0 |

Multiplexer primitives are reported separately in `execution.json`. Captured input arrays intentionally map to registers; the corresponding synthesis warnings were inspected. The ordinary mapped DSP netlist was **not** simulated in this case; [the documented DSP-model limitation and distinct LUT-only checks](../netlist.md) remain unchanged.

With Yosys available, reproduce just this mapping without routing:

```sh
PYTHONPATH=src python3 -m siliconpilot.cli build models/banknote_4x8x2.json \
  --parallelism 2 --pipeline --synthesis-only --out work/mapped-proof
```

No fresh place-and-route, routed timing, board, power or physical validation is claimed here. The released corpus uses the older alternating product schedule and is preserved unchanged. Its recorded costs cannot be assigned to newly generated RTL. See [recorded-design compatibility](../arithmetic.md#recorded-design-compatibility), [recorded observatory](https://nazeeh111.github.io/SILICONPILOT/), and [benchmark definitions and limits](../benchmarks.md).

## Figure source and provenance

The warm paper/ink, green and oxide palette follows SiliconPilot's existing observatory identity. Direct stage labels, numeric clock lengths, the table and alt text provide alternatives to color. Desktop and narrow PNGs are accompanied by SVGs with editable text and a portable sans-serif font stack. [`figure.py`](figure.py) reads only [`execution.json`](execution.json); [`figure-manifest.json`](figure-manifest.json) binds source hashes, exact clock rows, rendering version and outputs. No values are smoothed, normalized or statistically aggregated. These deterministic clock observations have no invented uncertainty interval.

Original source is Apache-2.0. The packaged model derives from Volker Lohweg's UCI Banknote Authentication dataset (2012), CC BY 4.0, DOI [10.24432/C55P57](https://doi.org/10.24432/C55P57). The synthetic verification vectors do not replace that model/data provenance. External Icarus, Yosys and other components keep their own licenses; see [third-party notices](../THIRD_PARTY.md). No external binaries or proprietary HDL were added.
