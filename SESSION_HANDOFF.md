# Session handoff — 2026-11-05 (v2c, TMAC2C) — overnight run

A (`tt-ternary-mac-v2`, `signoff-a`) and B (`tt-ternary-mac-v2b`) were not touched. Nothing submitted, paid,
posted, or changed in GitHub settings. All work is on `Muhammad-Sohair/tt-ternary-mac-v2c` `main`.

## 1. Gate status

| gate | date | status |
|---|---|---|
| 1 datasheets | 8 Nov | **passed 4 Nov** |
| 2 RTL + tests passing | 15 Nov | **met 5 Nov**: RTL, gate level and mutation all pass (§2, §3) |
| 3 full A-standard sign-off | 22 Nov | **on track; every check is met on run 41912700855** (§4). Not tagged: tagging `signoff-c` and choosing C over A are yours (§5) |

## 2. The gate-level X — root cause, fix, results

Not one bug but one *pattern*, hit twice (traces in `notes/v2c_05_gate_level_x_and_mutant_19.md`):

- **Cause.** Synthesis expressed a register's synchronous reset as logic that reconverges on the flop's own
  output (D = Q & ~Q: 0 on silicon for Q = 0 or 1, but X & ~X = X in gate-level simulation), so the flop keeps
  its power-on X through reset. Found with a per-clock monitor over all named nets of the netlist (first X at
  cycle 1 after reset) and a fan-in trace of the flop's D logic.
  1. **`a_ptr[0]`** (A's own LOAD_A activation index), netlist 41888474394: X activation address → X
     accumulators after every CMP (A's GL suite 7/14).
  2. After fixing (1), **`qspi_fetch.ptr[2]`** (C's new byte pointer), netlist 41902595956: IO0 X while carrying
     address bit 2 → A's testbench skipped an SCK edge → flash data one byte late (3 flash tests).
- **Fix.** Both registers have their own block with an **asynchronous reset from the synchronised `rst`**
  (reset flops: the reset dominates by construction), same clears/loads/steps as before. No `initial` values.
- **Your checks.** (a) The shrink removed no resets: every new register is reset; only the free-running input
  samplers are not, as in A. (b) Floating IO1–IO3: `test_float.py` drives `uio_in` high-Z and runs the v1 flow
  and BIST: exact results, no X on any output, at RTL and gate level.
- **Guard against recurrence.** Local loop: LibreLane 3.0.14 (WSL Docker, CI config) synthesis → powered
  netlist in ~1 min, then the post-reset X scan and the GL suites before each CI run.

**Results, final RTL (ee36234) and final netlist (debe305, run 41912700855):**

| suite | RTL | gate level |
|---|---|---|
| A `test.py` | 14/14 | 13/13 in CI `gl_test` + slow internal-saturation 1/1 (local) |
| A `test_devkit.py` | 2/2 | — (RTL only, as in A) |
| C `test_c.py` (incl. new arbiter test) | 10/10 | 10/10 |
| C `test_float.py` | 1/1 | 1/1 |
| C `test_devkit_c.py` (devkit R1–R3, new) | 1/1 (R3: 6/6 bit-exact) | — (RTL only) |

## 3. Mutant #19 — outcome

**Provably equivalent for every host within the chip's SPI limit (f_SCK ≤ f_clk/16)**; proof in notes/v2c_05 §2.
My first directed test claimed a kill but was invalid (FSTART clears a pending compute, so it failed on the real
RTL too); replaced. The mutant differs only if, in the arbiter's acquire state, the flash is held open and a
pending LOAD_FC compute's `next` lands in the same cycle; that needs a new pending compute and the RAM request
to arrive inside one flash fetch: ≥ 768 clk of SPI bytes vs a fetch of ≤ 392 clk at the allowed dividers
(≤ 784 at clk/16, where an extra FCFG is needed first). `test_c_arbiter_waits_for_flash_cs_high` drives the
closest legal schedule (coverage-checked) with an RTL invariant monitor on every clock. The guard stays in the
RTL so safety does not depend on the host.

**Final mutation batch on the final RTL** (`notes/v2c_mutation_final_ee36234.log`): no-mutation control
survived; **26/27 caught** (all 10 of A's flash mutants, 16/17 new ones); #19 the only survivor (above).

## 4. Latest hardening vs A — run 41912700855 (debe305)

| | C | A `signoff-a` |
|---|---|---|
| utilisation (2x2) | 79.3 % | 63.8 % |
| slew violations | **0** at all corners | 5 pins, +50.5 ps max_ss (accepted residual) |
| max-cap / max-fanout violations | **0 / 0** (clock root fanout 2, 0.017 pF) | 0 / clock root 16, one buffer 9 (accepted) |
| setup WS (worst, max_ss) | +5.23 ns | +4.88 ns |
| hold WS (worst, min_ff) | +0.100 ns | +0.103 ns |
| clock latency skew (max_ss) | 0.43 ns | 0.20 ns |
| clock insertion delay max (max_ss) | 1.72 ns | 1.38 ns |
| DRC / LVS / antenna / precheck / gl_test | 0 / 0 / 0 / pass / pass | same |

Every corner, no `VIOLATED` line in any of the nine `checks.rpt`. Hold / setup WS (ns): nom_tt 0.298/11.82,
nom_ss 0.816/5.29, nom_ff 0.103/13.33, min_tt 0.295/11.89, min_ss 0.815/5.36, min_ff 0.100/13.39,
max_tt 0.300/11.76, max_ss 0.819/5.23, max_ff 0.103/13.28.

Runs since the last handoff, one setting each: b32e844 (`a_ptr` reset) → ee36234 (`ptr` reset; **crashed** in
post-GPL repair at 14 GiB) → 09b1546 (`DESIGN_REPAIR_MAX_SLEW_PCT` 40 → 20: same grinding as B's lrc1; 14 s
locally at 20; clean except the clock root) → **debe305 (`CTS_DISTANCE_BETWEEN_BUFFERS` 70): all clean.**

## 5. Decisions waiting for you

1. **Is this C's sign-off?** By the numbers it meets the full A standard and is stricter than A (no residuals).
   Not tagged, because it is your call. Recommendation: review §4 and notes/v2c_05, then tag `signoff-c` on
   `main` (debe305 is the hardening commit; later commits are docs only).
2. **Skew 0.43 ns vs A's 0.20 ns** (latency skew, max_ss). Not a violation and hold is met everywhere (≥ +0.100
   ns), but it is about twice A's; flagging it. Recommendation: accept; it comes from the deeper clock tree
   that removes the root fanout/cap violation.
3. **Submitting C instead of A** (separate from sign-off and from paying): two TT points are [UNKNOWN] in their
   docs (notes/v2c_04): which build "Submit a new revision" takes, and whether the top-module name may change
   (`tt_um_msohair_tmac2` → `tt_um_msohair_tmac2c`). Recommendation: ask TT before 22 Nov.

## 6. What went wrong / what I am unsure of

- I called mutant #19 "probably equivalent", then "killed" it with an invalid test before finding the error; the
  proof replaced both. Also wrong: my first theory for the second GL failure (a counter skipping 4→2) was a
  sampling artifact of my own monitor; the X on IO0 was the cause.
- The reconvergent-reset pattern is a property of synthesis, not of one register: any re-synthesis can put it on
  another flop. The local post-reset X scan and CI `gl_test` catch it; run them after every RTL change.
- The post-GPL repair blow-up (14 GiB) shows calibrated `LAYERS_RC` makes `repair_design` sensitive to large
  slew margins; both margins are now 20 %. A future change that raises them could hang or crash again.
- Utilisation 79.3 % routes cleanly now but leaves little room for RTL growth in 2x2.
- The mutation batch is RTL-level; gate level is covered by the suites above, not by mutation.

## Where things are

- Repo: `E:\extras\portfolio\ternary-silicon\v2c` (public `tt-ternary-mac-v2c`). Gate-level workspace:
  `..\v2c_gl` (local copy, probes `test_xtrace.py`, `netcone.py`, `depth.py`). Local flow:
  `scratchpad\c_local\quick.sh` (WSL), runs in `~/v2c_local` inside WSL.
- Notes: v2c_00 plan/gates, v2c_01 datasheets, v2c_02 spec, v2c_03 RTL/verification, v2c_04 switching a TT
  submission, v2c_05 gate-level X and mutant #19, mutation logs.
