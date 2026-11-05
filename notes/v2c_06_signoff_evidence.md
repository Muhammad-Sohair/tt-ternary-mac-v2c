# v2c_06 — Sign-off evidence for `signoff-c` (2026-11-05)

**Candidate:** commit **debe305** (`CTS_DISTANCE_BETWEEN_BUFFERS` 70), CI run **41912700855**
(gds / gl_test / precheck / viewer all success). Netlist = the run's `tt_submission/tt_um_msohair_tmac2c.v`
(= LibreLane `final/pnl`, byte-identical); SDF = the run's `56-openroad-stapostpnr` per-corner SDF.
RTL is unchanged after debe305; later commits are docs, the SDF harness and one testbench rounding fix (§3).

| # | check | result | meets A standard |
|---|---|---|---|
| 1 | A `test.py`, RTL | **14/14** (one run, incl. slow internal saturation) | yes |
| 1 | A `test.py`, gate level, unit delay (TT CI flow, `TMAC_GL_SLOW=1`) | **14/14** (one run) | yes |
| 1 | A `test.py`, gate level, **SDF** max_ss / min_ff / nom_tt | **14/14 / 14/14 / 14/14** (full RTL-sized workload, §2) | yes |
| 2 | "bitn 4−1 = 2" / 3 flash GL failures (netlist 41902595956) | not timing, not a silicon defect: 4-state X-pessimism of a reconvergent sync reset on `qspi_fetch.ptr[2]`; fixed by construction (async reset) in ee36234; proven with SDF at max_ss + min_ff (§4) | yes (resolved) |
| 3 | new max-cap violation | `clkbuf_0_clk/X` (clock root), 0.211 pF vs 0.200 pF limit, max_ss/max_tt/max_ff only (−11.1/−11.2/−11.7 fF), run 41909979592 (09b1546). **Cleared** in 41912700855: 0 at all 9 corners (root now 0.017 pF, fanout 2) | yes |
| 4 | C `test_c.py`: RTL / unit-delay GL / SDF max_ss, min_ff, nom_tt | **10/10 / 10/10 / 10/10, 10/10, 10/10** | yes |
| 4 | C `test_float.py`: RTL / unit GL / SDF ×3 | **1/1 / 1/1 / 1/1 ×3** | yes |
| 4 | A slow test at GL | in row 1 (unit and SDF) | yes |
| 5 | mutation, final RTL ee36234 | control passed (survived); **26/27 caught**; sole survivor #19, proven equivalent for f_SCK ≤ f_clk/16 (v2c_05 §2) | yes |
| 6 | hardening vs A | table below | yes, stricter than A |

| run | util | slew | cap | fanout | setup WS (worst) | hold WS (worst) | DRC (magic/route) | LVS | antenna | precheck |
|---|---|---|---|---|---|---|---|---|---|---|
| C 41912700855 | 79.3 % | 0 all corners | 0 | 0 | +5.228 max_ss | +0.100 min_ff | 0/0 | 0 | 0 | pass |
| A 40677816085 (`signoff-a`) | 63.8 % | 5 pins max_ss (accepted) | 0 | 2 (accepted) | +4.883 max_ss | +0.103 max_ff | 0/0 | 0 | 0 | pass |

Setup / hold WS (ns) per corner, C (A):
nom_tt 11.823/0.298 (12.653/0.310) · nom_ss 5.290/0.816 (5.005/0.866) · nom_ff 13.334/0.103 (13.864/0.106) ·
min_tt 11.891/0.295 (12.720/0.307) · min_ss 5.359/0.815 (5.124/0.860) · min_ff 13.388/0.100 (13.892/0.106) ·
max_tt 11.764/0.300 (12.582/0.314) · max_ss 5.228/0.819 (4.883/0.872) · max_ff 13.283/0.103 (13.833/0.103).
Clock latency skew max_ss 0.426 ns (A 0.20): not a violation; hold met everywhere (open decision in the handoff).

## 1. Earlier report, corrected

"3 flash tests failed at gate level" was netlist **41902595956** (pre-ee36234), not the candidate. On the
candidate, A's GL suite was previously reported as "13/13 in CI + slow 1/1 locally"; it is now one 14/14 run.

## 2. SDF simulation — method and its limits

