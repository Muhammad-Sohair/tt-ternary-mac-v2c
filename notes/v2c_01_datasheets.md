# v2c Track 1: datasheet facts for option C (activations in the Pmod PSRAM)

Checked 2026-11-04. Read-only. Every value below comes from a document listed in section 8, with its
section, table or figure. `[CALC]` marks numbers I worked out from datasheet values. `[UNKNOWN]` means the
document does not say.

## 1. Parts identified

| ref | part (exact) | where it is stated |
|---|---|---|
| U1 | **W25Q128JVSIM** (Winbond, 128 Mbit flash, SOIC-8 5.23 mm) | mole99/qspi-pmod schematic v2.2: symbol value and MPN field "W25Q128JVSIM" |
| U2 (PSRAM A) | **APS6404L-3SQR-SN** (AP Memory, 64 Mbit QSPI PSRAM, SOP-8 150 mil) | schematic v2.2: value "878-APS6404L-3SQR-SN" (Mouser order code), MPN field "APS6404L-3SQR-SN" |
| U3 (PSRAM B) | **APS6404L-3SQR-SN** | same as U2 |
| R1, R2, R3 | 10 kΩ pull-ups (0402WGF1002TCE) | schematic v2.2, "CS pull up" block |
| C7 | 22 pF, optional SCK delay cap | schematic v2.2, "CS cut / clock delay" block |

- The earlier note "2 × APS6404L-3SQR" was right. The full part number is **APS6404L-3SQR-SN**.
- The TT store page and TT's QSPI guide call the flash "25Q128JVSM", which matches the W25Q128JV family. The
  store page as fetched did not show part numbers (search snippets did), so the schematic is the authority here.
- What the suffix means (APS6404L datasheet Rev 2.7, Table 1): "-SN" is the SOP-8 package with **Tc = −40 to
  +85 °C** (standard grade) and **84 MHz** max. The "R" in 3SQR means RBX (row-boundary crossing), which
  allows linear bursts across pages (Table 1 note).

## 2. APS6404L-3SQR-SN timing (Rev 2.7, 5 Jan 2024)

