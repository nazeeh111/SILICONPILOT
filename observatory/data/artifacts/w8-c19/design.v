// SILICONPILOT generated RTL. Signed saturating fixed-point inference.
`default_nettype none

// Dense stage 0: 4 -> 8, 4 multiplier lanes.
module sp_dense_0(input clk, input rst,
 input [15:0] in_data, input in_valid, output in_ready,
 output reg [31:0] out_data, output reg out_valid, input out_ready);
  localparam W=4, A=8, NI=4, NO=8, P=4, F=1;
  reg signed [W-1:0] x [0:NI-1];
  reg signed [A-1:0] acc;
  reg busy, phase;
  integer base, neuron, k;
  assign in_ready = !busy && !out_valid;
  function signed [W-1:0] weight;
    input integer address;
    begin case (address)
      0: weight = 4'h0;
      1: weight = 4'h0;
      2: weight = 4'h0;
      3: weight = 4'h0;
      4: weight = 4'he;
      5: weight = 4'he;
      6: weight = 4'hb;
      7: weight = 4'h0;
      8: weight = 4'hd;
      9: weight = 4'hf;
      10: weight = 4'h1;
      11: weight = 4'h4;
      12: weight = 4'h1;
      13: weight = 4'h5;
      14: weight = 4'h2;
      15: weight = 4'h1;
      16: weight = 4'h0;
      17: weight = 4'h0;
      18: weight = 4'h0;
      19: weight = 4'h0;
      20: weight = 4'h0;
      21: weight = 4'h0;
      22: weight = 4'h0;
      23: weight = 4'h0;
      24: weight = 4'h2;
      25: weight = 4'h2;
      26: weight = 4'h1;
      27: weight = 4'h0;
      28: weight = 4'hd;
      29: weight = 4'hd;
      30: weight = 4'hd;
      31: weight = 4'h0;
      default: weight = 0;
    endcase end
  endfunction
  function signed [A-1:0] bias;
    input integer address;
    begin case (address)
      0: bias = 8'hf6;
      1: bias = 8'h1;
      2: bias = 8'hfe;
      3: bias = 8'h2;
      4: bias = 8'hf7;
      5: bias = 8'hf6;
      6: bias = 8'h6;
      7: bias = 8'h4;
      default: bias = 0;
    endcase end
  endfunction
  function [W-1:0] activate;
    input signed [A-1:0] value;
    reg signed [A-1:0] shifted;
    begin
      shifted = value >>> F;
      if (1 && shifted < 0) activate = 0;
      else if (shifted > 8'sd7) activate = 4'h7;
      else if (shifted < -8'sd8) activate = 4'h8;
      else activate = shifted[W-1:0];
    end
  endfunction
  wire signed [7:0] product_0;
  wire signed [7:0] product_1;
  wire signed [7:0] product_2;
  wire signed [7:0] product_3;
  assign product_0 = (base + 0 < NI) ? $signed(x[base+0]) * $signed(weight(neuron*NI+base+0)) : 8'sd0;
  assign product_1 = (base + 1 < NI) ? $signed(x[base+1]) * $signed(weight(neuron*NI+base+1)) : 8'sd0;
  assign product_2 = (base + 2 < NI) ? $signed(x[base+2]) * $signed(weight(neuron*NI+base+2)) : 8'sd0;
  assign product_3 = (base + 3 < NI) ? $signed(x[base+3]) * $signed(weight(neuron*NI+base+3)) : 8'sd0;
  reg signed [A-1:0] sum_next;
  always @* begin
    sum_next = acc;
    sum_next = sum_next + $signed(product_0);
    sum_next = sum_next + $signed(product_1);
    sum_next = sum_next + $signed(product_2);
    sum_next = sum_next + $signed(product_3);
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

// Dense stage 1: 8 -> 2, 4 multiplier lanes.
module sp_dense_1(input clk, input rst,
 input [31:0] in_data, input in_valid, output in_ready,
 output reg [7:0] out_data, output reg out_valid, input out_ready);
  localparam W=4, A=8, NI=8, NO=2, P=4, F=1;
  reg signed [W-1:0] x [0:NI-1];
  reg signed [A-1:0] acc;
  reg busy, phase;
  integer base, neuron, k;
  assign in_ready = !busy && !out_valid;
  function signed [W-1:0] weight;
    input integer address;
    begin case (address)
      0: weight = 4'h0;
      1: weight = 4'hf;
      2: weight = 4'h0;
      3: weight = 4'h0;
      4: weight = 4'h0;
      5: weight = 4'h0;
      6: weight = 4'h1;
      7: weight = 4'hf;
      8: weight = 4'h0;
      9: weight = 4'h1;
      10: weight = 4'h0;
      11: weight = 4'h0;
      12: weight = 4'h0;
      13: weight = 4'h0;
      14: weight = 4'hf;
      15: weight = 4'h1;
      default: weight = 0;
    endcase end
  endfunction
  function signed [A-1:0] bias;
    input integer address;
    begin case (address)
      0: bias = 8'h1;
      1: bias = 8'hff;
      default: bias = 0;
    endcase end
  endfunction
  function [W-1:0] activate;
    input signed [A-1:0] value;
    reg signed [A-1:0] shifted;
    begin
      shifted = value >>> F;
      if (0 && shifted < 0) activate = 0;
      else if (shifted > 8'sd7) activate = 4'h7;
      else if (shifted < -8'sd8) activate = 4'h8;
      else activate = shifted[W-1:0];
    end
  endfunction
  wire signed [7:0] product_0;
  wire signed [7:0] product_1;
  wire signed [7:0] product_2;
  wire signed [7:0] product_3;
  assign product_0 = (base + 0 < NI) ? $signed(x[base+0]) * $signed(weight(neuron*NI+base+0)) : 8'sd0;
  assign product_1 = (base + 1 < NI) ? $signed(x[base+1]) * $signed(weight(neuron*NI+base+1)) : 8'sd0;
  assign product_2 = (base + 2 < NI) ? $signed(x[base+2]) * $signed(weight(neuron*NI+base+2)) : 8'sd0;
  assign product_3 = (base + 3 < NI) ? $signed(x[base+3]) * $signed(weight(neuron*NI+base+3)) : 8'sd0;
  reg signed [A-1:0] sum_next;
  always @* begin
    sum_next = acc;
    sum_next = sum_next + $signed(product_0);
    sum_next = sum_next + $signed(product_1);
    sum_next = sum_next + $signed(product_2);
    sum_next = sum_next + $signed(product_3);
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
 input [15:0] in_data, input in_valid, output in_ready,
 output [7:0] out_data, output out_valid, input out_ready);
  wire [15:0] data_0; wire valid_0, ready_0;
  wire [31:0] data_1; wire valid_1, ready_1;
  wire [7:0] data_2; wire valid_2, ready_2;
  reg [15:0] queue [0:1];
  reg rd_ptr, wr_ptr; reg [1:0] count;
  assign in_ready = count < 2;
  assign data_0 = queue[rd_ptr]; assign valid_0 = count != 0;
  wire push = in_valid && in_ready;
  wire pop = valid_0 && ready_0;
  always @(posedge clk) begin
    if (rst) begin count <= 0; rd_ptr <= 0; wr_ptr <= 0; end
    else begin
      case ({push,pop}) 2'b10: count <= count+1; 2'b01: count <= count-1; default: count <= count; endcase
      if (push) begin queue[wr_ptr] <= in_data; wr_ptr <= !wr_ptr; end
      if (pop) rd_ptr <= !rd_ptr;
    end
  end
  assign out_data = data_2; assign out_valid = valid_2; assign ready_2 = out_ready;
  sp_dense_0 stage_0(.clk(clk),.rst(rst),.in_data(data_0),.in_valid(valid_0),.in_ready(ready_0),.out_data(data_1),.out_valid(valid_1),.out_ready(ready_1));
  sp_dense_1 stage_1(.clk(clk),.rst(rst),.in_data(data_1),.in_valid(valid_1),.in_ready(ready_1),.out_data(data_2),.out_valid(valid_2),.out_ready(ready_2));
endmodule

// Pin-efficient streaming shell. Features and scores travel in ascending index order.
module siliconpilot_top(input clk, input rst,
 input [3:0] in_data, input in_valid, output in_ready,
 output [3:0] out_data, output out_valid, input out_ready);
  reg [15:0] vector_in;
  reg vector_valid;
  integer input_index, output_index;
  wire core_ready, core_valid;
  wire [7:0] vector_out;
  assign in_ready = !vector_valid;
  assign out_valid = core_valid;
  assign out_data = vector_out[output_index*4 +: 4];
  siliconpilot_core core(.clk(clk),.rst(rst),.in_data(vector_in),.in_valid(vector_valid),.in_ready(core_ready),.out_data(vector_out),.out_valid(core_valid),.out_ready(out_ready && output_index == 1));
  always @(posedge clk) begin
    if (rst) begin vector_in <= 0; vector_valid <= 0; input_index <= 0; output_index <= 0; end
    else begin
      if (vector_valid && core_ready) vector_valid <= 0;
      if (in_valid && in_ready) begin
        vector_in[input_index*4 +: 4] <= in_data;
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
