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
| 1 | 8 Nov 2026 | datasheet check done; every [PENDING DATASHEET] item in v2c_02 resolved; if the datasheets break the architecture, C stops | — |
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
