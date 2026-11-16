"""Independent black-box RTL verification through Icarus Verilog."""
from __future__ import annotations
import json
import random
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence
from .compiler import compile_model
from .model import HardwareConfig, quantize
from .reference import evaluate_integer


def boundary_vectors(size: int, bits: int, count: int = 64, seed: int = 1729) -> list[list[int]]:
    lo, hi = -(1 << (bits-1)), (1 << (bits-1))-1
    vectors = [[0]*size,[lo]*size,[hi]*size,[lo if i%2 else hi for i in range(size)],[1]*size,[-1]*size]
    for i in range(size):
        row = [0]*size
        row[i] = hi
        vectors.append(row)
        row = [0]*size
        row[i] = lo
        vectors.append(row)
    rng = random.Random(seed)
    vectors.extend([[rng.randint(lo,hi) for _ in range(size)] for _ in range(count)])
    return vectors


def _pack(values: Sequence[int], bits: int) -> int:
    return sum((int(v) % (1 << bits)) << (i*bits) for i,v in enumerate(values))


def _testbench(ni: int, no: int, bits: int, count: int, latency: int, streaming: bool) -> str:
    ib,ob = (bits,bits) if streaming else (ni*bits,no*bits)
    top = 'siliconpilot_top' if streaming else 'siliconpilot_core'
    send = f'''        in_valid = (sent < N) && (input_was_stalled || ((lfsr & 7) != 0));
        in_data = input_vectors[sent][input_index*W +: W];''' if streaming else '''        in_valid = (sent < N) && (input_was_stalled || ((lfsr & 7) != 0));
        in_data = input_vectors[sent];'''
    accept = f'''          if (input_index == NI-1) begin sent_at[sent] = cycles; sent = sent+1; input_index=0; end
          else input_index=input_index+1;''' if streaming else '''          sent_at[sent] = cycles; sent = sent+1;'''
    compare = '''          if (out_data !== expected[received][output_index*W +: W]) begin
            $display("MISMATCH sample=%0d score=%0d got=%h expected=%h",received,output_index,out_data,expected[received][output_index*W +: W]); $fatal(1);
          end
          if (output_index == NO-1) begin received=received+1; output_index=0; end
          else output_index=output_index+1;''' if streaming else '''          if (out_data !== expected[received]) begin
            $display("MISMATCH sample=%0d got=%h expected=%h",received,out_data,expected[received]); $fatal(1);
          end
          $display("RESULT %0d %0d",received,cycles-sent_at[received]-1);
          received=received+1;'''
    return f'''`timescale 1ns/1ps
module tb;
  localparam N={count}, NI={ni}, NO={no}, W={bits};
  reg clk=0; always #5 clk=!clk;
  reg rst=1, in_valid=0, out_ready=0;
  reg [{ib-1}:0] in_data=0;
  wire in_ready, out_valid; wire [{ob-1}:0] out_data;
  {top} dut(.clk(clk),.rst(rst),.in_data(in_data),.in_valid(in_valid),.in_ready(in_ready),.out_data(out_data),.out_valid(out_valid),.out_ready(out_ready));
  reg [NI*W-1:0] input_vectors[0:N-1]; reg [NO*W-1:0] expected[0:N-1];
  integer sent_at[0:N-1];
  integer sent=0,received=0,cycles=0,input_index=0,output_index=0,stalls=0,first_valid=-1,reset_checks=0;
  reg active=0, was_stalled=0, input_was_stalled=0;
  reg [{ob-1}:0] held_data;
  reg [31:0] lfsr=32'h5eed1234;
  initial begin
    $readmemh("inputs.hex",input_vectors); $readmemh("expected.hex",expected);
    $dumpfile("{'streaming' if streaming else 'waveform'}.vcd"); $dumpvars(0,tb);
    repeat(3) @(negedge clk);
    rst=0; in_valid=1; in_data=input_vectors[0]; out_ready=0;
    repeat({ni+3 if streaming else 3}) @(negedge clk);
    rst=1; in_valid=0;
    repeat(2) @(negedge clk);
    rst=0; in_valid=1;
    repeat({latency+ni+no+8}) @(negedge clk);
    if (!out_valid) $fatal(1,"reset setup did not reach stalled output");
    rst=1; in_valid=0;
    repeat(2) @(negedge clk);
    rst=0; active=1;
  end
  always @(negedge clk) begin
    if (active) begin
      lfsr = {{lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]}};
      out_ready = cycles < {latency+5} ? 0 : ((lfsr & 3) != 0);
{send}
    end
  end
  always @(posedge clk) begin
    if (active && !rst) begin
      cycles=cycles+1;
      input_was_stalled=in_valid && !in_ready;
      if (cycles > 2500) $dumpoff;
      if (was_stalled && (!out_valid || out_data !== held_data)) begin $display("STABILITY_FAILURE"); $fatal(1); end
      if (out_valid && first_valid < 0) first_valid=cycles;
      was_stalled=out_valid && !out_ready;
      if (was_stalled) begin held_data=out_data; stalls=stalls+1; end
      if (in_valid && in_ready && sent<N) begin
{accept}
      end
      if (out_valid && out_ready) begin
        if (received>=N) $fatal(1,"unexpected extra output");
{compare}
      end
      if (received==N) begin
        $display("PASS samples=%0d cycles=%0d stalls=%0d first_latency=%0d reset_checks=%0d",received,cycles,stalls,first_valid-sent_at[0]-1,reset_checks);
        $finish;
      end
      if (cycles > {count*(latency+ni+no+15)*8}) $fatal(1,"TIMEOUT");
    end
    if (rst) begin #1; reset_checks=reset_checks+1; if (out_valid) $fatal(1,"reset failed to clear valid"); end
  end
endmodule
'''


