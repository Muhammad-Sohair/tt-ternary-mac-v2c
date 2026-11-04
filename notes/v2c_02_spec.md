# v2c Step 2 — option C specification (gate 1 review, 4 Nov 2026)

Status: every datasheet-dependent item is now resolved from notes/v2c_01_datasheets.md (Track 1); the
architecture-critical values were re-checked against the PDF text (AP Memory APS6404L Rev 2.7, 5 Jan 2024).
**The datasheets do not break the architecture.** What is left are the owner's **[DECISION]** items (§7)
and the bench-only **[UNKNOWN]** items (§8). No RAM-controller RTL is written before the decisions.

## 1. Goal and scope

A's 4 × 5 array and A's flash weight streamer, plus an activation store in the QSPI Pmod's RAM: the host
writes an activation vector x (K int8 values) once; the chip re-reads it for every row group of the weight
matrix instead of the host re-sending it over SPI. Nothing else changes from A (v1 commands, flash stream
protocol, readout, BIST), except what §3 shows is unavoidable.

## 2. Data flow

```
host --SPI (≤ 3.1 MHz)--> AWRITE base, x[0..K-1] --> chip --QSPI--> RAM A   (once per vector)
host --SPI--> FSTART page  (A)                       chip --QSPI--> flash    (weights, A's 6Bh stream)
per row group g:
  host --SPI--> CLEAR, ARUN base, nchunks
     chip, per visit of m chunks:  RAM A -> 5m activation bytes into the buffer   (one RAM burst)
                                   flash -> 4 weight bytes per chunk               (resume at saved byte)
                                   array -> acc += W_chunk · x_chunk               (A's compute)
  host --SPI--> READ_ACC / READ_RAW
```

Flash layout: A's `pack_stream`. RAM layout: `pack_acts(x)` = K bytes padded with zeros to a multiple of 5,
contiguous from `base`. Golden model: `test/tmac_model.py` `TMAC2C`, `matvec_c` (provisional opcodes
`AWRITE` 0xA0, `ARUN` 0xA1), self-checked against integer arithmetic. RAM A only; RAM B stays deselected.
APS6404L is 64 Mbit = 8 MB per chip (v2c_01 §1), far more than any TriLM-99M activation vector.

## 3. Bus: flash and RAM share the Pmod (verified)

