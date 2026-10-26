# Reproducible open toolchain

The recorded run uses OSS CAD Suite **2026-10-25**, Darwin arm64. Its archive is SHA256 `5038c0410f12f6f650287e6bd7ddbe5da5b271aee40650ab1dcb51099cfbefa6`, matching GitHub release metadata. Tools report Yosys `0.70+219 / 5053d0e26`, nextpnr `0.11.1-79 / 22c5adf4`, and Icarus Verilog `14.0 (devel) / s20260301-670-g2b8d42dc0`. CI uses the same release date on Linux x64. Upstream may not provide bit-identical cross-platform implementation results; compare measurements with platform and tool versions attached.

Download the correct archive from the [official release](https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-10-25), verify the release asset's SHA256 digest before extraction, and prepend `oss-cad-suite/bin` to PATH. `siliconpilot doctor` identifies missing tools. Download/build artifacts do not belong in the source repository.

The ECP5 target is **LFE5U-25F-6, CABGA256**, 25 MHz, deterministic nextpnr seed 1. `synth.ys` and `constraints.lpf` are generated for every build. LPF constrains the clock. `--lpf-allow-unconstrained` permits automatic device IO assignment; no specific board pin map or external IO-delay budget is assumed. This enables meaningful device-level circuit comparisons but is not enough to flash a board safely.

Synthesis preserves the streaming shell around the packed-vector core. Mapped LUT equivalents are logic LUT4 count plus two per CCU2C carry cell, matching nextpnr's total LUT4 report for these circuits. Routing may pack more TRELLIS_COMB cells for mux structures; that resource is a separate field, not interchangeable with mapped LUT4. DSP and memory primitives are counted explicitly.

`latency_cycles` refers to packed-core input handshake to output-valid on an empty pipeline. RTL simulation checks this cycle model. `core_throughput_estimate_per_s` is an analytic bound from the core initiation interval. The serial shell can impose input/output serialization limits. Neither is a measured physical throughput. Fmax is the minimum achieved nextpnr clock estimate; a target-clock miss is infeasible for search. `--timing-allow-fail` retains the result and its failed timing state instead of hiding that design.

Typical memory is below a few gigabytes per small candidate. The released collector uses two concurrent jobs; recorded per-process wall time includes host contention. Run one worker on resource-limited CPUs. Build subprocesses have bounded timeouts, failed logs remain, and the live search reports noninterruptible budget overruns.
