# v2c Step 0 — option C: plan, gates and the owner's rules (4 Nov 2026)

Seeded from A (`tt-ternary-mac-v2`, tag `signoff-a`, d180bca), **not** from B. Top module renamed
`tt_um_msohair_tmac2` → `tt_um_msohair_tmac2c` (source, info.yaml, tb.v, Makefile, model, devkit). A's tags
were not copied. A's repo, tag and CI are never modified.

## Scope

A's 4-row array and A's signed-off flash controller, **plus** activations kept in the Pmod's RAM chips so the
PC does not re-send them over SPI. Nothing else changes from A.

## Gates

| gate | date | condition | status |
|---|---|---|---|
| 1 | 8 Nov 2026 | datasheet check done; every [PENDING DATASHEET] item in v2c_02 resolved; if the datasheets break the architecture, C stops | **datasheets done 4 Nov, architecture not broken; waiting on owner decisions R1 and m/tiles (v2c_02 §7)** |
| 2 | 15 Nov 2026 | RTL + tests passing: golden model, bit-exact checks, RAM model with real datasheet timing, mutation tests with a no-mutation control | — |
| 3 | 22 Nov 2026 | full A standard: 9-corner timing, DRC/LVS/antenna, gate-level sim, mutation tests, slew residuals no worse than A's, no clock-net violations; else C stops for this shuttle (v3 input) | — |

## Rules (owner's, verbatim in substance)

- Track 1 (checks, datasheets) and Track 2 (setup) run in parallel; the RAM controller RTL is written only
  after gate 1.
- Harden from lrc2's calibrated `LAYERS_RC` (B, notes in `tt-ternary-mac-v2b`). **One setting per run.**
- Never modify A's repo, tag or CI. Never submit, pay, post publicly or create accounts.
- Never invent datasheet values, limits or tool behaviour: verify, or [UNKNOWN].
- Report status against the three gates at every handoff. Signing off C does not commit the owner to paying
  for its tiles.

## Progress log

| date | status |
|---|---|
| 4 Nov | Seed created; B archive and A integrity checks passed (A `main` 2c24307 green, src/info.yaml/docs identical to `signoff-a`, no commits since 29 Oct). |
| 4 Nov | Seed RTL 14/14 locally; seed CI queued. Track 2 setup: `test/psram_model.py` (pin-level RAM engine, every datasheet value a parameter, 6/6 self-tests with placeholder values), golden model `TMAC2C`/`matvec_c` (self-checked), hardening config = A + lrc2 `LAYERS_RC` + post-GRT margin 20, spec draft v2c_02. **Found: A's flash controller only opens at page boundaries, so interleaving RAM reads needs a byte-address resume in `qspi_fetch` ([DECISION] R1).** |
| 4 Nov | Track 1 done: parts W25Q128JVSIM + 2 × APS6404L-3SQR-SN (schematic v2.2); tCEM 8 µs, tCPH 18 ns, EBh 6 wait cycles, 1 KB pages re-checked against the APS6404L Rev 2.7 PDF text. Shared bus confirmed (serialise). All [PENDING DATASHEET] items in v2c_02 resolved; RAM model has the cited timing set (7/7 self-tests). Limits: RAM bursts ≤ 89 bytes at 25 MHz, ≤ 39 at 12.5 MHz, unusable at clk/16; chip must reset the RAM after power-up. |
| 4 Nov | RTL done (R1 pause/resume, m = 2, strict superset). First GDS 41883111400 failed placement (57.9k vs A 39.6k um2). Shrunk without behaviour change (no activation buffer, shared argument register): GDS 41888474394 **places: util 78.8 %, slew 0 at all corners, setup +4.64, hold +0.101, DRC/LVS/antenna/precheck clean**. RTL: test_c 9/9, A test.py 14/14, test_devkit 2/2. **Open: CI gate-level fails 7/14 (X in accumulators after CMP); reproduced locally in ../v2c_gl; registers are not X after reset, so the X enters during operation - not yet found.** Mutation batch (28 incl. control) running locally (../v2c_mutation.log). |
