# Session handoff — 2026-11-05 (v2c, TMAC2C) — overnight run

A (`tt-ternary-mac-v2`, `signoff-a`) and B (`tt-ternary-mac-v2b`) were not touched. Nothing submitted, paid,
posted, or changed in GitHub settings. All work is on `Muhammad-Sohair/tt-ternary-mac-v2c` `main`.

## 1. Gate status

| gate | date | status |
|---|---|---|
| 1 datasheets | 8 Nov | **passed 4 Nov** |
| 2 RTL + tests passing | 15 Nov | **on track — all items met except the final mutation batch, which is running** (see §3 and §6) |
| 3 full A-standard sign-off | 22 Nov | **on track if the clock-root fix holds**: gate level now passes on the real netlist; one clock-net residual left (§4, §5) |

## 2. The gate-level X — root cause, fix, results

Not one bug but one *pattern*, hit twice (details and traces in `notes/v2c_05_gate_level_x_and_mutant_19.md`):

- **Cause.** Synthesis expressed the synchronous reset of a register as logic that reconverges on the flop's own
  output (D = Q & ~Q: 0 on silicon for Q = 0 or 1, but X & ~X = X in gate-level simulation). The flop keeps its
  power-on X through reset. Found by a per-clock monitor over all named nets of the netlist (first X at cycle 1
  after reset) and a fan-in trace of the flop's D logic.
  1. **`a_ptr[0]`** (A's own LOAD_A activation index) in netlist 41888474394: X activation address → X
     accumulators after CMP (A's GL suite 7/14).
  2. After fixing (1), **`qspi_fetch.ptr[2]`** (C's new byte pointer) in netlist 41902595956: IO0 X while
     carrying address bit 2 → A's testbench skipped an SCK edge → flash data one byte late (3 flash tests).
- **Fix.** Both registers have their own block with an **asynchronous reset from the synchronised `rst`**
  (reset flops: the reset is dominant by construction), same clears/loads/steps as before. No `initial` values.
- **Owner's checks.** (a) The shrink removed no resets (every new register is reset; only the free-running
  input samplers are not, as in A). (b) Floating IO1–IO3: new `test_float.py` drives `uio_in` high-Z and runs
  the v1 flow and BIST: exact results, no X on any output, at RTL and gate level.
- **Method so it does not recur silently.** A local loop (LibreLane 3.0.14 in WSL Docker, same config,
  synthesis → powered netlist in ~1 min) plus the post-reset X scan and the full GL suites before each CI run.
- **Results on the CI netlist of 09b1546 (run 41909979592):** A's GL suite 13/13 (CI `gl_test` green) + slow
  internal-saturation test 1/1; `test_c` GL 10/10; `test_float` GL 1/1. RTL: test_c 10/10, A `test.py` 14/14,
  `test_devkit.py` 2/2, `test_devkit_c.py` (devkit R1–R3 stages, new) 1/1.

## 3. Mutant #19 — outcome

**Provably equivalent for every host within the chip's SPI limit (f_SCK ≤ f_clk/16)**, with the proof in
notes/v2c_05 §2. My first directed test claimed a kill but was invalid (FSTART clears a pending compute in A,
so the test failed on the real RTL too); I replaced it. In short: the mutant differs only if, in the arbiter's
acquire state, the flash is held open and a pending LOAD_FC compute's `next` lands in the same cycle; that
needs a new pending compute *and* the RAM request to arrive during one flash fetch, which takes ≥ 768 clk of
SPI bytes, while the longest fetch at an allowed divider is ≤ 392 clk (≤ 784 at clk/16, where an extra FCFG is
needed first). The new test `test_c_arbiter_waits_for_flash_cs_high` drives the closest legal schedule
(coverage-checked) and an RTL monitor asserts the invariant on every clock. The `!f_open` guard stays in the
RTL so safety does not depend on the host's SPI rate.

## 4. Latest hardening vs A

| | C 09b1546 (run 41909979592) | A `signoff-a` |
|---|---|---|
| utilisation (2x2) | 78.9 % | 63.8 % |
| slew violations | **0** at all corners | 5 pins, +50.5 ps max_ss (accepted) |
| setup WS (worst, max_ss) | +5.23 ns | +4.88 ns |
| hold WS (worst, max_ff) | +0.092 ns | +0.103 ns |
| clock latency skew (max_ss) | 0.42 ns | 0.20 ns |
| max-cap violations | **1: clock root `clkbuf_0_clk` 0.211 / 0.200 pF** at max_ss, max_ff | 0 |
| max-fanout (own limit 8) | clock root 16; data buffer `fanout151` 11 | clock root 16; one buffer 9 (accepted) |
| DRC / LVS / antenna / precheck / gl_test | 0 / 0 / 0 / pass / pass | same |

Setup and hold met at all nine corners (this run, ns, hold / setup): nom_tt 0.293/11.95, nom_ss 0.816/5.30,
nom_ff 0.093/13.41, min_tt 0.289/12.03, min_ss 0.815/5.36, min_ff 0.095/13.47, max_tt 0.296/11.88,
max_ss 0.819/5.23, max_ff 0.092/13.35. Runs since the last handoff, one setting each: b32e844 (a_ptr reset) →
ee36234 (ptr reset; **crashed** in post-GPL repair at 14 GiB) → 09b1546 (post-GPL repair margin 40 → 20: the
crash is the same grinding as B's lrc1; 14 s locally at 20) → debe305 (`CTS_DISTANCE_BETWEEN_BUFFERS` 70, in
CI as 41912700855: aimed at the clock root).

## 5. Decisions waiting for you

1. **Clock-root cap/fanout residual** — only if the CTS run (41912700855) does not clear it. Gate 3 says "no
   clock-net violations", so I will not accept it myself. Options: (a) more CTS runs (one setting each:
   buffer distance, `CTS_SINK_CLUSTERING_SIZE`, a clock-root buffer constraint); (b) accept it as a documented
   residual like A's fanout-16 root (A had no cap violation there, so this would be a new residual); (c) stop
   C. Recommendation: (a), up to two more runs before 22 Nov.
2. **`fanout151` drives 11 (own limit 8)** — a data buffer, not a clock net; A accepted a 9 under the same
   rule. Options: accept as a residual like A's, or chase it with a fanout setting after the clock root is
   fixed. Recommendation: decide after the clock-root run, since CTS changes move it.
3. **Hold margin**: +0.092 ns vs A's +0.103 ns (all corners met). Not a violation; flagging because it is
   below A's number. Recommendation: accept unless a later run gets worse.
4. **Submitting C instead of A** (your call after sign-off): two TT points are [UNKNOWN] in their docs —
   which build "Submit a new revision" takes, and whether the top-module name may change
   (`tt_um_msohair_tmac2` → `tt_um_msohair_tmac2c`). Ask TT before 22 Nov (notes/v2c_04).

## 6. What went wrong / what I am unsure of

- I called mutant #19 "probably equivalent", then "killed" it with an invalid test before finding the
  error; the proof replaced both. Also wrong earlier: my first theory for the second GL failure (a bit
  counter skipping 4→2) was a sampling artifact of my monitor; the X on IO0 was the real cause.
- The reconvergent-reset pattern is a property of synthesis, not of one register: any re-synthesis could put
  it on another flop. The local post-reset X scan and the CI `gl_test` would catch it; they are now part of
  every run.
- Utilisation 78.9 % is well above A's 63.8 %; it routes cleanly now, but each CTS/repair change moves it.
- Final mutation batch on the final RTL: control and mutants 1–8 graded; 9–27 running when this was written
  (`../v2c_mutation_final_9on.log`); the earlier full batch on 000cb05 was 26/27 with only #19 surviving.
