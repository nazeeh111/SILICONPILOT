// SILICONPILOT generated RTL. Signed saturating fixed-point inference.
`default_nettype none

// Dense stage 0: 4 -> 8, 2 multiplier lanes.
module sp_dense_0(input clk, input rst,
 input [31:0] in_data, input in_valid, output in_ready,
 output reg [63:0] out_data, output reg out_valid, input out_ready);
  localparam W=8, A=24, NI=4, NO=8, P=2, F=5;
  reg signed [W-1:0] x [0:NI-1];
  reg signed [A-1:0] acc;
  reg busy, phase;
  integer base, neuron, k;
  assign in_ready = !busy && !out_valid;
  function signed [W-1:0] weight;
    input integer address;
    begin case (address)
      0: weight = 8'hfe;
      1: weight = 8'h0;
      2: weight = 8'hff;
      3: weight = 8'hff;
      4: weight = 8'he1;
      5: weight = 8'he2;
      6: weight = 8'hb0;
      7: weight = 8'h4;
      8: weight = 8'hd3;
      9: weight = 8'hf1;
      10: weight = 8'he;
      11: weight = 8'h3f;
      12: weight = 8'he;
      13: weight = 8'h4e;
      14: weight = 8'h28;
      15: weight = 8'he;
      16: weight = 8'h0;
      17: weight = 8'h0;
      18: weight = 8'h1;
      19: weight = 8'hff;
      20: weight = 8'h0;
      21: weight = 8'h0;
      22: weight = 8'h0;
      23: weight = 8'h0;
      24: weight = 8'h1a;
      25: weight = 8'h1d;
      26: weight = 8'h16;
      27: weight = 8'hfd;
      28: weight = 8'hce;
      29: weight = 8'hc9;
      30: weight = 8'hd6;
      31: weight = 8'h5;
      default: weight = 0;
    endcase end
  endfunction
  function signed [A-1:0] bias;
    input integer address;
    begin case (address)
      0: bias = 24'hfff600;
      1: bias = 24'h135;
      2: bias = 24'hfffe5c;
      3: bias = 24'h1f2;
      4: bias = 24'hfff69d;
      5: bias = 24'hfff600;
      6: bias = 24'h5ee;
      7: bias = 24'h3a7;
      default: bias = 0;
    endcase end
  endfunction
  function [W-1:0] activate;
    input signed [A-1:0] value;
    reg signed [A-1:0] shifted;
    begin
      shifted = value >>> F;
      if (1 && shifted < 0) activate = 0;
      else if (shifted > 24'sd127) activate = 8'h7f;
      else if (shifted < -24'sd128) activate = 8'h80;
      else activate = shifted[W-1:0];
    end
  endfunction
  wire signed [15:0] product_0;
  wire signed [15:0] product_1;
  assign product_0 = (base + 0 < NI) ? $signed(x[base+0]) * $signed(weight(neuron*NI+base+0)) : 16'sd0;
  assign product_1 = (base + 1 < NI) ? $signed(x[base+1]) * $signed(weight(neuron*NI+base+1)) : 16'sd0;
  reg signed [A-1:0] sum_next;
  always @* begin
    sum_next = acc;
    sum_next = sum_next + $signed(product_0);
    sum_next = sum_next + $signed(product_1);
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
          if (base + P >= NI) begin
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
          end
      end
    end
  end
endmodule

// Dense stage 1: 8 -> 2, 2 multiplier lanes.
module sp_dense_1(input clk, input rst,
 input [63:0] in_data, input in_valid, output in_ready,
 output reg [15:0] out_data, output reg out_valid, input out_ready);
  localparam W=8, A=24, NI=8, NO=2, P=2, F=5;
  reg signed [W-1:0] x [0:NI-1];
  reg signed [A-1:0] acc;
  reg busy, phase;
  integer base, neuron, k;
  assign in_ready = !busy && !out_valid;
  function signed [W-1:0] weight;
    input integer address;
    begin case (address)
      0: weight = 8'h0;
      1: weight = 8'hf3;
      2: weight = 8'hf8;
      3: weight = 8'h1;
      4: weight = 8'h0;
      5: weight = 8'h0;
      6: weight = 8'hf;
      7: weight = 8'hf6;
      8: weight = 8'h0;
      9: weight = 8'hd;
      10: weight = 8'h8;
      11: weight = 8'hff;
      12: weight = 8'h0;
      13: weight = 8'h0;
      14: weight = 8'hf1;
      15: weight = 8'ha;
      default: weight = 0;
    endcase end
  endfunction
  function signed [A-1:0] bias;
    input integer address;
    begin case (address)
      0: bias = 24'h89;
      1: bias = 24'hffff77;
      default: bias = 0;
    endcase end
  endfunction
  function [W-1:0] activate;
    input signed [A-1:0] value;
    reg signed [A-1:0] shifted;
    begin
      shifted = value >>> F;
      if (0 && shifted < 0) activate = 0;
      else if (shifted > 24'sd127) activate = 8'h7f;
      else if (shifted < -24'sd128) activate = 8'h80;
      else activate = shifted[W-1:0];
    end
  endfunction
  wire signed [15:0] product_0;
  wire signed [15:0] product_1;
  assign product_0 = (base + 0 < NI) ? $signed(x[base+0]) * $signed(weight(neuron*NI+base+0)) : 16'sd0;
  assign product_1 = (base + 1 < NI) ? $signed(x[base+1]) * $signed(weight(neuron*NI+base+1)) : 16'sd0;
  reg signed [A-1:0] sum_next;
  always @* begin
    sum_next = acc;
    sum_next = sum_next + $signed(product_0);
    sum_next = sum_next + $signed(product_1);
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
          if (base + P >= NI) begin
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
          end
      end
    end
  end
endmodule

module siliconpilot_core(input clk, input rst,
 input [31:0] in_data, input in_valid, output in_ready,
 output [15:0] out_data, output out_valid, input out_ready);
  wire [31:0] data_0; wire valid_0, ready_0;
  wire [63:0] data_1; wire valid_1, ready_1;
  wire [15:0] data_2; wire valid_2, ready_2;
  assign data_0 = in_data; assign valid_0 = in_valid; assign in_ready = ready_0;
  assign out_data = data_2; assign out_valid = valid_2; assign ready_2 = out_ready;
  sp_dense_0 stage_0(.clk(clk),.rst(rst),.in_data(data_0),.in_valid(valid_0),.in_ready(ready_0),.out_data(data_1),.out_valid(valid_1),.out_ready(ready_1));
  sp_dense_1 stage_1(.clk(clk),.rst(rst),.in_data(data_1),.in_valid(valid_1),.in_ready(ready_1),.out_data(data_2),.out_valid(valid_2),.out_ready(ready_2));
endmodule

// Pin-efficient streaming shell. Features and scores travel in ascending index order.
module siliconpilot_top(input clk, input rst,
 input [7:0] in_data, input in_valid, output in_ready,
 output [7:0] out_data, output out_valid, input out_ready);
  reg [31:0] vector_in;
  reg vector_valid;
  integer input_index, output_index;
  wire core_ready, core_valid;
  wire [15:0] vector_out;
  assign in_ready = !vector_valid;
  assign out_valid = core_valid;
  assign out_data = vector_out[output_index*8 +: 8];
  siliconpilot_core core(.clk(clk),.rst(rst),.in_data(vector_in),.in_valid(vector_valid),.in_ready(core_ready),.out_data(vector_out),.out_valid(core_valid),.out_ready(out_ready && output_index == 1));
  always @(posedge clk) begin
    if (rst) begin vector_in <= 0; vector_valid <= 0; input_index <= 0; output_index <= 0; end
    else begin
      if (vector_valid && core_ready) vector_valid <= 0;
      if (in_valid && in_ready) begin
        vector_in[input_index*8 +: 8] <= in_data;
        if (input_index == 3) begin input_index <= 0; vector_valid <= 1; end
        else input_index <= input_index + 1;
      end
      if (out_valid && out_ready) begin
        if (output_index == 1) output_index <= 0;
        else output_index <= output_index+1;
      end
    end
  end
endmodule
`default_nettype wire
