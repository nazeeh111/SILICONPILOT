"""Deterministic dense/ReLU compiler emitting synthesizable Verilog-2005."""
from __future__ import annotations
import hashlib
import json
from math import ceil
from pathlib import Path
from typing import Any, Mapping
from .model import HardwareConfig, quantize


def _literal(value: int, bits: int) -> str:
    return f"{bits}'h{value % (1 << bits):x}"


def _dense(index: int, inputs: int, layer: Mapping[str, Any], cfg: HardwareConfig) -> str:
    w, a, p = cfg.bits, cfg.accumulator_bits, min(cfg.parallelism, inputs)
    outputs = len(layer['bias'])
    weights = '\n'.join(f'      {j*inputs+i}: weight = {_literal(value,w)};' for j,row in enumerate(layer['weights']) for i,value in enumerate(row))
    biases = '\n'.join(f'      {j}: bias = {_literal(value,a)};' for j,value in enumerate(layer['bias']))
    comb = '\n'.join(f'  assign product_{lane} = (base + {lane} < NI) ? $signed(x[base+{lane}]) * $signed(weight(neuron*NI+base+{lane})) : {2*w}\'sd0;' for lane in range(p))
    decl = '\n'.join(f'  wire signed [{2*w-1}:0] product_{lane};' + (f'\n  reg signed [{2*w-1}:0] registered_{lane};' if cfg.pipeline else '') for lane in range(p))
    additions = '\n'.join(f'    sum_next = sum_next + $signed({"registered" if cfg.pipeline else "product"}_{lane});' for lane in range(p))
    latch = '\n'.join(f'          registered_{lane} <= product_{lane};' for lane in range(p))
    accumulate = f'''          if (base + P >= NI) begin
            out_data[neuron*W +: W] <= activate(sum_next);
            base <= 0;
            if (neuron + 1 >= NO) begin
              busy <= 0;
              out_valid <= 1;
            end else begin
              neuron <= neuron + 1;
              acc <= bias(neuron + 1);
            end
          end else begin
            base <= base + P;
            acc <= sum_next;
          end'''
    body = f'''        if (!phase) begin
{latch}
          phase <= 1;
        end else begin
          phase <= 0;
{accumulate}
        end''' if cfg.pipeline else accumulate
    return f'''// Dense stage {index}: {inputs} -> {outputs}, {p} multiplier lanes.
module sp_dense_{index}(input clk, input rst,
 input [{inputs*w-1}:0] in_data, input in_valid, output in_ready,
 output reg [{outputs*w-1}:0] out_data, output reg out_valid, input out_ready);
  localparam W={w}, A={a}, NI={inputs}, NO={outputs}, P={p}, F={cfg.fractional_bits};
  reg signed [W-1:0] x [0:NI-1];
  reg signed [A-1:0] acc;
  reg busy, phase;
  integer base, neuron, k;
  assign in_ready = !busy && !out_valid;
  function signed [W-1:0] weight;
    input integer address;
    begin case (address)
{weights}
      default: weight = 0;
    endcase end
  endfunction
  function signed [A-1:0] bias;
    input integer address;
    begin case (address)
{biases}
      default: bias = 0;
    endcase end
  endfunction
  function [W-1:0] activate;
    input signed [A-1:0] value;
    reg signed [A-1:0] shifted;
    begin
      shifted = value >>> F;
      if ({1 if layer['relu'] else 0} && shifted < 0) activate = 0;
      else if (shifted > {a}'sd{(1 << (w-1))-1}) activate = {_literal((1 << (w-1))-1,w)};
      else if (shifted < -{a}'sd{1 << (w-1)}) activate = {_literal(-(1 << (w-1)),w)};
      else activate = shifted[W-1:0];
    end
  endfunction
{decl}
{comb}
  reg signed [A-1:0] sum_next;
  always @* begin
    sum_next = acc;
{additions}
  end
  always @(posedge clk) begin
    if (rst) begin
      busy <= 0; phase <= 0; out_valid <= 0; out_data <= 0;
      base <= 0; neuron <= 0; acc <= 0;
      for (k=0; k<NI; k=k+1) x[k] <= 0;
    end else begin
      if (out_valid && out_ready) out_valid <= 0;
      if (in_valid && in_ready) begin
        for (k=0; k<NI; k=k+1) x[k] <= in_data[k*W +: W];
        busy <= 1; phase <= 0; base <= 0; neuron <= 0; acc <= bias(0);
      end else if (busy) begin
{body}
      end
    end
  end
endmodule
'''


