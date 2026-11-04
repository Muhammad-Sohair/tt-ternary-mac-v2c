# v2c Step 3 — RTL and verification (gate 2, due 15 Nov)

Owner's decisions (4 Nov): **R1 allowed** (C's copy of `qspi_fetch` only), **m = 2 on 2x2**, and a new hard
requirement: **C is a strict superset of A** and must be safe to submit *instead of* A in the same slot.

## What changed from A

| file | change |
|---|---|
| `src/qspi_fetch.v` | 24-bit byte pointer (loaded with `{page, 8'h00}` on start, +1 per delivered byte) replaces the fixed `{page, 8'h00}` address; new `pause` input and `S_PAUSE` state: with a chunk held, /CS goes high and the chunk stays (ready = 1); a `next` while paused re-issues 6Bh at the pointer. With `pause` low the module is A's. |
| `src/psram_ctl.v` (new) | APS6404L sequencer, SPI-mode commands: 66h + 99h reset, 38h write (quad address and data), EBh read (quad address, 6 wait clocks, quad data, up to 15 bytes). SCK runs without a pause from the first rise to the last fall of every command. Same divider and sample-point mechanism as the flash. |
| `src/tt_um_msohair_tmac2c.v` | opcodes AWRITE 0xA0, ARUN 0xA1, AINIT 0xA2, ASTAT 0xA3; one arbiter for the shared Pmod bus (waits for a flash fetch to finish, pauses the flash, runs the RAM command); ARUN with 10-byte RAM visits (m = 2); while a RAM operation runs, core/flash/RAM-changing opcodes are refused (BLOCKED); FSTOP/BIST end ARUN after the RAM command in flight; IO1..IO3 output enables now switchable. |

**Superset by construction:** the new logic only acts on opcodes 0xA0–0xA3 (TMAC2 ignored them and returned
STATUS). Until one is used: RAM A /CE stays high, RAM SCK and IO enables stay low, `uio_out`/`uio_oe` are
bit-for-bit TMAC2's, `qspi_fetch` never sees `pause`, and the decoder never blocks. If the RAM path fails on
silicon, the chip is still a full TMAC2 (tested, below). ASTAT reads 0x00 on C after reset and STATUS (bit 7 =
1) on A, so the host can tell them apart.

## Verification (RTL, 4 Nov)

| suite | result |
|---|---|
| **A's RTL suite** `test.py`, unchanged, on C | **14/14** |
| **A's devkit harness** `test_devkit.py`, unchanged, on C | **2/2** |
| **C's RAM suite** `test_c.py` | **9/9** |
| RAM model self-tests `psram_model.py` (pytest) | 10/10 |
| golden model `TMAC2C` self-check | pass |
| Verilator `-Wall` lint | no warnings in new code (A's 22 existing ones unchanged) |

`test_c.py` runs on a shared-bus model (`PmodBus`): A's W25Q128JV protocol checks, the APS6404L-3SQR-SN
engine with the datasheet timing set (`psram_model.APS6404L_3SQR_SN`, Rev 2.7 citations in the file), and the
schematic's bus rules. **Every rule is an assertion that fails the test at the offending edge** (strict mode):

| checked property | where |
|---|---|
| /CE low ≤ tCEM (8 µs) | RAM engine, every edge |
| /CE high ≥ tCPH (18 ns) | RAM engine |
| a linear burst crosses at most one 1 KB page boundary | RAM engine |
| SCK never paused inside a burst (no edge gap > 200 ns while /CE low) | RAM engine |
| no read/write before the power-up reset 66h → 99h; 99h only after 66h | RAM engine |
| mode 0, no partial command, supported opcodes only | RAM engine |
| at most one of flash /CS, RAM A /CE low; RAM B never selected | `PmodBus` |
| the chip never drives an IO line the RAM drives (no bus fight); IO1..3 not driven while the flash is selected | `PmodBus` |

Tests: reset state and feature detect; AINIT sends exactly 66h, 99h and nothing reaches the RAM before it;
AWRITE storage incl. a RAM page crossing and the top of the 8 MB; ARUN matvec bit-exact at SCK /2, /4, /8;
**resume at arbitrary bytes** (a 328-byte stream crossing flash pages with pause/resume, a nonzero start page,
LOAD_FC → AWRITE → LOAD_FC → ARUN (odd count) → LOAD_FC on one stream, asserting non-page-aligned 6Bh
re-opens); errors and blocking (DIV, STREAM, BLOCKED, ABORT, AINIT clears); AWRITE overrun at /8; the
longest burst at the slowest clock (measured /CE low 6.36 µs < 8 µs); and a dead RAM: ARUN terminates, then
A's LOAD_FC flow is bit-exact.

Bugs found by the tests before any commit: (1) my second-chunk activation index was 8+2+k instead of 5+k
(read past the 10-byte buffer: X at two-chunk visits); (2) an abort cut a RAM command mid-instruction:
changed so FSTOP/BIST end ARUN between RAM commands; (3) a test helper sent AWRITE bytes faster than a /8
RAM write: the chip correctly dropped them (OVERRUN), the helper now paces bytes at /8 as the docs say.

## Clock range for the RAM path

The longest RAM command is the 10-byte read: 8 + 6 + 6 + 20 = 40 SCK. Within tCEM = 8 µs that needs
SCK ≥ 5 MHz: at the 50 MHz project clock the FCFG dividers /2, /4, /8 (25, 12.5, 6.25 MHz) work and /16 is
refused (ASTAT DIV). Below about 10 MHz project clock no divider works, so the devkit's RAM stages run at
50 MHz. Documented in docs/info.md and the devkit script.

## Open for gate 2

- Mutation batch with control including the new logic (`test/mutate_c.py`): running.
- Gate-level: A's GL suite plus `test_c` on C's netlist (needs C's GDS run).
- Devkit R1–R3 stages: written; a harness run against the RTL (like A's test_devkit) is still to do.