def _schedule_testbench(ni: int, no: int, bits: int, count: int, transactions: int,
                        latency: int, interval: int) -> str:
    """Measure continuous-traffic output spacing, independently of RTL internals."""
    return f'''`timescale 1ns/1ps
module tb;
  localparam N={count}, RUN={transactions}, NI={ni}, NO={no}, W={bits};
  reg clk=0; always #5 clk=!clk;
  reg rst=1, in_valid=0;
  reg [NI*W-1:0] in_data=0;
  wire in_ready, out_valid;
  wire [NO*W-1:0] out_data;
  siliconpilot_core dut(.clk(clk),.rst(rst),.in_data(in_data),.in_valid(in_valid),
    .in_ready(in_ready),.out_data(out_data),.out_valid(out_valid),.out_ready(1'b1));
  reg [NI*W-1:0] input_vectors[0:N-1];
  reg [NO*W-1:0] expected[0:N-1];
  integer sent=0, received=0, cycles=0, first_sent=-1, previous_output=-1;
  integer measured_latency=-1, measured_interval=-1;
  initial begin
    $readmemh("inputs.hex",input_vectors);
    $readmemh("expected.hex",expected);
    repeat(3) @(negedge clk);
    rst=0;
  end
  always @(negedge clk) begin
    if (!rst) begin
      in_valid = sent < RUN;
      if (sent < RUN) in_data = input_vectors[sent];
    end
  end
  always @(posedge clk) begin
    if (!rst) begin
      cycles=cycles+1;
      if (in_valid && in_ready) begin
        if (sent==0) first_sent=cycles;
        sent=sent+1;
      end
      if (out_valid) begin
        if (received>=sent || out_data !== expected[received])
          $fatal(1,"SCHEDULE_DATA_MISMATCH sample=%0d got=%h",received,out_data);
        if (received==0) begin
          measured_latency=cycles-first_sent-1;
          if (measured_latency!={latency})
            $fatal(1,"SCHEDULE_LATENCY got=%0d expected={latency}",measured_latency);
        end else begin
          measured_interval=cycles-previous_output;
          if (measured_interval!={interval})
            $fatal(1,"SCHEDULE_INTERVAL got=%0d expected={interval}",measured_interval);
        end
        previous_output=cycles;
        received=received+1;
      end
      if (received==RUN && cycles-previous_output>{latency+interval}) begin
        $display("SCHEDULE_PASS samples=%0d latency=%0d interval=%0d",received,measured_latency,measured_interval);
        $finish;
      end
      if (cycles>{transactions*(latency+interval+4)}) $fatal(1,"SCHEDULE_TIMEOUT");
    end
  end
endmodule
'''


def _simulate(directory: Path, name: str, testbench: str, iverilog: str, vvp: str) -> str:
    (directory/f'tb_{name}.v').write_text(testbench)
    commands = [[iverilog,'-g2012','-s','tb','-o',f'sim_{name}','design.v',f'tb_{name}.v'],
                [vvp,f'sim_{name}']]
    output = []
    for command in commands:
        try:
            proc = subprocess.run(command,cwd=directory,text=True,capture_output=True,timeout=180)
        except subprocess.TimeoutExpired as exc:
            (directory/f'{name}.log').write_text('\n'.join(output) + '\n' + str(exc))
            raise RuntimeError(f'{name} RTL verification timed out; see {name}.log') from exc
        output.append(proc.stdout+proc.stderr)
        (directory/f'{name}.log').write_text('\n'.join(output))
        if proc.returncode:
            raise RuntimeError(f'{name} RTL verification failed: {proc.stdout[-2000:]} {proc.stderr[-2000:]}')
    return '\n'.join(output)


