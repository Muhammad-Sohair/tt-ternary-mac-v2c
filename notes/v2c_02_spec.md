# v2c Step 2 — option C specification (DRAFT, 4 Nov 2026)

Status: draft for gate 1 (8 Nov). Every value that depends on the RAM datasheets is marked
**[PENDING DATASHEET]** and is resolved from notes/v2c_01_datasheets.md (Track 1). Everything marked
**[DECISION]** is the owner's call. No RAM-controller RTL is written before gate 1.

## 1. Goal and scope

A's 4 × 5 array and A's flash weight streamer, plus an activation store in the QSPI Pmod's RAM: the host
writes an activation vector x (K int8 values) once; the chip then re-reads it for every row group of the
weight matrix instead of the host re-sending it over SPI. Nothing else changes from A (v1 commands, flash
stream, readout, BIST, pins other than the Pmod data lines' output enables).

## 2. Data flow

```
host --SPI (≤ 3.1 MHz)--> AWRITE base, x[0..K-1] --> chip --QSPI--> RAM A   (once per vector)
host --SPI--> FSTART page  (A, unchanged)            chip --QSPI--> flash    (weights, A's 6Bh stream)
per row group g:
  host --SPI--> CLEAR, ARUN base, nchunks
     chip: for each chunk c:  RAM A  -> 5 activation bytes (x[5c..5c+4])
                              flash  -> 4 weight bytes (rows 4g..4g+3, columns 5c..5c+4)
                              array  -> acc += W_chunk · x_chunk  (A's compute, 2 clocks)
  host --SPI--> READ_ACC / READ_RAW (8 or 12 bytes)
```

Flash layout: A's `pack_stream`, unchanged. RAM layout: `pack_acts(x)` = K bytes padded with zeros to a
multiple of 5, contiguous from `base`. Golden model: `test/tmac_model.py` `TMAC2C`, `matvec_c` (provisional
opcodes `AWRITE` 0xA0, `ARUN` 0xA1); self-checked against plain integer arithmetic.

Only RAM A is needed for one vector (8 MB [PENDING DATASHEET: part size]). RAM B stays deselected (its /CS
held high, as in A) unless a later decision uses it.

## 3. Bus: flash and RAM share the Pmod

| uio | Pmod signal (A's RTL comment) | flash | RAM A | RAM B |
|---|---|---|---|---|
| 0 | flash /CS | /CS | — | — |
| 1 | IO0 | DI/IO0 | SI/SIO0 | SI/SIO0 |
| 2 | IO1 | DO/IO1 | SO/SIO1 | SO/SIO1 |
| 3 | SCK | CLK | SCLK | SCLK |
| 4 | IO2 | IO2 | SIO2 | SIO2 |
| 5 | IO3 | IO3 | SIO3 | SIO3 |
| 6 | RAM A /CS | — | /CE | — |
| 7 | RAM B /CS | — | — | /CE |

[PENDING DATASHEET: confirm against the Pmod schematic, and that SCK and IO0..IO3 are shared.] If shared,
**flash and RAM accesses must be serialised: one /CS low at a time.** The testbench enforces this
(`psram_model.check_exclusive_select`).

A drives `uio_oe` = 0b11001001 statically: /CS ×3 and SCK out, IO0 out only during the flash command,
IO1..IO3 always inputs. C must drive IO0..IO3 during RAM writes (quad) and possibly during RAM command and
address phases (QPI): **`uio_oe[5:4,2:1]` becomes dynamic.** Bus turnaround (chip releases IO before the RAM
drives) must respect the RAM's output-enable timing [PENDING DATASHEET].

### Arbitration and the flash re-open problem

A's `qspi_fetch` opens the flash stream only at a 256-byte boundary (`page` = address[23:8]) and streams
forward. To read activations from RAM between weight chunks, the flash /CS must go high (shared bus), and
the stream must later resume at the **next byte**, not at a page start. **A's flash controller cannot do this
unchanged.**

| option | change to A's flash controller | on-chip buffer | cost |
|---|---|---|---|
| **R1** pause/resume: `qspi_fetch` keeps its 24-bit byte pointer; a pause closes /CS, a resume re-issues 6Bh at the pointer | small (address register 16 → 24 bits, resume path) | 5 bytes (A's activation register) or m chunks | modifies a signed-off block; full re-verification (C does that anyway) |
| R2 page-aligned segments: read activations only at flash page boundaries | none | 64 chunks = 320 bytes (256 weight bytes per page / 4) | ~2,600 flip-flops: does not fit next to A's array in 2x2, likely not in 3x2 [ESTIMATE] |
| R3 weights also through RAM | larger (flash copy step) | — | changes A's data flow; out of scope |

**[DECISION]** R1 is the only practical one; it contradicts "A's signed-off flash controller, nothing else
changes" in the narrow sense. Recommended: allow R1, keep the change minimal and re-run A's full flash test
set plus new resume tests.

### Burst size m (activation chunks fetched per RAM visit)

With R1, each RAM visit costs one RAM read command and one flash re-open:

- flash re-open (A's 6Bh: 8 instruction + 24 address clocks on IO0, 8 dummy): **40 SCK** [verified for A,
  notes/v2_02]
- RAM read command overhead: SPI-mode EBh 8 + 6 (address) + W wait clocks, or QPI 2 + 6 + W
  [PENDING DATASHEET: W, and whether QPI is used]; written below as O_r
- data: 4 weight bytes = 8 SCK and 5 activation bytes = 10 SCK per chunk (both quad)

SCK per chunk = 18 + (40 + O_r) / m. Buffer = 5m bytes (40m flip-flops beyond A's single chunk, m ≥ 2).

| m | buffer | SCK / chunk (O_r = 14 [PENDING]) | µs / chunk at SCK 25 MHz | at 12.5 MHz |
|---|---|---|---|---|
| 1 | A's 5-byte register | 72 | 2.88 | 5.76 |
| 2 | 10 bytes | 45 | 1.80 | 3.60 |
| 4 | 20 bytes | 31.5 | 1.26 | 2.52 |
| 8 | 40 bytes | 24.8 | 0.99 | 1.98 |

The RAM's maximum /CS-low time bounds one RAM burst: 5m bytes take 10m SCK (+ overhead), e.g. m = 8 at
12.5 MHz ≈ 6.4 µs + overhead [PENDING DATASHEET: tCEM; if it is ~8 µs at the relevant temperature, m = 8 at
12.5 MHz is marginal and m ≤ 4 is safe]. The flash has no such limit (A streams whole matrices).

SCK: A defaults to clk/4 = 12.5 MHz and allows clk/2 = 25 MHz after calibration (F4 window). The RAM's
maximum clock for each command [PENDING DATASHEET] and the TT pad round trip (~20 ns, tinytapeout.com/specs)
set what the RAM path can use; the RAM sample point uses A's programmable `samp` mechanism.

## 4. Speed per token (TriLM-99M ternary projections)

~48 M ternary MACs per token [CALCULATED in v2_01] → 2.4 M array chunks (20 MACs each).

| design | bound by | per token |
|---|---|---|
| A | host SPI (activations re-sent per row group) | ~30 s [v2_01] |
| B (stopped) | host SPI, half the groups | ~15 s [v2_01] |
| **C, m = 1** | shared QSPI bus | 6.9 s at 25 MHz, 13.8 s at 12.5 MHz [ESTIMATE, PENDING O_r] |
| **C, m = 4** | shared QSPI bus | 3.0 s at 25 MHz, 6.0 s at 12.5 MHz [ESTIMATE, PENDING O_r] |
| C, m = 8 | shared QSPI bus | 2.4 s at 25 MHz, 4.8 s at 12.5 MHz [ESTIMATE, PENDING tCEM] |

Host traffic per token drops to the vectors once per layer plus 8–12 result bytes per row group (~0.1 MB
[v2_01]). These exclude the FP16 embedding/head on the PC and Python overhead on the RP2040, which v2_01
already flagged as likely to dominate.

## 5. Tiles [ESTIMATE]

A: 63.8 % utilisation in 2x2 with the tech-LEF RC; with lrc2's calibrated `LAYERS_RC`, B gained
+1.5 points of buffers (B notes v2b_02). C adds: a RAM command/address sequencer (similar to `qspi_fetch`,
which is a small fraction of A), the R1 resume path (+8 address bits), dynamic IO enables, and the m-chunk
buffer (40m flip-flops + read muxes for m ≥ 2).

| m | estimate | tiles |
|---|---|---|
| 1–2 | A + ~6–10 points | 2x2 possible but tight (≥ 70 %, where B's slew trouble started) |
| 4–8 | A + ~12–20 points | 3x2 |

The 1.55× LibreLane-vs-YoWASP area factor (v1 notes) applies; a synthesis-only area check comes before the
first hardening run. **[DECISION]** tiles: 2x2 with m ≤ 2, or 3x2 with m = 4.

## 6. Hardening plan

Start from A's config plus lrc2's calibrated `LAYERS_RC` and `GRT_DESIGN_REPAIR_MAX_SLEW_PCT` 20 (55 hangs
repair once the RC is calibrated, B notes v2b_02). The `LAYERS_RC` values were fitted on B's 3x2 layout; C's
first run is the place to re-fit them on C's own extraction (one setting per run).

## 7. Open items

| item | owner |
|---|---|
| RAM part number, size, tCEM, tCPH, wait cycles, max SCK per command, page size and burst/wrap rules, power-up/reset sequence, QPI entry, output-enable and turnaround timing | Track 1 → v2c_01 [PENDING DATASHEET] |
| Pmod pin map and shared-bus confirmation | Track 1 [PENDING DATASHEET] |
| R1 (modify A's flash controller to resume at a byte address) | **[DECISION]** owner |
| m and tiles | **[DECISION]** owner, after gate 1 numbers |
| opcodes AWRITE/ARUN argument layout | spec, after gate 1 |
