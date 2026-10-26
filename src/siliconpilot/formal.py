"""Small exhaustive bounded proof of emitted RTL using open-source Yosys SAT.

This proves a representative tiny circuit, not every arbitrary generated network.
The harness tests all 64 signed 3-bit feature combinations and stalls output.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
from .compiler import compile_model
from .model import HardwareConfig, quantize


def prove_tiny(output_dir: str | Path) -> dict:
    yosys=shutil.which('yosys')
    if not yosys:
        raise RuntimeError('formal proof requires yosys on PATH')
    directory=Path(output_dir).resolve();directory.mkdir(parents=True,exist_ok=True)
    cfg=HardwareConfig(bits=3,fractional_bits=1,accumulator_bits=6,parallelism=1,pipeline=False,buffering=1)
    model={'name':'formal-tiny','input_size':2,'layers':[{'op':'dense','weights':[[1.5,-2.],[-2.,1.5]],'bias':[1.25,-1.25]},{'op':'relu'},{'op':'dense','weights':[[1.5,-2.]],'bias':[.25]}]}
    manifest=compile_model(model,cfg,directory)
    q=quantize(model,cfg)
    # Independently spelled reference: 32-bit signed math, explicit low-bit wrapping,
    # floor division (not RTL generator's shift), and scalar min/max saturation.
    w,a,f=cfg.bits,cfg.accumulator_bits,cfg.fractional_bits
    lines=[]
    previous=['$signed(features[2:0])','$signed(features[5:3])']
    for li,layer in enumerate(q['layers']):
        current=[]
        for oi,(weights,bias) in enumerate(zip(layer['weights'],layer['bias'])):
            terms=[f'({expr} * ({int(weight)}))' for expr,weight in zip(previous,weights)]
            lines.append(f'wire signed [{a-1}:0] sum_{li}_{oi} = {bias} + '+ ' + '.join(terms)+';')
            lines.append(f'wire signed [{w-1}:0] ref_{li}_{oi} = reference_activation(sum_{li}_{oi},1\'b{int(layer["relu"])});')
            current.append(f'$signed(ref_{li}_{oi})')
        previous=current
    harness=f'''module formal_harness(input clk,input rst);
  (* anyconst *) reg [5:0] features;
  reg [5:0] age=0;
  wire in_ready,out_valid; wire [2:0] out_data;
  siliconpilot_core dut(.clk(clk),.rst(rst),.in_data(features),.in_valid(age==0 && !rst),.in_ready(in_ready),.out_data(out_data),.out_valid(out_valid),.out_ready(1'b0));
  function signed [2:0] reference_activation;
    input signed [5:0] accumulator;
    input relu;
    integer expanded, floored;
    begin
      expanded=accumulator;
      if (expanded<0) floored=-((-expanded+{(1<<f)-1})/{1<<f});
      else floored=expanded/{1<<f};
      if (relu && floored<0) floored=0;
      if (floored>3) floored=3;
      if (floored< -4) floored=-4;
      reference_activation=floored;
    end
  endfunction
  {chr(10).join(lines)}
  reg prev_valid=0;
  reg [2:0] prev_data=0;
  always @(posedge clk) begin
    if (rst) begin age<=0;prev_valid<=0;prev_data<=0; end
    else begin
      age<=age+1;
      if (age==0) assert(in_ready);
      if (out_valid) assert(out_data==ref_1_0);
      if (age>={manifest['latency_cycles']+1}) assert(out_valid);
      if (prev_valid) begin assert(out_valid);assert(out_data==prev_data); end
      prev_valid<=out_valid;prev_data<=out_data;
    end
  end
endmodule
'''
    (directory/'formal_harness.v').write_text(harness)
    depth=manifest['latency_cycles']+7
    script=f'read_verilog -formal -sv design.v formal_harness.v; prep -top formal_harness -flatten; memory_map; opt; async2sync; chformal -lower; sat -verify -prove-asserts -seq {depth} -set-init-zero -set rst 0 -set-at 1 rst 1 -show-inputs -show-outputs'
    (directory/'proof.ys').write_text(script+'\n')
    proc=subprocess.run([yosys,'-Q','-T','-s','proof.ys'],cwd=directory,text=True,capture_output=True,timeout=180)
    log=proc.stdout+proc.stderr
    (directory/'formal.log').write_text(log)
    success=proc.returncode==0 and 'SUCCESS' in log
    report={'passed':success,'method':'Yosys bounded SAT assertion proof','depth_cycles':depth,'symbolic_input_bits':6,'input_combinations':64,'scope':'one documented representative 2→2→1 3-bit dense/ReLU circuit, all input bit patterns; synchronous initial reset, non-vacuous completion, exact arithmetic and held output throughout bounded depth','limitations':'Does not prove arbitrary models, reset sequences, or implementation timing. General generated circuits are independently simulated.','rtl_sha256':manifest['rtl_sha256'],'tool_version':subprocess.run([yosys,'-V'],capture_output=True,text=True).stdout.strip(),'log':'formal.log'}
    (directory/'formal.json').write_text(json.dumps(report,indent=2)+'\n')
    if not success:
        raise RuntimeError(f'Yosys formal proof failed; inspect {directory / "formal.log"}')
    return report