| parameter | value | condition | ref |
|---|---|---|---|
| **tCEM** (CE# low pulse width, max) | **8 µs** | standard grade (−40 to 85 °C, which covers -SN) | §16.7 Table 10 |
| tCEM, extended grade | 3 µs | −40 to 105 °C parts (3SQRX); not our part | Table 10; change log v2.4 (changed from 4 µs to 3 µs) |
| What happens if CE# stays low too long | "Not doing so will block internal refresh operations and cause memory failure" | all reads and writes must end by raising CE# "immediately afterwards" | §9.6 |
| Refresh | Self-managed; the host does no refresh, only has to obey tCEM | | p.1 Specifications; §2 |
| tCPH (CE# high between bursts, min) | 18 ns | | Table 10 |
| tCLK (min period), 03h SPI Read | 30.3 ns (33 MHz) | | Table 10; §9.5 |
| tCLK, 0Bh QPI Fast Read | 15.1 ns (66 MHz) | | Table 10 |
| tCLK, linear burst / page crossing | 11.9 ns (84 MHz) | | Table 10 note 1 |
| tCLK, Wrap-32 | 7.5 ns (133 MHz @ 3.0 V ±10 %), 9.17 ns (109 MHz @ 3.3 V ±10 %) | | Table 10 |
| tCH/tCL (clock high/low width) | min 0.45, max 0.55, in units of "tCLK(min)" | see the [UNKNOWN] list for how to read this | Table 10 |
| tKHKL (rise/fall time) | ≤ 1.5 ns | 20–80 % VDD | Table 10 note 4 |
| tCSP (CE# setup to CLK rise) | ≥ 2.5 ns | | Table 10 |
| tCHD (CE# hold from CLK rise) | ≥ 3.0 ns; for reads, tCHD > tACLK + tCLK is recommended | | Table 10; §9.6 Fig. 3 text |
| tSP / tHD (input setup / hold) | ≥ 2 ns / ≥ 2 ns | to the active (rising) CLK edge | Table 10; Fig. 20 |
| tACLK (CLK falling edge to output) | 2 to 5.5 ns | data launched on the CLK **falling** edge | Table 10; §11.1 / §13.1 text |
| tKOH (data hold after CLK falling edge) | ≥ 1.5 ns | | Table 10; Fig. 21 |
| tHZ (CE# high to DQ high-Z) | ≤ 5.5 ns | | Table 10 |
| tPU (power-up) | 150 µs after VDD ≥ VDDmin, **then a user-issued RESET** | during it: CLK low, CE# high (tracking VDD), SIO[3:0] low | §8, Fig. 1 |
| tRST (end of RST to next command) | ≥ 50 ns | | §8; Table 10 |
| Max load | CL 15 pF | package | Table 7; Table 10 note 2 |
| Power-on state | SPI mode, linear burst, 50 Ω drive. "It is required to have CE# high before beginning any operations" | | §9.3, §9.4, §10 |

### Commands (§9.5 table and figures)

| cmd | SPI mode: cmd / addr / wait / data | max f | QPI mode: cmd / addr / wait / data | max f | figure |
|---|---|---|---|---|---|
| 03h Read | S / S / 0 / S | 33 MHz | n/a | | Fig. 6 |
| 0Bh Fast Read | S / S / **8** / S | 133/84* | Q / Q / **4** / Q | 66 MHz | Fig. 7, 14 |
| EBh Fast Read Quad | S / Q / **6** / Q | 133/84* | Q / Q / **6** / Q | 133/84* | Fig. 8, 15 |
| 02h Write | S / S / 0 / S | 133/84* | Q / Q / 0 / Q | 133/84* | Fig. 9, 16 |
| 38h Quad Write | S / Q / 0 / Q | 133/84* | same as 02h | | Fig. 10, 16 |
| 35h Enter Quad (QPI) | S, SPI mode only | 133 | n/a | | Fig. 11 |
| F5h Exit Quad | n/a | | Q, QPI mode only | 133 | Fig. 17 |
| 66h / 99h Reset Enable / Reset | S | 133 | Q | 133 | Fig. 18, 19 |
| C0h Wrap Boundary Toggle | S | 133 | Q | 133 | Fig. 4, 5 |
| 9Fh Read ID | S / S / 0 / S | 33 | n/a | | Fig. 13 |

\* 133 MHz (3.0 V) or 109 MHz (3.3 V) for Wrap-32; **84 MHz for linear burst** (§9.5 note).

**Clock counts per command, read from the figures** (S = 1 bit per clock, Q = 4 bits per clock):
- SPI EBh: 8 clocks of command + 6 of address + 6 wait = **20 clocks**, then 2 clocks per byte (Fig. 8).
- QPI EBh: 2 + 6 + 6 wait = **14 clocks**, then 2 per byte (Fig. 15).
- SPI 38h: 8 + 6 = **14 clocks**, then 2 per byte (Fig. 10).
- QPI 02h/38h: 2 + 6 = **8 clocks**, then 2 per byte (Fig. 16).
- SPI 0Bh: 8 + 24 + 8 wait = 40 clocks, then 8 per byte (Fig. 7).

Other rules:
- Reset must come straight after Reset-Enable. Any other command in between cancels it (§14). Reset puts
  the device in SPI standby (§14).
- Nibble order: the high nibble goes first, IO3..IO0 = bits 7..4 then 3..0 (Fig. 8, 10, 15, 16). This is
  the same order as the flash's 6Bh.

**At our clocks (25 MHz and below) every frequency limit is met by a wide margin**, including 03h
(33 MHz). The binding constraints are tCEM and the IO round trip, not f(max).

## 3. Burst, wrap and page rules (Rev 2.7)

- **Page size: 1024 bytes** (CA[9:0]) (§9.2).
- **Default after power-up: linear burst**, which crosses page boundaries (§9.2, §10).
- A linear burst that crosses a page boundary has max CLK **84 MHz**, and **"it can cross page boundary
  one time only in a burst"** (§9.2). So one burst may span at most two pages.
- **Wrap-32** (CA[4:0]) is selected by the C0h Wrap Boundary Toggle. The command flips between linear and
  Wrap-32; it has no explicit setting. In Wrap-32 a burst may not cross a page (§9.2, §10).
- RBX/linear crossing is allowed "as long as tCEM is met" (p.1 Features).
- The older Rev 2.3 (Table 3) also lists a "Wrap 1K" behaviour when page crossing is disabled. Rev 2.7 drops
  that table. It does not matter for C if C stays in the default linear mode and never sends C0h.

## 4. Pmod pin map, and how A's RTL uses it

From the schematic v2.2 (all three memories are drawn with net labels) and the README pinout table:

| Pmod pin | TT pin | net | U1 flash | U2 PSRAM A | U3 PSRAM B | A's RTL (`tt_um_msohair_tmac2.v` l.309–310, `qspi_fetch.v`) |
|---|---|---|---|---|---|---|
| 1 | uio[0] | PMOD1 | /CS (pin 1) | | | `f_csn`, oe = 1 |
| 2 | uio[1] | PMOD2 | DI/IO0 (5) | DI/IO0 (5) | DI/IO0 (5) | `f_io0`, oe = `f_io0_oe` (driven during cmd/addr only); in = io_in[0] |
| 3 | uio[2] | PMOD3 | DO/IO1 (2) | DO/IO1 (2) | DO/IO1 (2) | out 0, **oe = 0** (input only); in = io_in[1] |
| 4 | uio[3] | PMOD4 | CLK (6) | CLK (6) | CLK (6) | `f_sck`, oe = 1 |
| 7 | uio[4] | PMOD5 | IO2 (3) | IO2 (3) | IO2 (3) | out 0, **oe = 0**; in = io_in[2] |
| 8 | uio[5] | PMOD6 | IO3 (7) | IO3 (7) | IO3 (7) | out 0, **oe = 0**; in = io_in[3] |
| 9 | uio[6] | PMOD7 | | /CE (1) | | constant 1, oe = 1 (RAM A deselected) |
| 10 | uio[7] | PMOD8 | | | /CE (1) | constant 1, oe = 1 (RAM B deselected) |

(Header pin numbers 1–4 / 7–10 are J1's IO1–IO8. Pins 5, 11 are GND and 6, 12 are 3.3 V.)

A's RTL matches the schematic on every pin. Two consequences for C:
- A never drives uio[2], uio[4] or uio[5]. C must drive all four IOs (QPI commands, the 38h address/data,
  QPI addresses), so C needs per-pin output enables on uio[1,2,4,5] that it can switch.
- A only ever issues 6Bh at {page, 8'h00} (address[7:0] hard-wired to 0, `qspi_fetch.v` `cmd_word`). See §6.

**Pull-ups and pull-downs on the Pmod:** only R1–R3, 10 kΩ to +3.3 V on the three chip selects (PMOD1/7/8,
on the memory side of the J2 cut jumpers). **There are no pulls on SCK or IO0–IO3.** The README says "a 1k
resistor pulls up the chip's /CS". The schematic and BOM field say **10k**; I trust the schematic.
J2 (CONFIG) holds solder-bridge pairs: CS1/CS7/CS8 are closed by default (cut to disconnect a chip), and an
SCK-to-22 pF pair is open by default (bridge it to add C7 on SCK).

TT's QSPI guide (ETR script comment) says SD2/SD3 are held high by **RP2040 internal pull-ups** in
single-SPI mode. Those pulls are on the demo board's MCU, not on the Pmod.

## 5. Bus sharing conclusion

- **All three chips share SCK and IO0–IO3.** Only the /CS lines are separate (schematic v2.2). So every
  access must be serialised: **at most one /CS low at any time.** No part of the board allows overlap: no
  bus switch and no separate data lanes.
- Deselected devices do not drive the bus:
  - flash: "When /CS is high the device is deselected and the … IO0, IO1, IO2, IO3 pins are at high
    impedance" (W25Q128JV Rev F §4.1);
  - PSRAM: "When CE#=1, chip is in standby state" (APS6404L Table 2); outputs go high-Z within tHZ ≤ 5.5 ns
    of CE# rising (Table 10).
- SCK toggling while a chip's /CS is high does no harm: neither device accepts commands while deselected
  (flash §4.1; PSRAM Table 2).
- Flash IO3 is /HOLD only when QE = 0. With QE = 1, "/HOLD function is disabled" (W25Q128JV §7.1.4, §4.4).
  /HOLD acts only "while /CS is low" anyway (§4.4). So RAM traffic on IO2/IO3 cannot hold or write-protect
  the deselected flash.
- **A RAM in QPI mode with CE# high:** the datasheet says only that it is in standby (Table 2) and that QPI
  persists until F5h or Reset (§13.3, §14). Nothing suggests it reacts to bus activity while deselected.
  It can stay in QPI mode for good while the flash runs 6Bh. The flash's 6Bh and the RAM's EBh/38h can
  therefore share the four lines, **time-multiplexed by /CS**.
- Turnaround when switching devices: the previous device releases the bus within tSHQZ ≤ 7 ns (flash, see
  `v2_02_flash_timing.md`) or tHZ ≤ 5.5 ns (PSRAM). One 20 ns clk with both /CS high covers both, and
  tCPH ≥ 18 ns. A's S_GAP already waits one SCK phase (≥ 20 ns).

## 6. Limits on C

### 6.1 tCEM forces burst splitting (8 µs, standard grade)

Assumptions for the `[CALC]` numbers below:
- /CS goes low one SCK half-period before the first rising edge, as A's `S_GAP` does.
- After a read, /CS stays low one more full SCK period, following the §9.6 guidance tCHD > tACLK + tCLK.
- After a write, /CS stays low half a period.
- The SCK is **continuous** inside the burst. Any SCK pause while CE# is low counts against tCEM.

Max bytes per CE#-low window:

| SCK | period | read clocks in 8 µs | **SPI-mode EBh read** (20-clk hdr) | **QPI EBh read** (14-clk hdr) | SPI 38h write (14) | QPI 38h write (8) |
|---|---|---|---|---|---|---|
| 25 MHz (clk/2) | 40 ns | 198 | **89 B** | **92 B** | 92 B | 95 B |
| 12.5 MHz (clk/4, A's default) | 80 ns | 98 | **39 B** | **42 B** | 42 B | 45 B |
| 6.25 MHz (clk/8) | 160 ns | 48 | **14 B** | **17 B** | 17 B | 20 B |
| 3.125 MHz (clk/16) | 320 ns | 23 | **1 B** | **4 B** | 5 B | 8 B |

For comparison, on an extended-grade part (3 µs, not ours) a QPI read would allow 29 / 11 / 1 / 0 bytes.

Consequences:
- **Splitting is unavoidable for any vector longer than about 90 bytes, even at 25 MHz.** At the default
  12.5 MHz it is 42 bytes per burst. The RAM side of C must be a burst engine with a byte counter that
  raises CE#, re-issues EBh at address + n, and continues.
- **The clk/16 setting is effectively unusable for the PSRAM** (1–4 bytes per command). At clk/8 every
  burst carries 14 header clocks for 17 data bytes.
- The A-style "pause SCK and hold /CS low until the datapath wants the next chunk" **cannot be used on the
  PSRAM.** The pause counts toward tCEM, and if tCEM is exceeded refresh is blocked and data is lost (§9.6).
  The RAM side must either run to completion or close CE# between chunks. A chunk of ≤ 4 bytes per
  command, as in A's CHUNK = 4, works but costs about 14 header clocks per 4 bytes.
- **Page crossing is not a limit at these sizes.** Each burst is ≤ 95 bytes, far below 1024, so a burst
  crosses a page boundary at most once, as §9.2 requires. Default linear mode is fine. Do not send C0h.

### 6.2 Switching between the flash stream and RAM

- **The flash stream cannot stay open during a RAM access.** Both use the same IO lines and SCK, so flash
  /CS must go high, and a W25Q128JV read ends when /CS goes high (flash §8.2.6, as used in
  `v2_02_flash_timing.md`).
- Cost of each flash→RAM→flash round trip `[CALC]`, excluding the data bytes:
  - RAM header: 20 clocks for SPI EBh, 14 for QPI EBh;
  - flash re-open: 6Bh + 24-bit address + 8 dummy = **40 clocks** (W25Q128JV Fig. 20 / `v2_02`);
  - plus about 3 clk of /CS gaps.
  - Total: **2.4 µs at 25 MHz, 4.8 µs at 12.5 MHz, 9.6 µs at 6.25 MHz** with SPI-mode RAM. QPI saves 6
    SCK: 2.16 / 4.32 / 8.64 µs.
- **A's fetcher cannot reopen the flash mid-stream.** `qspi_fetch.v` builds the address as `{page, 8'h00}`,
  so it can only restart at a 256-byte boundary. C must keep a byte-resolution resume address, or arrange
  to switch to RAM only at 256-byte boundaries of the weight stream. The flash AC table also has note 6,
  "4-bytes address alignment for Quad Read" (W25Q128JV Rev F §9.6). The resume address should be a
  multiple of 4. Whether that note applies to 6Bh or only to EBh is `[UNKNOWN]` (see §7).
- A layout that avoids most switches: read the whole activation vector from RAM into on-chip storage once
  per row group, in ⌈len/burst⌉ bursts, then run the flash stream uninterrupted. If on-chip storage cannot
  hold the vector, every interleave pays the round trip above.

### 6.3 Mode switching (SPI vs QPI on the RAMs)

- Entering QPI costs one 8-clock 35h command per RAM, once (Fig. 11). After that every RAM access saves
  6 header clocks for reads (20 → 14) and 6 for writes (14 → 8).
- QPI persists across deselection. The flash is unaffected because its /CS is high (§5). Using QPI does not
  require the flash to change mode.
- **Power-up:** a user-issued Reset (66h, then 99h) is required after tPU (§8). C must issue it before
  first use. Because a RAM could already be in QPI from an earlier project or a test, the reset must work
  in either mode. See §7.

### 6.4 Signal timing at ≤ 25 MHz (PSRAM vs flash)

- PSRAM tACLK ≤ 5.5 ns and tKOH ≥ 1.5 ns are close to the flash's tCLQV ≤ 6 ns and tCLQX ≥ 1.5 ns. A's
  programmable sample point (1–4 clk after the SCK fall) and SCK divider apply to the RAM unchanged.
  Round trip: TT GPIO page, "the worst round trip latency was measured to be 20 ns", with pin-to-pin
  variance under 2 ns.
- Inputs to the PSRAM: tSP/tHD 2 ns. Changing IO on SCK falling edges, as A does, gives half an SCK period
  (≥ 20 ns at 25 MHz) on each side.
- TT GPIO limits: outputs rated 33 MHz, inputs 66 MHz. "People have driven the clock line of the QSPI Pmod
  at 32 MHz successfully." 25 MHz SCK is inside the rating.

### 6.5 Verdict

**Nothing found breaks C.** Bus sharing is plain /CS time-multiplexing, and the PSRAM is fine at our
clocks. But three constraints change the design:
1. **tCEM = 8 µs** caps a burst at about 89–92 bytes at 25 MHz and 39–42 at 12.5 MHz. The RAM engine must
   split bursts, and must not pause SCK with CE# low.
2. The flash stream has to be closed and re-opened (40 SCK) around every RAM access, at **byte-resolution
   addresses**, which A's fetcher cannot do.
3. C needs output enables on IO1–IO3, which A never drives.

## 7. [UNKNOWN] list

1. **tCH/tCL "0.45 to 0.55 tCLK(min)"** (Table 10). Read literally, it would cap the clock high/low width at
   0.55 × the minimum period, which would rule out slow or paused clocks. Most likely it is a duty-cycle
   spec. The datasheet gives no maximum tCLK. Tried: Rev 2.7 and Rev 2.3; neither defines it further.
   Treat as "continuous SCK, near 50 % duty, inside a burst."
2. **Whether Reset (66h/99h) sent in SPI form works on a device in QPI mode, or the reverse.** §14 gives
   both forms but not cross-mode behaviour. A common approach, not from the datasheet, is to send the QPI
   form and then the SPI form. Needs a bench test.
3. **Whether the wrap setting (C0h toggle) is cleared by Reset.** §14 says only that reset returns the
   device to "SPI standby mode", the power-up default. Irrelevant if C never sends C0h.
4. **SIO[3:0] must be low during tPU** (§8). The Pmod has no pull-downs, and the TT demo board and RP2040
   control those pins at power-up, not our design. Whether this is met is unknown. The power-up reset in
   §6.3 is the mitigation.
5. **W25Q128JV note 6 ("4-bytes address alignment for Quad Read")**: does it cover 6Bh or only EBh?
   (§9.6 note 6, Rev F, page with the AC table.)
6. **The exact board revision the TT store ships.** The repo HEAD (commit 250aee2, 21 Feb 2026) is
   schematic v2.2. The store page I fetched showed no revision or part list.
7. **README "1k" vs schematic "10k" CS pull-ups.** The schematic and BOM say 10 kΩ. Not checked on a
   physical board.

## 8. Sources

| document | revision / date | URL |
|---|---|---|
| AP Memory APS6404L-3SQR QSPI PSRAM datasheet ("APM SPI 3V PSRAM Datasheet.pdf") | **Rev 2.7, 5 Jan 2024**, 28 pp. (primary) | https://www.apmemory.com/cn/downloadFiles/032411212009597427 |
| same, older | Rev 2.3, 30 Apr 2020, 24 pp. (cross-check only) | https://www.pjrc.com/store/APS6404L_3SQR.pdf |
| mole99/qspi-pmod schematic (KiCad + PDF), README | **QSPI-Pmod v2.2** (title block), repo commit 250aee2c4e1e92606529e1285b97740970104465 (21 Feb 2026) | https://github.com/mole99/qspi-pmod (qspi-pmod.pdf, qspi-pmod.kicad_sch, README.md) |
| Winbond W25Q128JV datasheet | Revision F, 27 Mar 2018 (§4.1, §4.4, §7.1.4, §9.6 note 6) | https://www.winbond.com/resource-files/w25q128jv%20revf%2003272018%20plus.pdf |
| Tiny Tapeout GPIO specs (IO speed, 20 ns round trip, Pmod 32 MHz) | undated web page, fetched 2026-11-04 | https://tinytapeout.com/specs/gpio/ |
| Tiny Tapeout "Configuring and flashing the QSPI Pmod" guide | undated, fetched 2026-11-04 | https://tinytapeout.com/guides/configure-flash-qspi-pmod/ |
| TT store QSPI Pmod listing | fetched 2026-11-04 (no part list visible in the fetch) | https://store.tinytapeout.com/products/QSPI-Pmod-p716541602 |
| Local: A's RTL and notes | read-only | `v2/src/qspi_fetch.v`, `v2/src/tt_um_msohair_tmac2.v` (l.304–310), `v2/notes/v2_01_spec.md`, `v2/notes/v2_02_flash_timing.md` |
