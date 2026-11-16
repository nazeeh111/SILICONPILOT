"""Overlapped multiply/accumulate scheduling, checked at the public ports."""
import shutil

import pytest

from siliconpilot import compiler
from siliconpilot.model import HardwareConfig, quantize
from siliconpilot.reference import evaluate_integer
from siliconpilot.verification import _pack, _simulate, verify_model


ICARUS = bool(shutil.which('iverilog') and shutil.which('vvp'))


def dense_model(inputs, outputs):
    return {'name': 'pipeline-boundaries', 'input_size': inputs, 'layers': [
        {'op': 'dense',
         'weights': [[((i+2*j) % 7 - 3) / 2 for i in range(inputs)] for j in range(outputs)],
         'bias': [(j-1) / 4 for j in range(outputs)]}]}


@pytest.mark.skipif(not ICARUS, reason='Icarus required for real pipeline simulation')
@pytest.mark.parametrize('inputs,outputs,lanes,cycles', [
    (1, 1, 1, 2),       # Fill, then drain, no phantom second product.
    (1, 4, 8, 5),       # Consecutive neurons, requested lanes exceed input size.
    (5, 3, 2, 10),      # Tail lane and next-neuron metadata overlap.
    (7, 3, 3, 10),      # Two inactive tail lanes.
    (4, 3, 1, 13),      # Multiple groups in every neuron.
    (4, 3, 4, 4),       # One group per neuron, no boundary bubbles.
])
@pytest.mark.parametrize('buffering', [1, 2])
def test_pipeline_schedule_and_arithmetic(tmp_path, inputs, outputs, lanes, cycles, buffering):
    cfg = HardwareConfig(bits=4, fractional_bits=1, accumulator_bits=8,
                         parallelism=lanes, pipeline=True, buffering=buffering)
    result = verify_model(dense_model(inputs, outputs), cfg, tmp_path, random_count=24)
    assert result['latency_cycles'] == cycles + (buffering == 2)
    assert result['initiation_interval_cycles'] == cycles + 2
    assert result['results']['schedule']['samples'] >= 8
    assert result['results']['streaming']['passed']


@pytest.mark.skipif(not ICARUS, reason='Icarus required for real pipeline simulation')
@pytest.mark.parametrize('dimensions,latency,interval', [
    ([5, 3, 2], 16, 12),     # First stage is the bottleneck.
    ([2, 5, 3], 17, 12),     # Last stage is the bottleneck.
    ([1, 5, 2, 1], 17, 9),   # Middle bottleneck, one-group last stage.
])
def test_multistage_pipeline_sustained_output(tmp_path, dimensions, latency, interval):
    model = {'input_size': dimensions[0], 'layers': []}
    for ni, no in zip(dimensions, dimensions[1:]):
        model['layers'].extend(dense_model(ni, no)['layers'])
        model['layers'].append({'op': 'relu'})
    cfg = HardwareConfig(bits=5, fractional_bits=2, accumulator_bits=10,
                         parallelism=2, pipeline=True)
    result = verify_model(model, cfg, tmp_path, random_count=24)
    assert result['latency_cycles'] == latency
    assert result['initiation_interval_cycles'] == interval


@pytest.mark.skipif(not ICARUS, reason='Icarus required for mutation controls')
@pytest.mark.parametrize('original,mutation,failure', [
    ('registered_0 <= product_0;', "registered_0 <= 0;", 'MISMATCH'),
    ('product_last <= base + P >= NI;', "product_last <= 1'b1;", 'MISMATCH'),
    ('product_neuron <= neuron;', 'product_neuron <= 0;', 'reset setup did not reach stalled output'),
])
def test_scoreboard_rejects_wrong_product_or_tag(tmp_path, monkeypatch, original, mutation, failure):
    generate = compiler.generate_verilog

    def corrupt(*args):
        rtl = generate(*args)
        assert original in rtl
        return rtl.replace(original, mutation)

    monkeypatch.setattr(compiler, 'generate_verilog', corrupt)
    cfg = HardwareConfig(bits=4, fractional_bits=1, accumulator_bits=8,
                         parallelism=2, pipeline=True)
    with pytest.raises(RuntimeError, match=failure):
        verify_model(dense_model(5, 3), cfg, tmp_path, random_count=4)