def verify_model(model: Mapping[str, Any], config: HardwareConfig, output_dir: str | Path, vectors: Sequence[Sequence[int]] | None = None, *, random_count: int = 64, include_streaming: bool = True) -> dict[str, Any]:
    directory = Path(output_dir).resolve()
    manifest=compile_model(model,config,directory)
    iverilog, vvp = shutil.which('iverilog'),shutil.which('vvp')
    if not iverilog or not vvp:
        raise RuntimeError('RTL verification requires iverilog and vvp on PATH')
    q=quantize(model,config)
    samples=boundary_vectors(q['input_size'],config.bits,random_count)
    if vectors is not None:
        samples.extend([list(map(int,row)) for row in vectors])
    expected=[evaluate_integer(q,row) for row in samples]
    ni,no=q['input_size'],len(q['layers'][-1]['bias'])
    (directory/'inputs.hex').write_text('\n'.join(f'{_pack(row,config.bits):0{(ni*config.bits+3)//4}x}' for row in samples)+'\n')
    (directory/'expected.hex').write_text('\n'.join(f'{_pack(row,config.bits):0{(no*config.bits+3)//4}x}' for row in expected)+'\n')
    results={}
    for streaming in ([False,True] if include_streaming else [False]):
        name='streaming' if streaming else 'core'
        tb=_testbench(ni,no,config.bits,len(samples),manifest['latency_cycles'],streaming)
        log=_simulate(directory,name,tb,iverilog,vvp)
        match=re.search(r'PASS samples=(\d+) cycles=(\d+) stalls=(\d+) first_latency=(-?\d+) reset_checks=(\d+)',log)
        if not match:
            raise RuntimeError(f'{name} simulation did not produce PASS evidence')
        results[name]={'passed':True,'samples':int(match[1]),'simulation_cycles':int(match[2]),'backpressure_cycles':int(match[3]),'first_latency_cycles':int(match[4]),'reset_assertion_checks':int(match[5]),'waveform':f'{"streaming" if streaming else "waveform"}.vcd','log':f'{name}.log'}
        if not streaming and int(match[4]) != manifest['latency_cycles']:
            raise RuntimeError(f'cycle model mismatch: expected {manifest["latency_cycles"]}, measured {match[4]}')
    transactions = min(len(samples), 2*len(q['layers'])+8)
    tb = _schedule_testbench(ni,no,config.bits,len(samples),transactions,
                             manifest['latency_cycles'],manifest['initiation_interval_cycles'])
    log = _simulate(directory,'schedule',tb,iverilog,vvp)
    match = re.search(r'SCHEDULE_PASS samples=(\d+) latency=(\d+) interval=(\d+)',log)
    if not match or int(match[1]) != transactions:
        raise RuntimeError('schedule simulation did not produce complete matching sample evidence')
    results['schedule'] = {'passed':True,'samples':int(match[1]),'latency_cycles':int(match[2]),
                           'initiation_interval_cycles':int(match[3]),'log':'schedule.log',
                           'scope':'continuous core input, always-ready output; every consecutive output interval and post-drain silence checked'}
    report={'schema_version':1,'passed':True,'samples':len(samples),'boundary_and_random_samples':len(samples)-(len(vectors) if vectors is not None else 0),'dataset_samples':len(vectors) if vectors is not None else 0,'latency_cycles':results['core']['first_latency_cycles'],'tests':['integer bit equality','boundary values','seeded random values','output stability under backpressure','reset with in-flight input and stalled completed output','packed core handshake']+(['streaming shell handshake and score ordering'] if include_streaming else []),'simulator':subprocess.run([iverilog,'-V'],capture_output=True,text=True).stdout.splitlines()[0],'results':results,'rtl_sha256':manifest['rtl_sha256']}
    report['schedule_revision'] = manifest['schedule_revision']
    report['initiation_interval_cycles'] = results['schedule']['initiation_interval_cycles']
    report['tests'].append('continuous-traffic core latency and output interval')
    (directory/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
