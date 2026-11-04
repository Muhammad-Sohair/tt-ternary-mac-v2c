# SPDX-License-Identifier: Apache-2.0
"""Mutation batch for TMAC2C: A's flash mutants (re-pointed at C's files) plus mutants in the new
logic (byte-pointer pause/resume, the RAM sequencer, the arbiter and ARUN). Each mutant is applied,
C's RAM tests (test_c) and A's flash tests (test.py test_flash_*) are run, the file is restored.
Mutant 0 is the no-mutation control: it must SURVIVE (all tests pass), or the batch means nothing.

Run from test/ with the venv's Scripts first on PATH:  python mutate_c.py [indices...]
"""
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOP = "src/tt_um_msohair_tmac2c.v"
QF = "src/qspi_fetch.v"
PS = "src/psram_ctl.v"

M = [
    # ---- control ----
    ("CONTROL (no mutation)", QF, "localparam [7:0] CMD = 8'h6B;", "localparam [7:0] CMD = 8'h6B;"),
    # ---- A's flash mutants (v2 batch), on C's copy ----
    ("A: instruction 6Bh -> 6Ch", QF, "localparam [7:0] CMD = 8'h6B;", "localparam [7:0] CMD = 8'h6C;"),
    ("A: nibble order swapped", QF, "assign wbyte   = {hi_nib, in_q};", "assign wbyte   = {in_q, hi_nib};"),
    ("A: 7 dummy clocks instead of 8", QF, "bitn  <= 6'd8;", "bitn  <= 6'd7;"),
    ("A: sample point one clk early", QF, "wire       grab = evs[samp + 3'd1]", "wire       grab = evs[samp]"),
    ("A: compute does not wait for weights", TOP,
     "wire fc_fire  = fc_pend && f_ready && !bist_busy;", "wire fc_fire  = fc_pend && !bist_busy;"),
    ("A: OVERRUN never set", TOP,
     "if (s_a_we && fc_pend && !fc_fire) f_overrun <= 1'b1;", "if (1'b0) f_overrun <= 1'b1;"),
    ("A: IO0 not released for the dummy clocks", QF,
     "oe_q  <= 1'b0;               // IOs high-Z", "oe_q  <= 1'b1;               // IOs high-Z"),
    ("A: RAM B /CS driven low", TOP, "assign uio_out = {1'b1, r_csn,", "assign uio_out = {1'b0, r_csn,"),
    ("A: write address steps on every nibble", QF,
     "        if (hi_half) hi_nib <= in_q;\n        else begin", "        if (hi_half) hi_nib <= in_q;\n        if (1'b1) begin"),
    ("A: next chunk one nibble short", QF,
     "          nib_out <= 2 * CHUNK;\n          nib_in  <= 2 * CHUNK;\n          hi_half <= 1'b1;\n          hcnt    <= half;\n        end else if (pause)",
     "          nib_out <= 2 * CHUNK - 1;\n          nib_in  <= 2 * CHUNK;\n          hi_half <= 1'b1;\n          hcnt    <= half;\n        end else if (pause)"),
    # ---- C: byte pointer and pause/resume (decision R1) ----
    ("C: resume at the page start, not the byte", QF,
     "wire [31:0] cmd_word = {CMD, ptr};", "wire [31:0] cmd_word = {CMD, ptr[23:8], 8'h00};"),
    ("C: byte pointer never advances", QF, "          ptr   <= ptr + 24'd1;", "          ptr   <= ptr;"),
    ("C: pause ignored (flash stays selected)", QF, "        end else if (pause) begin", "        end else if (1'b0) begin"),
    # ---- C: RAM sequencer ----
    ("C: RAM read with 5 wait clocks", PS,
     "                oe_q  <= 4'b0000;          // release: the RAM drives after 6 wait clocks\n                cnt   <= 5'd6;",
     "                oe_q  <= 4'b0000;          // release: the RAM drives after 6 wait clocks\n                cnt   <= 5'd5;"),
    ("C: RAM read nibbles swapped", PS, "assign rd_byte = {hi_nib, in_q};", "assign rd_byte = {in_q, hi_nib};"),
    ("C: RAM write nibbles swapped", PS,
     "wire [3:0] data_nib = cnt[0] ? w_q[3:0] : w_q[7:4];", "wire [3:0] data_nib = cnt[0] ? w_q[7:4] : w_q[3:0];"),
    ("C: reset sends 99h without 66h", PS,
     "if (do_reset)      start_cmd(K_RST1, 8'h66);", "if (do_reset)      start_cmd(K_RST2, 8'h99);"),
    ("C: address on IO0 only (IO1..3 not enabled)", PS,
     "                state <= S_ADDR;\n                oe_q  <= 4'b1111;", "                state <= S_ADDR;\n                oe_q  <= 4'b0001;"),
    # ---- C: arbiter and ARUN ----
    ("C: RAM used without pausing the flash", TOP,
     "        X_ACQ: if (!f_busy && !f_open) x_state <= X_GO;", "        X_ACQ: if (!f_busy) x_state <= X_GO;"),
    ("C: second chunk reads the first chunk's activations", TOP,
     "wire [3:0] x_a_idx  = {1'b0, x_j, 2'b00} + {3'b000, x_j} + {1'b0, x_k};",
     "wire [3:0] x_a_idx  = {1'b0, x_k};"),
    ("C: next RAM visit 5 bytes on instead of 10", TOP,
     "else begin x_addr <= x_addr + 24'd10; x_state <= X_RCHK; end", "else begin x_addr <= x_addr + 24'd5; x_state <= X_RCHK; end"),
    ("C: clk/16 not refused", TOP, "wire        x_div_bad = (f_div == 2'd3);", "wire        x_div_bad = 1'b0;"),
    ("C: AWRITE before AINIT accepted", TOP,
     "            if (!x_init) x_noinit <= 1'b1;\n            else if (x_div_bad) x_err_div <= 1'b1;\n            else begin x_kind <= XK_WRITE;",
     "            if (1'b0) x_noinit <= 1'b1;\n            else if (x_div_bad) x_err_div <= 1'b1;\n            else begin x_kind <= XK_WRITE;"),
    ("C: opcodes not blocked during a RAM operation", TOP,
     "  wire op_blocked = x_busy && (", "  wire op_blocked = 1'b0 && ("),
]