Icarus Verilog 12, `-gspecify`, sky130_fd_sc_hd **timing** models (no `FUNCTIONAL`, no `UNIT_DELAY`),
`$sdf_annotate` of the sign-off SDF. Harness in `test/sdf/`. Three things Icarus does not do, and what was done:

1. **Timing checks are not evaluated** (`$setuphold`, `$recrem`, `$width`); their `*_delayed` nets are left
   undriven, which kills every flop. `patch_lib.py` ties `X_delayed = X`. Consequence: the sim does not flag
   setup/hold violations; those are covered by STA at all 9 corners (no violations, row 6).
2. **SDF `INTERCONNECT` is ignored silently** (measured: clk→clkbuf_0_clk.A 0 ns instead of 0.150 ns).
   `fold_ic.py` folds every wire delay into the load cell's IOPATH (rise/fall mapped by arc unateness; 12,987
   load pins) and output-port wires into the driver (19/19). Not foldable: flop D / RESET_B pin wires (no arc
   from them): ≤ 6 ps at max_ss, ≤ 4 ps at min_ff — setup/hold only, covered by STA. Non-unate rounding ≤ 1 ps.
3. An empty top-level `ABSOLUTE` block after removing INTERCONNECTs is an SDF syntax error; `fold_ic.py`
   removes it. **Every run reported here has 0 `SDF ERROR`/`SDF WARNING` lines** (a first batch with that
   error was discarded and rerun).

**Validation against STA:** simulated clock insertion to all 557 flops = 1.356–1.632 ns (max_ss),
0.500–0.602 ns (min_ff); STA `report_clock_latency` max_ss 1.289 (`_8004_`) – 1.715 (`_7931_`) ns, the same two
flops, and equal to the sim × the SDC derates (1.289/0.95 = 1.357, 1.715/1.05 = 1.633). Cell IOPATHs annotate
exactly (clkbuf_0_clk 0.284/0.279 ns max_ss, 0.098/0.099 min_ff).

A `test.py` under SDF ran **without** `GATES=yes`, i.e. its RTL-sized workload (40 random trials, all shapes,
all dividers, all timing cases), a superset of the GL mode. `test_c`/`test_float` under SDF ran with
`GATES=yes` (the GL mode CI uses; it only drops `test_c`'s RTL-internal monitor and its coverage assert).

## 3. Testbench change made for SDF (not a relaxation)

`test_c.py` `PmodBus._later`: `Timer(delay, unit="ns", round_mode="round")`. With SDF, pin edges fall on
fractional picoseconds and `when - now` (float ns) was not exactly representable (`ValueError ... 5.554999999934807
ns`). Rounding to the simulator's 1 ps step changes no check. Re-verified: `test_c` RTL 10/10, unit-delay GL 10/10.

## 4. Row 2 settled with SDF

Netlist 41902595956 + its own sign-off SDF (folded the same way), A's 5 flash tests:

| corner | `ptr[2]` flop `_8124_` power-up | result |
|---|---|---|
| max_ss | X (simulator default) | 2/5 — same 3 failures ("IO0 not driven at command bit 31", rows one byte late) |
| max_ss | held 0 through reset | **5/5**, no X on the loop after reset |
| max_ss | held 1 through reset | **5/5** |
| min_ff | X / 0 / 1 | 2/5 / **5/5** / **5/5** |

The failure is identical with real delays at both corners, so it is **not a timing artifact**. With any
resolved power-up value (what silicon has) the netlist is correct, so it is **not a netlist defect**. Cause:
the loop `_8124_.Q → hold684 → _6466_/_6467_ → hold685 → _8124_.D`, under reset D = ¬(Q∧`_2776_`)∧(… ∨ Q) =
Q∧¬Q: 0 for Q = 0 or 1, X for Q = X. The "4−1 = 2" reading of `bitn` was my probe sampling the counter at the
wrong time (retracted in v2c_05); the real symptom was IO0 = X while carrying `cmd_word[2]`. Resolution: `ptr`
has an asynchronous reset since ee36234; the candidate netlist has no X after reset (post-reset X scan) and
passes everything above. Emulation method: force `_8124_`'s D net (`net685`) for the whole reset period and
release it at `rst_n` rise (forcing only 2 clocks before `rst_n` was driven re-captured X: method error, fixed).
