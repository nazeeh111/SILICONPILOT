# Arithmetic and interface contract

SILICONPILOT supports a fixed feature vector followed by one or more fully connected (dense) layers, each optionally followed by ReLU. Weights have output-major shape `[outputs][inputs]`. Dynamic shapes, convolution, softmax, arbitrary activations and unknown operation attributes are rejected. The final scores may be compared with argmax outside the circuit. There is no division, floating-point operation or softmax inside the circuit.

## Bit-exact arithmetic

A configuration specifies signed activation/weight width `W`, shared fractional precision `F`, and signed accumulator width `A`. `3 <= W <= 16`, `0 <= F < W`, and `2W <= A <= 48`.

1. Quantize each input and weight with Python's round-to-nearest, ties-to-even at scale `2^F`, then saturate to the signed W-bit range. These conversions run before the hardware.
2. Quantize a bias at scale `2^(2F)` using ties-to-even and wrap to signed A bits.
3. Each dense layer computes an A-bit signed modular sum of the bias and signed W-by-W products. Overflow wraps modulo `2^A`; it does not saturate. Because modular addition is associative, changing the number of multiplier lanes preserves numerical results.
4. Shift the signed accumulator right by F bits using an arithmetic shift. This rounds toward negative infinity, including for negative non-integers.
5. Saturate the shifted result to signed W bits. Apply ReLU (`max(0, value)`) if that operation follows the layer. Every layer therefore uses the same activation scale `2^F`.

Example with W=4, F=2, A=8: four products `7*7` sum to 196, which wraps to -60; arithmetic right shift yields -15; signed saturation yields -8. Such overflow is intentional and verified. Accuracy evaluation includes all clipping and wrapping effects. Narrow-accumulator designs may therefore lose accuracy.

## Hardware architecture

Each dense stage has `min(parallelism, input_count)` physical multiplier lanes. It processes one output neuron at a time and reuses lanes over groups of inputs. Every stage has a captured input vector and a held output vector. Stages communicate with valid/ready handshakes and may process different transactions concurrently.

`pipeline=true` adds a register between each multiplier and the accumulator, with two cycles per input group. This implementation deliberately trades more cycles and registers for a shorter multiply-to-accumulate combinational path. It does **not** promise higher throughput. `buffering=2` adds a two-vector FIFO before the first stage; `buffering=1` connects the first stage directly. Buffering does not change arithmetic.

For a layer with NI inputs, NO outputs and P active lanes, compute time is `C = NO * ceil(NI/P) * (pipeline ? 2 : 1)` cycles. With L dense stages, empty-pipeline core latency is `sum(C) + L - 1 + (buffering == 2 ? 1 : 0)` cycles from input acceptance to output-valid assertion after a rising clock edge. Steady-state core initiation interval is `max(C) + 2` cycles without downstream backpressure. FIFO burst admission can be faster, but does not increase sustained compute throughput. Verification measures the first transaction's core latency and rejects formula disagreement.

## Reset, handshakes and pin-efficient shell

`clk` is the rising-edge clock. `rst` is synchronous and active high. Reset aborts all queued and in-flight transactions, clears output-valid flags, and restarts feature/score counters. Inputs and outputs use valid/ready: a transfer happens only at a rising edge where both are high. Senders hold data and valid stable while stalled. A held output remains unchanged until accepted. Input-ready is not gated by reset, so transfers during asserted reset are discarded and must not be treated as accepted work by an external producer.

`siliconpilot_core` exposes little-endian packed vectors: element zero occupies the least significant W bits. Its output is one packed vector. `siliconpilot_top`, the synthesis and routing target, exposes W-bit serial input and output ports. Feed one complete vector's features in ascending index order; read the output scores in ascending index order. Input vectors and output scores are independently backpressured. The shell adds serialization and one cycle for a completed input vector to reach the core. Core latency figures exclude this serialization. Sustained external throughput is additionally bounded by feature and score transfer rates.

No board oscillator frequency, physical pins or I/O electrical standard is implied by the analytical FPGA placement. Reports use a named ECP5 device/package and an explicit clock target. Loading a physical board requires a board-specific pin/clock constraint file and electrical review.

## Verification evidence

The integer reference uses independent Python arithmetic and has no dependence on Verilog-generation code. `verify_model` generates signed extrema, alternating signs, impulses, zero, one, minus one, seeded random vectors and optional real dataset vectors. It compares every output bit through actual Icarus Verilog execution, tests a reset during an in-flight transaction, drives randomized output backpressure, checks output stability while stalled, and separately verifies the serial shell. Testbench sources, exact vector files, simulator logs and VCD waveforms are retained. These are digital simulation results, not physical FPGA measurements.
