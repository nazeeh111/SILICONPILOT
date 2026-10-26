module formal_harness(input clk,input rst);
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
      if (expanded<0) floored=-((-expanded+1)/2);
      else floored=expanded/2;
      if (relu && floored<0) floored=0;
      if (floored>3) floored=3;
      if (floored< -4) floored=-4;
      reference_activation=floored;
    end
  endfunction
  wire signed [5:0] sum_0_0 = 5 + ($signed(features[2:0]) * (3)) + ($signed(features[5:3]) * (-4));
wire signed [2:0] ref_0_0 = reference_activation(sum_0_0,1'b1);
wire signed [5:0] sum_0_1 = -5 + ($signed(features[2:0]) * (-4)) + ($signed(features[5:3]) * (3));
wire signed [2:0] ref_0_1 = reference_activation(sum_0_1,1'b1);
wire signed [5:0] sum_1_0 = 1 + ($signed(ref_0_0) * (3)) + ($signed(ref_0_1) * (-4));
wire signed [2:0] ref_1_0 = reference_activation(sum_1_0,1'b0);
  reg prev_valid=0;
  reg [2:0] prev_data=0;
  always @(posedge clk) begin
    if (rst) begin age<=0;prev_valid<=0;prev_data<=0; end
    else begin
      age<=age+1;
      if (age==0) assert(in_ready);
      if (out_valid) assert(out_data==ref_1_0);
      if (age>=8) assert(out_valid);
      if (prev_valid) begin assert(out_valid);assert(out_data==prev_data); end
      prev_valid<=out_valid;prev_data<=out_data;
    end
  end
endmodule
