/*
 * Copyright (c) 2026 Muhammad Sohair Khan
 * SPDX-License-Identifier: Apache-2.0
 *
 * Sequencer for one APS6404L-3SQR QSPI PSRAM on the TT QSPI Pmod (RAM A),
 * SPI-mode commands only (no QPI state to lose; notes/v2c_02_spec.md):
 *
 *   do_reset : 66h (Reset Enable), /CE high, 99h (Reset)       8 + 8 SCK on IO0
 *   do_write : 38h on IO0, 24-bit address quad (6 SCK), one data byte quad (2 SCK)
 *   do_read  : EBh on IO0, 24-bit address quad (6 SCK), 6 wait clocks,
 *              then 2 SCK per byte for nbytes bytes (quad, high nibble first)
 *
 * Timing (APS6404L Rev 2.7, Table 10 / 9.5): SCK runs without a pause from
 * the first rise to the last fall of a command (tCEM 8 us counts the whole
 * /CE-low time); /CE stays high >= 1 SCK phase + 2 clk between commands
 * (tCPH 18 ns, tRST 50 ns after 99h); mode 0. SCK = clk / (2 * 2^div); the
 * caller refuses div = 3 (clk/16 cannot fit a useful burst in tCEM).
 * Read data are captured exactly as in qspi_fetch: from the free-running
 * input register, (samp + 1) clk after the clock that drops SCK.
 * addr and wdata are not copied: the caller holds them stable while busy.
 *
 * io_oe is driven only while the chip sends (command, address, write data)
 * and is released on the SCK fall after the last address nibble of a read,
 * a full wait period before the RAM drives (tHZ/turnaround).
 */