env = dict(os.environ, PWD=str(ROOT / "test").replace("\\", "/"))
RUNS = [("test_c", []), ("test", ["COCOTB_TEST_FILTER=test_flash_"])]
only = sys.argv[1:]
for i, (name, f, old, new) in enumerate(M):
    if only and str(i) not in only:
        continue
    p = ROOT / f
    orig = p.read_text()
    assert orig.count(old) == 1, f"mutant {i} pattern not unique/found: {old!r}"
    p.write_text(orig.replace(old, new), newline="\n")
    try:
        caught = []
        for mod, extra in RUNS:
            r = subprocess.run(["mingw32-make", f"COCOTB_TEST_MODULES={mod}"] + extra, cwd=ROOT / "test",
                               env=env, capture_output=True, text=True, timeout=7200)
            out = r.stdout + r.stderr
            fails = re.findall(r"\*\* (\S+)\s+FAIL", out)
            if "FAIL=0" not in out:
                msg = re.findall(r"(AssertionError: .*|PsramViolation: .*|Error: .*|error: .*)", out)
                caught.append((mod, fails[:3], (msg[0] if msg else "no result: " + out[-160:].replace("\n", " "))[:160]))
        status = "CAUGHT" if caught else "SURVIVED"
        print(f"[{i:2d}] {status}: {name}")
        for mod, fl, m in caught[:2]:
            print(f"      {mod} {fl}: {m}")
        sys.stdout.flush()
    finally:
        p.write_text(orig, newline="\n")
