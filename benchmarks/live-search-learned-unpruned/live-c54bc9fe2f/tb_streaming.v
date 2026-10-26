`timescale 1ns/1ps
module tb;
  localparam N=353, NI=4, NO=2, W=8;
  reg clk=0; always #5 clk=!clk;
  reg rst=1, in_valid=0, out_ready=0;
  reg [7:0] in_data=0;
  wire in_ready, out_valid; wire [7:0] out_data;
  siliconpilot_top dut(.clk(clk),.rst(rst),.in_data(in_data),.in_valid(in_valid),.in_ready(in_ready),.out_data(out_data),.out_valid(out_valid),.out_ready(out_ready));
  reg [NI*W-1:0] input_vectors[0:N-1]; reg [NO*W-1:0] expected[0:N-1];
  integer sent_at[0:N-1];
  integer sent=0,received=0,cycles=0,input_index=0,output_index=0,stalls=0,first_valid=-1;
  reg active=0, was_stalled=0, input_was_stalled=0;
  reg [7:0] held_data;
  reg [31:0] lfsr=32'h5eed1234;
  initial begin
    $readmemh("inputs.hex",input_vectors); $readmemh("expected.hex",expected);
    $dumpfile("streaming.vcd"); $dumpvars(0,tb);
    repeat(3) @(negedge clk);
    rst=0; in_valid=1; in_data=input_vectors[0]; out_ready=0;
    repeat(7) @(negedge clk);
    rst=1; in_valid=0;
    repeat(2) @(negedge clk);
    rst=0; in_valid=1;
    repeat(27) @(negedge clk);
    if (!out_valid) $fatal(1,"reset setup did not reach stalled output");
    rst=1; in_valid=0;
    repeat(2) @(negedge clk);
    rst=0; active=1;
  end
  always @(negedge clk) begin
    if (active) begin
      lfsr = {lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
      out_ready = cycles < 18 ? 0 : ((lfsr & 3) != 0);
        in_valid = (sent < N) && (input_was_stalled || ((lfsr & 7) != 0));
        in_data = input_vectors[sent][input_index*W +: W];
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
          if (input_index == NI-1) begin sent_at[sent] = cycles; sent = sent+1; input_index=0; end
          else input_index=input_index+1;
      end
      if (out_valid && out_ready) begin
        if (received>=N) $fatal(1,"unexpected extra output");
          if (out_data !== expected[received][output_index*W +: W]) begin
            $display("MISMATCH sample=%0d score=%0d got=%h expected=%h",received,output_index,out_data,expected[received][output_index*W +: W]); $fatal(1);
          end
          if (output_index == NO-1) begin received=received+1; output_index=0; end
          else output_index=output_index+1;
      end
      if (received==N) begin
        $display("PASS samples=%0d cycles=%0d stalls=%0d first_latency=%0d",received,cycles,stalls,first_valid-sent_at[0]-1);
        $finish;
      end
      if (cycles > 96016) $fatal(1,"TIMEOUT");
    end
    if (rst) begin #1; if (out_valid) $fatal(1,"reset failed to clear valid"); end
  end
endmodule