`default_nettype none

module psram_ctl (
    input  wire        clk,
    input  wire        rst,
    input  wire        abort,
    input  wire [1:0]  div,
    input  wire [1:0]  samp,

    input  wire        do_reset,
    input  wire        do_write,
    input  wire        do_read,
    input  wire [23:0] addr,
    input  wire [7:0]  wdata,
    input  wire [3:0]  nbytes,             // read length, 1..15

    output wire        busy,
    output wire        rd_we,              // one cycle per received byte
    output reg  [3:0]  rd_idx,
    output wire [7:0]  rd_byte,

    output wire        sck,
    output wire        csn,
    output wire [3:0]  io_out,
    output wire [3:0]  io_oe,
    input  wire [3:0]  io_in
);

  localparam [2:0] S_IDLE = 3'd0,
                   S_GAP  = 3'd1,          // /CE high before a command
                   S_CMD  = 3'd2,          // 8 instruction bits on IO0
                   S_ADDR = 3'd3,          // 6 address nibbles
                   S_WAIT = 3'd4,          // 6 wait clocks (read)
                   S_DATA = 3'd5,          // data nibbles (read or write)
                   S_DRAIN= 3'd6,          // SCK stopped, last read nibble in flight
                   S_END  = 3'd7;          // /CE high, tCPH / tRST

  localparam [1:0] K_RST1 = 2'd0, K_RST2 = 2'd1, K_WRITE = 2'd2, K_READ = 2'd3;

  reg [2:0]  state;
  reg [1:0]  kind;
  reg        sck_q, csn_q;
  reg [3:0]  oe_q;
  reg [2:0]  hcnt;
  reg [4:0]  cnt;                          // clocks left in the current phase
  reg [4:0]  nib_out, nib_in;              // read nibbles still to launch / capture
  reg        hi_half;
  reg [3:0]  hi_nib, in_q;
  reg [4:0]  evs;

  wire [2:0] half = (3'd1 << div) - 3'd1;
  wire       tick = (hcnt == 3'd0);
  wire       fall_now = tick && sck_q;
  wire       launch = fall_now && kind == K_READ &&
                      ((state == S_DATA && nib_out != 5'd0) || (state == S_WAIT && cnt == 5'd1));
  wire       grab = evs[samp + 3'd1] && (nib_in != 5'd0);

  // what the chip drives: instruction bit on IO0, then address / write nibbles
  wire [7:0] cmd = (kind == K_RST1) ? 8'h66 : (kind == K_RST2) ? 8'h99 :
                   (kind == K_WRITE) ? 8'h38 : 8'hEB;
  wire [3:0] addr_nib = addr[4*cnt - 1 -: 4];
  wire [3:0] data_nib = cnt[0] ? wdata[3:0] : wdata[7:4];   // cnt 2 -> high, 1 -> low
  assign io_out = (state == S_CMD)  ? {3'b000, cmd[cnt - 1]} :
                  (state == S_ADDR) ? addr_nib :
                  (state == S_DATA && kind == K_WRITE) ? data_nib : 4'b0000;

  assign sck     = sck_q;
  assign csn     = csn_q;
  assign io_oe   = oe_q;
  assign busy    = (state != S_IDLE);
  assign rd_we   = grab && !hi_half;
  assign rd_byte = {hi_nib, in_q};

  always @(posedge clk) in_q <= io_in;

  task start_cmd(input [1:0] k);
    begin
      kind  <= k;
      state <= S_GAP;
      hcnt  <= half;
    end
  endtask

  always @(posedge clk) begin
    evs <= {evs[3:0], launch};
    if (rst || abort) begin
      state  <= S_IDLE;
      sck_q  <= 1'b0;
      csn_q  <= 1'b1;
      oe_q   <= 4'b0000;
      hcnt   <= 3'd0;
      evs    <= 5'd0;
      nib_in <= 5'd0;
      nib_out<= 5'd0;
      rd_idx <= 4'd0;
      hi_half<= 1'b1;
      if (rst) begin kind <= K_RST1; cnt <= 5'd0; hi_nib <= 4'd0; end
    end else begin
      if (hcnt != 3'd0) hcnt <= hcnt - 3'd1;

      if (grab) begin
        nib_in  <= nib_in - 5'd1;
        hi_half <= ~hi_half;
        if (hi_half) hi_nib <= in_q;
        else rd_idx <= rd_idx + 4'd1;
      end

      case (state)
        S_IDLE: begin
          rd_idx  <= 4'd0;
          hi_half <= 1'b1;
          if (do_reset)      start_cmd(K_RST1);
          else if (do_write) start_cmd(K_WRITE);
          else if (do_read) begin
            start_cmd(K_READ);
            nib_out <= {nbytes, 1'b0};
            nib_in  <= {nbytes, 1'b0};
          end
        end
        S_GAP: if (tick) begin
          // /CE low with IO0 = first instruction bit; first rise one phase later
          state <= S_CMD;
          csn_q <= 1'b0;
          oe_q  <= 4'b0001;
          cnt   <= 5'd8;
          hcnt  <= half;
        end
        S_CMD: if (tick) begin
          sck_q <= ~sck_q;
          hcnt  <= half;
          if (sck_q) begin
            cnt <= cnt - 5'd1;
            if (cnt == 5'd1) begin
              if (kind == K_RST1 || kind == K_RST2) begin
                state <= S_END;
                oe_q  <= 4'b0000;
                cnt   <= 5'd3;             // /CE high, then 2 more clk (tRST after 99h)
              end else begin
                state <= S_ADDR;
                oe_q  <= 4'b1111;
                cnt   <= 5'd6;
              end
            end
          end
        end
        S_ADDR: if (tick) begin
          sck_q <= ~sck_q;
          hcnt  <= half;
          if (sck_q) begin
            cnt <= cnt - 5'd1;
            if (cnt == 5'd1) begin
              if (kind == K_WRITE) begin
                state <= S_DATA;
                cnt   <= 5'd2;
              end else begin
                state <= S_WAIT;
                oe_q  <= 4'b0000;          // release: the RAM drives after 6 wait clocks
                cnt   <= 5'd6;
              end
            end
          end
        end
        S_WAIT: if (tick) begin
          sck_q <= ~sck_q;
          hcnt  <= half;
          if (sck_q) begin
            cnt <= cnt - 5'd1;
            if (cnt == 5'd1) begin         // this fall launched the first data nibble
              state   <= S_DATA;
              nib_out <= nib_out - 5'd1;
            end
          end
        end
        S_DATA: if (tick) begin
          if (kind == K_WRITE) begin
            sck_q <= ~sck_q;
            hcnt  <= half;
            if (sck_q) begin
              cnt <= cnt - 5'd1;
              if (cnt == 5'd1) begin
                state <= S_END;
                oe_q  <= 4'b0000;
                cnt   <= 5'd1;
              end
            end
          end else if (!sck_q && nib_out == 5'd0) begin
            state <= S_DRAIN;              // every nibble launched; SCK stays low
          end else begin
            sck_q <= ~sck_q;
            hcnt  <= half;
            if (sck_q) nib_out <= nib_out - 5'd1;
          end
        end
        S_DRAIN: if (nib_in == 5'd0) begin
          state <= S_END;
          cnt   <= 5'd1;
        end
        S_END: begin
          csn_q <= 1'b1;
          if (cnt != 5'd0) cnt <= cnt - 5'd1;
          else if (tick) begin             // >= one SCK phase + cnt clk with /CE high
            if (kind == K_RST1) start_cmd(K_RST2);
            else state <= S_IDLE;
          end
        end
        default: state <= S_IDLE;
      endcase
    end
  end

endmodule