@pytest.mark.skipif(not ICARUS, reason='Icarus required for cycle-contract control')
def test_schedule_checker_rejects_wrong_interval(tmp_path, monkeypatch):
    from siliconpilot import verification
    compile_model = verification.compile_model

    def wrong_interval(*args):
        manifest = compile_model(*args)
        manifest['initiation_interval_cycles'] += 1
        return manifest

    monkeypatch.setattr(verification, 'compile_model', wrong_interval)
    cfg = HardwareConfig(parallelism=2, pipeline=True)
    with pytest.raises(RuntimeError, match='SCHEDULE_INTERVAL'):
        verify_model(dense_model(5, 3), cfg, tmp_path, random_count=4)


@pytest.mark.skipif(not ICARUS, reason='Icarus required for reset-phase simulation')
def test_reset_flushes_each_product_phase_and_stalled_output(tmp_path):
    model = dense_model(5, 3)
    cfg = HardwareConfig(bits=4, fractional_bits=1, accumulator_bits=8,
                         parallelism=2, pipeline=True, buffering=2)
    compiler.compile_model(model, cfg, tmp_path)
    fresh = [2, -1, 3, -4, 1]
    expected = _pack(evaluate_integer(quantize(model, cfg), fresh), 4)
    # The discarded transaction differs from the fresh one. Reset crosses every
    # issue/retirement edge, FIFO occupancy, and finally a stalled completed output.
    tb = f'''`timescale 1ns/1ps
module tb;
  reg clk=0; always #5 clk=!clk;
  reg rst=1, in_valid=0, out_ready=0;
  reg [19:0] in_data=0;
  wire in_ready, out_valid;
  wire [11:0] out_data;
  integer phase, waited;
  siliconpilot_core dut(.clk(clk),.rst(rst),.in_valid(in_valid),.in_ready(in_ready),
    .in_data(in_data),.out_valid(out_valid),.out_ready(out_ready),.out_data(out_data));
  initial begin
    for (phase=0; phase<=13; phase=phase+1) begin
      rst=1; in_valid=0; out_ready=0;
      repeat(2) @(negedge clk);
      rst=0; in_valid=1; in_data=20'h77777;
      // Fill both queue slots with work that must be discarded.
      repeat(2) @(negedge clk);
      in_valid=0;
      repeat(phase) @(negedge clk);
      rst=1;
      @(negedge clk);
      if (out_valid) $fatal(1,"RESET_VALID phase=%0d",phase);
      rst=0; in_data=20'h{_pack(fresh,4):05x}; in_valid=1;
      if (!in_ready) $fatal(1,"RESET_READY");
      @(negedge clk);
      in_valid=0; waited=0;
      while (!out_valid && waited<40) begin
        @(negedge clk); waited=waited+1;
      end
      if (!out_valid || out_data !== 12'h{expected:03x})
        $fatal(1,"RESET_STALE_PRODUCT phase=%0d got=%h",phase,out_data);
      repeat(3) begin
        @(negedge clk);
        if (!out_valid || out_data !== 12'h{expected:03x}) $fatal(1,"RESET_STALL");
      end
      out_ready=1;
      @(negedge clk);
      repeat(30) begin
        if (out_valid) $fatal(1,"RESET_EXTRA_OUTPUT phase=%0d",phase);
        @(negedge clk);
      end
    end
    $display("RESET_PHASE_PASS phases=14"); $finish;
  end
endmodule
'''
    log = _simulate(tmp_path, 'reset_phases', tb, shutil.which('iverilog'), shutil.which('vvp'))
    assert 'RESET_PHASE_PASS phases=14' in log
