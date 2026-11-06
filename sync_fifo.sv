module sync_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 8    // must be a power of 2
) (
    input  logic                     clk,
    input  logic                     rst_n,
    input  logic                     wr_en,
    input  logic [WIDTH-1:0]         wr_data,
    input  logic                     rd_en,
    output logic [WIDTH-1:0]         rd_data,
    output logic                     full,
    output logic                     empty,
    output logic [$clog2(DEPTH):0]   count
);

    logic [WIDTH-1:0]         mem [0:DEPTH-1];
    logic [$clog2(DEPTH)-1:0] wr_ptr;
    logic [$clog2(DEPTH)-1:0] rd_ptr;

    // A write is ignored when full. A read is ignored when empty.
    logic do_wr;
    logic do_rd;
    assign do_wr = wr_en && !full;
    assign do_rd = rd_en && !empty;

    assign full    = (count == DEPTH);
    assign empty   = (count == 0);
    assign rd_data = mem[rd_ptr];   // always shows the oldest word

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
            count  <= '0;
        end else begin
            if (do_wr) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr      <= wr_ptr + 1'b1;
            end
            if (do_rd) begin
                rd_ptr <= rd_ptr + 1'b1;
            end
            case ({do_wr, do_rd})
                2'b10:   count <= count + 1'b1;
                2'b01:   count <= count - 1'b1;
                default: count <= count;   // both or neither
            endcase
        end
    end

endmodule