Pin map (mole99/qspi-pmod schematic v2.2 = A's RTL comment, v2c_01 §4): uio[0] flash /CS, [1] IO0,
[2] IO1, [3] SCK, [4] IO2, [5] IO3, [6] RAM A /CE, [7] RAM B /CE; 10 kΩ pull-ups on the three selects only.

- **SCK and IO0..IO3 are shared by all three chips: accesses are serialised, one select low at a time.**
  The testbench enforces this (`psram_model.check_exclusive_select`).
- A deselected RAM releases the bus within tHZ ≤ 5.5 ns (Table 10); a deselected flash is high-Z (W25Q128JV
  §4.1). A RAM's mode (SPI/QPI) does not affect the flash while its /CE is high.
- **C must drive IO1..IO3**, which A never does (`uio_oe` = 0b11001001 is constant in A): quad writes and
  quad addresses need dynamic enables on uio[1,2,4,5], released before the RAM drives (after the address
  for reads) and while the flash outputs.

### Arbitration: the flash must resume at a byte address — [DECISION] R1

A's `qspi_fetch` opens the flash only at a 256-byte boundary (`page` = address[23:8]) and streams forward.
With a shared bus the flash /CS must go high for every RAM visit and the stream must resume at the next
byte. **A's flash controller cannot do this unchanged.**

| option | change to A's flash controller | on-chip buffer | verdict |
|---|---|---|---|
| **R1** pause/resume: keep a 24-bit byte pointer; pause = /CS high; resume = 6Bh at the pointer | small (16 → 24-bit address, resume path) | 5m bytes | the only practical one |
| R2 RAM visits only at flash page boundaries | none | 320 bytes (64 chunks) | ~2,600 flip-flops; and a 320-byte RAM burst breaks tCEM at every SCK (max ~93 bytes, below) |
| R3 weights also through RAM | larger | — | out of scope |

### RAM protocol choice

| | SPI-mode commands (EBh read, 38h write) | QPI mode (35h first) |
|---|---|---|
| read header | 8 cmd + 6 addr + 6 wait = **20 SCK** | 2 + 6 + 6 = 14 SCK |
| write header | 8 + 6 = 14 SCK | 2 + 6 = 8 SCK |
| state | none | RAM keeps QPI until F5h/reset; whether a reset sent in the "wrong" mode works is **[UNKNOWN]** (v2c_01 §7) |

Recommended: **SPI-mode EBh/38h** (quad address and data, serial command): 6 SCK more per visit, but no
mode state to lose across a chip reset or a host that power-cycles the Pmod.

### Limits from the datasheet (all verified, APS6404L Rev 2.7)

- **tCEM ≤ 8 µs** (Table 10, standard grade; -SN = Tc −40…85 °C, Table 1). Every read and write must end with
  /CE high, or refresh is blocked and data is lost (§9.6). **SCK must not pause inside a RAM burst** (the pause
  counts against tCEM): the burst size m must be fixed by the buffer, not by back-pressure.
- tCPH ≥ 18 ns between RAM commands (Table 10); A's /CS gap state already gives ≥ 1 SCK.
- Max SCK: 84 MHz for EBh/38h linear bursts, 33 MHz for 03h (§9.5). Our ≤ 25 MHz is far below.
- Page 1 KB; a linear burst may cross a page boundary once (§9.2): never an issue for ≤ 93-byte bursts.
- Power-up: 150 µs, then reset 66h + 99h before use (v2c_01 §2). **The chip must issue the RAM reset** (an
  `AINIT` command, or as part of the first AWRITE) — the host cannot reach the RAM while the chip owns the Pmod.

Bytes per RAM burst within tCEM (SPI-mode EBh, 20-SCK header, continuous SCK) [CALC, v2c_01 §6]:

| SCK (A's divider) | max bytes per burst | max m (5 bytes per chunk) |
|---|---|---|
| 25 MHz (clk/2) | 89 | 17 |
| 12.5 MHz (clk/4, A's default) | 39 | 7 |
| 6.25 MHz (clk/8) | 14 | 2 |
| 3.125 MHz (clk/16) | 1 | 0: **unusable for the RAM** |

So the RAM path needs its own SCK setting (≥ 6.25 MHz) or a rule that ARUN refuses clk/16. **AWRITE**: the
host's bytes arrive far slower than tCEM allows, so the chip writes each received group of bytes with its own
38h command (14-SCK header), never holding /CE low while waiting for SPI.

## 4. Speed per token (TriLM-99M ternary projections)

Per RAM visit: flash re-open 40 SCK (A's 6Bh, notes/v2_02) + RAM read header 20 SCK; per chunk: 8 SCK of
weights + 10 SCK of activations. **SCK per chunk = 18 + 60 / m.** ~48 M ternary MACs per token = 2.4 M chunks
[v2_01].

| m | buffer beyond A | SCK / chunk | per token at 25 MHz | at 12.5 MHz |
|---|---|---|---|---|
| 1 | none (A's 5-byte register) | 78 | 7.5 s | 15.0 s |
| 2 | 5 bytes | 48 | 4.6 s | 9.2 s |
| 4 | 15 bytes | 33 | 3.2 s | 6.3 s |
| 7 | 30 bytes | 26.6 | 2.6 s | 5.1 s (largest m within tCEM at 12.5 MHz) |

For comparison A ~30 s and B ~15 s per token (host-SPI bound, v2_01). Host traffic falls to the vectors
once per layer plus 8–12 result bytes per row group. All figures exclude the PC's FP16 parts and RP2040
Python overhead, which v2_01 already flagged as likely to dominate. [CALC from verified timing; real SCK at
25 MHz depends on A's F4 sample-window calibration on silicon.]

## 5. Tiles [ESTIMATE]

A: 63.8 % utilisation in 2x2 with the tech-LEF RC; with calibrated `LAYERS_RC` B gained ~1.5 points of
buffers (v2b_02). C adds a RAM sequencer (comparable to `qspi_fetch`), the R1 resume path (+8 address bits),
dynamic IO enables, and for m ≥ 2 a 5(m−1)-byte buffer (40 flip-flops per extra chunk plus read muxes).

| m | estimate | tiles |
|---|---|---|
| 1–2 | A + ~6–10 points | 2x2 possible but tight (≥ 70 %, where B's slew trouble started) |
| 4–7 | A + ~12–20 points | 3x2 |

A synthesis-only area check (1.55× LibreLane factor, v1 notes) comes before the first hardening run.

## 6. Hardening plan

A's config + lrc2's calibrated `LAYERS_RC` + post-GRT slew margin 20 % (55 hangs repair once the RC is
calibrated, v2b_02); committed in `src/config.json`. The `LAYERS_RC` values were fitted on B's 3x2 layout;
re-fitting them on C's own first run is a candidate single-setting change. One setting per run.

## 7. Decisions for the owner (needed before RAM-controller RTL)

| decision | options | recommendation |
|---|---|---|
| **R1** | allow a minimal change to A's signed-off `qspi_fetch` (24-bit byte pointer, pause/resume), re-verified with A's full flash test set plus new tests; or stop C | allow R1: nothing else works within tCEM and area |
| **m and tiles** | m = 1–2 on 2x2 (≈ 7.5–4.6 s/token at 25 MHz) or m = 4–7 on 3x2 (≈ 3.2–2.6 s) | m = 2 on 2x2: smallest change from A, keeps A's tile cost; 3x2 also brings back B's long-net risk |
| RAM SCK | share A's divider (and forbid clk/16 for ARUN) or a fixed RAM divider | share A's divider, ARUN rejects clk/16 |

## 8. Bench-only unknowns (cannot be settled from documents; v2c_01 §7)

- Whether a RAM reset sent in SPI mode works on a RAM left in QPI mode (avoided by never using QPI).
- Whether the RAM IO lines are low during its 150 µs power-up on the TT board (the Pmod has no pull-downs).
- Whether the W25Q128JV "4-byte alignment for Quad Read" note (§9.6 note 6) applies to 6Bh — relevant to R1
  resuming at an arbitrary byte; to be checked in the datasheet before R1 RTL, or the resume rounds down to a
  4-byte boundary (chunks are 4 bytes, so resume points are 4-byte aligned anyway when the stream starts on
  a page).
- tCH/tCL in Table 10 is given in units of tCLK(min); read as a duty-cycle spec inside a burst.
- Whether the store ships schematic v2.2 (the board revision is not on the store page).