def generate_verilog(quantized: Mapping[str, Any], cfg: HardwareConfig) -> str:
    layers = quantized['layers']
    dims = [quantized['input_size']] + [len(layer['bias']) for layer in layers]
    w = cfg.bits
    code = ['// SILICONPILOT generated RTL. Signed saturating fixed-point inference.\n`default_nettype none\n']
    for i,layer in enumerate(layers):
        code.append(_dense(i,dims[i],layer,cfg))
    code.append(f'''module siliconpilot_core(input clk, input rst,
 input [{dims[0]*w-1}:0] in_data, input in_valid, output in_ready,
 output [{dims[-1]*w-1}:0] out_data, output out_valid, input out_ready);''')
    for i,dim in enumerate(dims):
        code.append(f'  wire [{dim*w-1}:0] data_{i}; wire valid_{i}, ready_{i};')
    if cfg.buffering == 2:
        code.append(f'''  reg [{dims[0]*w-1}:0] queue [0:1];
  reg rd_ptr, wr_ptr; reg [1:0] count;
  assign in_ready = count < 2;
  assign data_0 = queue[rd_ptr]; assign valid_0 = count != 0;
  wire push = in_valid && in_ready;
  wire pop = valid_0 && ready_0;
  always @(posedge clk) begin
    if (rst) begin count <= 0; rd_ptr <= 0; wr_ptr <= 0; end
    else begin
      case ({{push,pop}}) 2'b10: count <= count+1; 2'b01: count <= count-1; default: count <= count; endcase
      if (push) begin queue[wr_ptr] <= in_data; wr_ptr <= !wr_ptr; end
      if (pop) rd_ptr <= !rd_ptr;
    end
  end''')
    else:
        code.append('  assign data_0 = in_data; assign valid_0 = in_valid; assign in_ready = ready_0;')
    code.append(f'  assign out_data = data_{len(layers)}; assign out_valid = valid_{len(layers)}; assign ready_{len(layers)} = out_ready;')
    for i in range(len(layers)):
        code.append(f'  sp_dense_{i} stage_{i}(.clk(clk),.rst(rst),.in_data(data_{i}),.in_valid(valid_{i}),.in_ready(ready_{i}),.out_data(data_{i+1}),.out_valid(valid_{i+1}),.out_ready(ready_{i+1}));')
    code.append('endmodule\n')
    code.append(f'''// Pin-efficient streaming shell. Features and scores travel in ascending index order.
module siliconpilot_top(input clk, input rst,
 input [{w-1}:0] in_data, input in_valid, output in_ready,
 output [{w-1}:0] out_data, output out_valid, input out_ready);
  reg [{dims[0]*w-1}:0] vector_in;
  reg vector_valid;
  integer input_index, output_index;
  wire core_ready, core_valid;
  wire [{dims[-1]*w-1}:0] vector_out;
  assign in_ready = !vector_valid;
  assign out_valid = core_valid;
  assign out_data = vector_out[output_index*{w} +: {w}];
  siliconpilot_core core(.clk(clk),.rst(rst),.in_data(vector_in),.in_valid(vector_valid),.in_ready(core_ready),.out_data(vector_out),.out_valid(core_valid),.out_ready(out_ready && output_index == {dims[-1]-1}));
  always @(posedge clk) begin
    if (rst) begin vector_in <= 0; vector_valid <= 0; input_index <= 0; output_index <= 0; end
    else begin
      if (vector_valid && core_ready) vector_valid <= 0;
      if (in_valid && in_ready) begin
        vector_in[input_index*{w} +: {w}] <= in_data;
        if (input_index == {dims[0]-1}) begin input_index <= 0; vector_valid <= 1; end
        else input_index <= input_index + 1;
      end
      if (out_valid && out_ready) begin
        if (output_index == {dims[-1]-1}) output_index <= 0;
        else output_index <= output_index+1;
      end
    end
  end
endmodule
`default_nettype wire
''')
    return '\n'.join(code)


def compile_model(model: Mapping[str, Any], config: HardwareConfig, output_dir: str | Path) -> dict[str, Any]:
    directory = Path(output_dir)
    directory.mkdir(parents=True,exist_ok=True)
    q = quantize(model,config)
    rtl = generate_verilog(q,config)
    dims = [q['input_size']] + [len(layer['bias']) for layer in q['layers']]
    compute = [dims[i+1] * ceil(dims[i]/min(config.parallelism,dims[i])) * (2 if config.pipeline else 1) for i in range(len(q['layers']))]
    latency = sum(compute) + len(compute)-1 + (1 if config.buffering == 2 else 0)
    manifest = {'schema_version':1,'compiler_version':'0.1.0','model_name':q['name'],'config':config.to_dict(),'dimensions':dims,'top':'siliconpilot_top','core_top':'siliconpilot_core','target':{'family':'ECP5','device':'LFE5U-25F','package':'CABGA256','speed':'6'},'latency_cycles':latency,'initiation_interval_cycles':max(compute)+2,'stage_compute_cycles':compute,'latency_scope':'core input handshake to output-valid, empty pipeline, no backpressure; streaming shell serialization excluded','rtl_sha256':hashlib.sha256(rtl.encode()).hexdigest(),'model_sha256':hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'arithmetic':{'input_quantization':'round-to-nearest ties-to-even; signed saturation','weights':'round-to-nearest ties-to-even; signed saturation','bias':'round-to-nearest ties-to-even at 2F; modular wrap A','accumulation':'signed modular A-bit sum','requantization':'arithmetic right shift F (floor), then signed saturation','reset':'synchronous active high; abort all queued/in-flight work','handshake':'valid/ready; output stable while stalled'}}
    (directory/'design.v').write_text(rtl)
    (directory/'weights.json').write_text(json.dumps(q,indent=2)+'\n')
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
