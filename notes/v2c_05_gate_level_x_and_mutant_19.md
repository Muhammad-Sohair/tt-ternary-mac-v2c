# v2c Step 5 — the gate-level X, and mutant #19

## 1. Gate-level X in A's suite on C's netlist (run 41888474394)

**Symptom.** CI `gl_test` (A's `test.py` on C's netlist): 7/14 failed with X on MISO when reading the
accumulators after any CMP; the tests that never compute (reset state, decoder, BIST, SPI abort, flash pins,
timing windows) passed.

**Finding the origin.** Reproduced locally (`../v2c_gl`, the CI netlist, sky130 cell models). A cocotb monitor
(`test_xtrace.py`) checked all 5,554 named nets of the netlist on every clock after reset and reported the
first cycle with any X: **cycle 1 after reset, 4 nets: `a_ptr[0]` and three nets it drives**. `a_ptr` is A's
own 3-bit LOAD_A activation index. With it X, LOAD_A writes an activation at an X address, and every CMP
accumulates X.

**Fan-in of `a_ptr[0]` during reset** (`netcone.py`, values read in simulation with rst asserted):

```
a_ptr[0]  <- dfxtp_2  D = _0090_                         = X
_0090_    <- o211a_2  (A1 = a_ptr[0] | A2 = 0) & B1 = 1 & C1 = _2124_
_2124_    <- o21ai_2  ~((A1 = net228 = 1 | A2 = 0) & B1 = a_ptr[0])  = ~a_ptr[0]
```

So D = a_ptr[0] & ~a_ptr[0]. This is 0 for Q = 0 and for Q = 1 (the reset is logically correct, and silicon
resets after one clock), but synthesis expressed it through two reconvergent paths from the flop's own Q, and
gate-level simulation evaluates X & ~X = X: the power-on X can never be cleared. RTL is identical to A's
(`a_ptr` cleared by `rst || !spi_active` and at every opcode); A's netlist happened to synthesise it without
reconvergence. Nothing else in C's netlist went X.

**The owner's specific checks.**
- (a) Did the shrink remove resets from buffer, arbiter or `qspi_fetch` registers? **No.** Every register in the
  new logic is reset (`m_ptr`, `ar_n`, `x_*`, the RAM sequencer's state/counters, `qspi_fetch.ptr`); the only
  unreset flops are the free-running input samplers (`in_q`), as in A. The cycle-1 scan confirms it: no new
  register was X.
- (b) Can floating IO1–IO3 reach the datapath? Read data reach the array only through `x_a_we` (RAM burst
  state) and `f_we` (flash data phase); otherwise the core's write ports select SPI data. A gate-level test with
  `uio_in` undriven (Z) is in the gate-level runs below.

**Fix (b32e844).** `a_ptr` moved to its own always block with an **asynchronous reset from the synchronised
`rst`** (a reset flop: Q is forced to 0 by the reset pin, independent of the D logic), with the same
synchronous clears (SPI idle, every opcode) and step (each LOAD_A/AC/FC data byte). No `initial` values. RTL
behaviour is unchanged: test_c 9/9, A's `test.py` 14/14, `test_devkit.py` 2/2.

Why not keep it synchronous and hope: whether a synchronous reset survives as a dominant term depends on
ABC's restructuring, which changed between A and C for unrelated reasons; a reset flop does not.

## 2. Mutant #19: "RAM used without pausing the flash"

Mutant: `X_ACQ: if (!f_busy && !f_open)` → `if (!f_busy)` (the arbiter stops waiting for the flash /CS to go
high before starting the RAM command).

**First attempt was wrong.** A directed test that left a LOAD_FC compute pending before FSTART "killed" the
mutant, but it also failed on the real RTL: FSTART clears a pending compute (A's behaviour), so the test was
invalid. Replaced.

**Proof that #19 cannot be observed by any host within the chip's SPI limit (f_SCK ≤ f_clk/16).**

1. The mutant differs from the RTL only in a cycle where `x_state = X_ACQ`, `f_busy = 0`, `f_open = 1`, and the
   flash stays open in the next cycle. `!f_busy && f_open` is exactly `qspi_fetch` state `S_HOLD`. In `S_HOLD`,
   `x_pause` (asserted in exactly this condition) moves the flash to `S_PAUSE` (/CS high) at the same edge the
   mutant moves to `X_GO`, unless `next` is asserted in that cycle (`next` has priority). The RAM's /CE then
   falls no earlier than one SCK phase after `X_GO` (psram_ctl `S_GAP`). So the mutant is observable **only if
   `next` is asserted while X_ACQ sees `S_HOLD`**.
2. `next = fc_fire | x_next`. `x_next` is asserted only in `X_NEXT`/`X_FIRE`, never in `X_ACQ`. So `fc_fire`
   (= `fc_pend & f_ready & !bist_busy`) must be 1, i.e. a LOAD_FC compute is pending.
3. `fc_pend` is set by the 5th activation byte of LOAD_FC and is cleared by FSTART and consumed by `fc_fire`. In
   `S_HOLD` a pending compute fires in the very cycle the flash enters `S_HOLD`. For the coincidence, the flash
   must enter `S_HOLD` with `fc_pend = 1` **and** `X_ACQ` already active, so both must happen while one fetch
   is in flight.
4. That fetch was started by FSTART (which clears `fc_pend`), by a `fc_fire` (which consumes it) or by the RAM
   path (`x_next`, during ARUN, when LOAD_FC is blocked). A new `fc_pend` therefore needs 5 more activation
   bytes after the fetch started, and the RAM request (`s_ainit` / `s_awr`) needs at least one more SPI byte
   after the LOAD_FC command (LOAD_FC cannot start while `X_ACQ` is active: it is blocked). At f_SCK ≤ f_clk/16 a
   byte takes ≥ 128 clk: the RAM request arrives **≥ 6 × 128 = 768 clk** after the fetch started.
5. The longest fetch is a start/resume: 1 phase + 32 command + 8 dummy + 8 data SCK. RAM requests are refused at
   clk/16 (`x_div_bad`), so a RAM request is accepted only at clk/8 or faster: ≤ 49 × 8 = 392 clk. If the fetch
   ran at clk/16 (≤ 784 clk), an FCFG (2 more SPI bytes, ≥ 256 clk) is needed before the request can be
   accepted: request ≥ 1,024 clk after the start, and changing the divider mid-fetch only shortens the fetch.
6. Hence the fetch always ends before the RAM request is accepted; when it ends, a pending compute fires
   immediately (`next`, an 8-SCK fetch at most 64 clk at clk/8 or 128 at clk/16, far shorter than the next SPI
   byte), and `fc_pend` is 0 again. Step 1's condition never occurs: **#19 is equivalent for every host that
   meets the chip's documented SPI limit.** (A host clocking SPI faster than f_clk/16 is outside the spec: the
   SPI slave itself is not specified there.)

**Evidence besides the argument.** `test_c_arbiter_waits_for_flash_cs_high` drives the closest legal schedule
(AINIT arriving during a ~390-clk flash re-open at clk/8, coverage-checked: the arbiter does wait on a busy
flash) and runs an RTL monitor on every clock asserting the invariant "never X_ACQ with the flash held and
`next` asserted". It passes on the RTL; mutant #19 survives the full C suite (expected by the proof).

The `!f_open` term stays in the RTL: it costs one gate and keeps the arbiter safe without relying on the host's
SPI rate.
