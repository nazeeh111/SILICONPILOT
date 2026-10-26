// SILICONPILOT generated RTL. Signed saturating fixed-point inference.
`default_nettype none

// Dense stage 0: 4 -> 8, 1 multiplier lanes.
module sp_dense_0(input clk, input rst,
 input [23:0] in_data, input in_valid, output in_ready,
 output reg [47:0] out_data, output reg out_valid, input out_ready);
  localparam W=6, A=20, NI=4, NO=8, P=1, F=3;
  reg signed [W-1:0] x [0:NI-1];
  reg signed [A-1:0] acc;
  reg busy, phase;
  integer base, neuron, k;
  assign in_ready = !busy && !out_valid;
  function signed [W-1:0] weight;
    input integer address;
    begin case (address)
      0: weight = 6'h0;
      1: weight = 6'h0;
      2: weight = 6'h0;
      3: weight = 6'h0;
      4: weight = 6'h38;
      5: weight = 6'h38;
      6: weight = 6'h2c;
      7: weight = 6'h1;
      8: weight = 6'h35;
      9: weight = 6'h3c;
      10: weight = 6'h3;
      11: weight = 6'h10;
      12: weight = 6'h3;
      13: weight = 6'h14;
      14: weight = 6'ha;
      15: weight = 6'h4;
      16: weight = 6'h0;
      17: weight = 6'h0;
      18: weight = 6'h0;
      19: weight = 6'h0;
      20: weight = 6'h0;
      21: weight = 6'h0;
      22: weight = 6'h0;
      23: weight = 6'h0;
      24: weight = 6'h7;
      25: weight = 6'h7;
      26: weight = 6'h5;
      27: weight = 6'h3f;
      28: weight = 6'h34;
      29: weight = 6'h32;
      30: weight = 6'h36;
      31: weight = 6'h1;
      default: weight = 0;
    endcase end
  endfunction
  function signed [A-1:0] bias;
    input integer address;
    begin case (address)
      0: bias = 20'hfff60;
      1: bias = 20'h13;
      2: bias = 20'hfffe6;
      3: bias = 20'h1f;
      4: bias = 20'hfff6a;
      5: bias = 20'hfff60;
      6: bias = 20'h5f;
      7: bias = 20'h3a;
      default: bias = 0;
    endcase end
  endfunction
  function [W-1:0] activate;
    input signed [A-1:0] value;
    reg signed [A-1:0] shifted;
    begin
      shifted = value >>> F;
      if (1 && shifted < 0) activate = 0;
      else if (shifted > 20'sd31) activate = 6'h1f;
      else if (shifted < -20'sd32) activate = 6'h20;
      else activate = shifted[W-1:0];
    end
  endfunction
  wire signed [11:0] product_0;
  reg signed [11:0] registered_0;
  assign product_0 = (base + 0 < NI) ? $signed(x[base+0]) * $signed(weight(neuron*NI+base+0)) : 12'sd0;
  reg signed [A-1:0] sum_next;
  always @* begin
    sum_next = acc;
    sum_next = sum_next + $signed(registered_0);
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
        if (!phase) begin
          registered_0 <= product_0;
          phase <= 1;
        end else begin
          phase <= 0;
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
  end
endmodule

// Dense stage 1: 8 -> 2, 1 multiplier lanes.
module sp_dense_1(input clk, input rst,
 input [47:0] in_data, input in_valid, output in_ready,
 output reg [11:0] out_data, output reg out_valid, input out_ready);
  localparam W=6, A=20, NI=8, NO=2, P=1, F=3;
  reg signed [W-1:0] x [0:NI-1];
  reg signed [A-1:0] acc;
  reg busy, phase;
  integer base, neuron, k;
  assign in_ready = !busy && !out_valid;
  function signed [W-1:0] weight;
    input integer address;
    begin case (address)
      0: weight = 6'h0;
      1: weight = 6'h3d;
      2: weight = 6'h3e;
      3: weight = 6'h0;
      4: weight = 6'h0;
      5: weight = 6'h0;
      6: weight = 6'h4;
      7: weight = 6'h3e;
      8: weight = 6'h0;
      9: weight = 6'h3;
      10: weight = 6'h2;
      11: weight = 6'h0;
      12: weight = 6'h0;
      13: weight = 6'h0;
      14: weight = 6'h3c;
      15: weight = 6'h2;
      default: weight = 0;
    endcase end
  endfunction
  function signed [A-1:0] bias;
    input integer address;
    begin case (address)
      0: bias = 20'h9;
      1: bias = 20'hffff7;
      default: bias = 0;
    endcase end
  endfunction
  function [W-1:0] activate;
    input signed [A-1:0] value;
    reg signed [A-1:0] shifted;
    begin
      shifted = value >>> F;
      if (0 && shifted < 0) activate = 0;
      else if (shifted > 20'sd31) activate = 6'h1f;
      else if (shifted < -20'sd32) activate = 6'h20;
      else activate = shifted[W-1:0];
    end
  endfunction
  wire signed [11:0] product_0;
  reg signed [11:0] registered_0;
  assign product_0 = (base + 0 < NI) ? $signed(x[base+0]) * $signed(weight(neuron*NI+base+0)) : 12'sd0;
  reg signed [A-1:0] sum_next;
  always @* begin
    sum_next = acc;
    sum_next = sum_next + $signed(registered_0);
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
        if (!phase) begin
          registered_0 <= product_0;
          phase <= 1;
        end else begin
          phase <= 0;
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
  end
endmodule

module siliconpilot_core(input clk, input rst,
 input [23:0] in_data, input in_valid, output in_ready,
 output [11:0] out_data, output out_valid, input out_ready);
  wire [23:0] data_0; wire valid_0, ready_0;
  wire [47:0] data_1; wire valid_1, ready_1;
  wire [11:0] data_2; wire valid_2, ready_2;
  assign data_0 = in_data; assign valid_0 = in_valid; assign in_ready = ready_0;
  assign out_data = data_2; assign out_valid = valid_2; assign ready_2 = out_ready;
  sp_dense_0 stage_0(.clk(clk),.rst(rst),.in_data(data_0),.in_valid(valid_0),.in_ready(ready_0),.out_data(data_1),.out_valid(valid_1),.out_ready(ready_1));
  sp_dense_1 stage_1(.clk(clk),.rst(rst),.in_data(data_1),.in_valid(valid_1),.in_ready(ready_1),.out_data(data_2),.out_valid(valid_2),.out_ready(ready_2));
endmodule

// Pin-efficient streaming shell. Features and scores travel in ascending index order.
module siliconpilot_top(input clk, input rst,
 input [5:0] in_data, input in_valid, output in_ready,
 output [5:0] out_data, output out_valid, input out_ready);
  reg [23:0] vector_in;
  reg vector_valid;
  integer input_index, output_index;
  wire core_ready, core_valid;
  wire [11:0] vector_out;
  assign in_ready = !vector_valid;
  assign out_valid = core_valid;
  assign out_data = vector_out[output_index*6 +: 6];
  siliconpilot_core core(.clk(clk),.rst(rst),.in_data(vector_in),.in_valid(vector_valid),.in_ready(core_ready),.out_data(vector_out),.out_valid(core_valid),.out_ready(out_ready && output_index == 1));
  always @(posedge clk) begin
    if (rst) begin vector_in <= 0; vector_valid <= 0; input_index <= 0; output_index <= 0; end
    else begin
      if (vector_valid && core_ready) vector_valid <= 0;
      if (in_valid && in_ready) begin
        vector_in[input_index*6 +: 6] <= in_data;
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
