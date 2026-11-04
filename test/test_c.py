# SPDX-License-Identifier: Apache-2.0
"""cocotb tests for TMAC2C's RAM path (option C). Bit-exact against tmac_model.TMAC2C.

A's own suite (test.py, test_devkit.py) runs unchanged against TMAC2C as the regression; this file
adds the RAM path. The Pmod is modelled as one shared bus (PmodBus): A's W25Q128JV protocol checks
for the flash, the APS6404L-3SQR-SN engine (psram_model, datasheet timing, strict: every datasheet
rule is an assertion) for RAM A, and the bus rules from the schematic: at most one select low, the
chip never drives an IO line the RAM drives, RAM B never selected.

Run: mingw32-make COCOTB_TEST_MODULES=test_c   (RTL)   or with GATES=yes (gate level)
"""

import random

import cocotb
from cocotb.triggers import ClockCycles, Timer
from cocotb.utils import get_sim_time

from psram_model import APS6404L_3SQR_SN, Psram, PsramTiming
from test import (OP_CLEAR, OP_FCFG, OP_FSTART, OP_FSTOP, OP_LOAD_FC, OP_LOAD_W,
                  check_all, check_flash, fstat, image_at, rand_matrix, start, wait_ready, xfer)
from tmac_model import (COLS, FLASH_ERASED, OP_AINIT, OP_ARUN, OP_ASTAT, OP_AWRITE, TMAC2C,
                        pack_acts, pack_stream)

IO_BITS = (1, 2, 4, 5)                     # uio bit for IO0..IO3
F_CS, SCK, RA_CS, RB_CS = 0, 3, 6, 7


def _nib(v):
    return sum(((v >> b) & 1) << k for k, b in enumerate(IO_BITS))


class PmodBus:
    """Flash + RAM A + RAM B on the shared Pmod lines, driving dut.uio_in."""

    def __init__(self, dut, flash_image, ram_timing=APS6404L_3SQR_SN, t_valid=26.0, t_hold=2.0,
                 ram_dead=False, seed=1):
        self.dut, self.image = dut, dict(flash_image)
        self.t_valid, self.t_hold = t_valid, t_hold
        self.rng = random.Random(seed)
        self.ram = Psram(ram_timing, name="RAM A")
        self.ram_dead = ram_dead                   # RAM path broken on silicon: never drives
        self.errors, self.f_cmds = [], []
        self.f_nib, self.uio_in = 0xF, 0
        self.max_ram_cs_low = 0.0
        self.t_ram_fall = None
        self.f_sel, self.f_desel = False, None
        self.task = cocotb.start_soon(self._run())

    def fail(self, msg):
        self.errors.append(msg)
        raise AssertionError(msg)                  # a bus rule is an assertion, not a warning

    # ---- what the Pmod drives on IO0..IO3 ----
    def _apply(self):
        v = self.uio_in
        vo = self.dut.uio_out.value
        if not vo.is_resolvable:
            return
        out = int(vo)
        if not (out >> F_CS) & 1:
            nib = self.f_nib
        elif not (out >> RA_CS) & 1 and not self.ram_dead:
            nib, oe = self.ram.outputs_at(get_sim_time("ns"))
            nib = nib if oe else 0xF
        else:
            nib = 0xF                              # no pull-downs: treat an idle bus as high
        for k, b in enumerate(IO_BITS):
            v = (v & ~(1 << b)) | (((nib >> k) & 1) << b)
        self.uio_in = v
        self.dut.uio_in.value = v

    async def _later(self, delay, fn):
        await Timer(delay, unit="ns")
        fn()

    def _flash_out(self, nib):
        self.f_nib = nib
        self._apply()

    async def _run(self):
        dut = self.dut
        prev = None
        while True:
            await dut.uio_out.value_change
            vo, ve = dut.uio_out.value, dut.uio_oe.value
            if not (vo.is_resolvable and ve.is_resolvable):
                continue
            out, oe = int(vo), int(ve)
            now = get_sim_time("ns")
            fcs, sck, racs, rbcs = (out >> F_CS) & 1, (out >> SCK) & 1, (out >> RA_CS) & 1, (out >> RB_CS) & 1
            if (oe & 0b11001001) != 0b11001001:
                self.fail(f"a select or SCK not driven (oe 0x{oe:02x})")
            if not rbcs:
                self.fail("RAM B selected (TMAC2C never uses it)")
            if not fcs and not racs:
                self.fail("flash and RAM A selected together (shared bus)")
            # ---- RAM A ----
            chip_io = _nib(out) & _nib(oe)
            self.ram.pins(now, racs, sck, chip_io)
            if not racs and not self.ram_dead:
                _, roe = self.ram.outputs_at(now + 1e-3)
                if roe & _nib(oe):
                    self.fail(f"bus fight: chip and RAM A both drive IO 0x{roe & _nib(oe):x}")
                for when, _n, _o in self.ram.pending:
                    cocotb.start_soon(self._later(max(when - now, 0.001), self._apply))
            if racs == 0 and self.t_ram_fall is None:
                self.t_ram_fall = now
            if racs == 1 and self.t_ram_fall is not None:
                self.max_ram_cs_low = max(self.max_ram_cs_low, now - self.t_ram_fall)
                self.t_ram_fall = None
            # ---- flash (A's FlashModel protocol, with the RAM allowed on the bus) ----
            if prev is None:
                prev = (fcs, sck)
                self._apply()
                continue
            pfcs, psck = prev
            prev = (fcs, sck)
            if pfcs != fcs:
                if sck:
                    self.fail("flash: SCK high on a /CS edge (not mode 0)")
                if fcs == 0:
                    self.f_sel, self.nbits, self.sreg, self.falls = True, 0, 0, 0
                    if self.f_desel is not None and now - self.f_desel < 10:
                        self.fail("flash: /CS high < 10 ns (tSHSL1)")
                else:
                    self.f_sel, self.f_desel = False, now
                self._apply()
                continue
            if not self.f_sel or psck == sck:
                self._apply()
                continue
            if oe & 0b00110100:
                self.fail("chip drives IO1..IO3 while the flash is selected")
            if sck:
                if self.nbits < 32:
                    if not (oe >> 1) & 1:
                        self.fail(f"flash: IO0 not driven at command bit {self.nbits}")
                    self.sreg = (self.sreg << 1) | ((out >> 1) & 1)
                    self.nbits += 1
                    if self.nbits == 32:
                        cmd, addr = self.sreg >> 24, self.sreg & 0xFFFFFF
                        self.f_cmds.append((cmd, addr))
                        if cmd != 0x6B:
                            self.fail(f"flash: unexpected instruction 0x{cmd:02x}")
                        self.addr = addr
            else:
                self.falls += 1
                if self.falls >= 40:
                    if (oe >> 1) & 1:
                        self.fail("flash: IO0 still driven during data out")
                    n = self.falls - 40
                    byte = self.image.get(self.addr + n // 2, FLASH_ERASED)
                    nib = (byte >> 4) if n % 2 == 0 else (byte & 0xF)
                    garbage = self.rng.randrange(16)
                    cocotb.start_soon(self._later(self.t_hold, lambda g=garbage: self._flash_out(g)))
                    cocotb.start_soon(self._later(self.t_valid, lambda v=nib: self._flash_out(v)))
            self._apply()

    def check(self, tag=""):
        assert not self.errors, f"{tag}: {self.errors[:3]}"
        assert not self.ram.errors, f"{tag}: {self.ram.errors[:3]}"


# ---------------- host helpers for the RAM opcodes ----------------
async def astat(dut):
    return (await xfer(dut, [OP_ASTAT], 1))[1]


async def wait_ram_idle(dut, limit=400000):
    for _ in range(limit // 2000):
        if not (await astat(dut)) & 0x80:
            return
        await ClockCycles(dut.clk, 2000)
    raise AssertionError("RAM operation never finished")


async def ainit(dut, m):
    await xfer(dut, [OP_AINIT])
    m.ainit()
    await wait_ram_idle(dut)


async def awrite(dut, m, base, data):
    """At clk/8 one RAM write (~140 clk) outlasts an SPI byte at the testbench's host rate (128 clk),
    as docs/info.md warns: there each byte goes in its own AWRITE so none is dropped (OVERRUN is
    tested separately)."""
    if m.f_div == 2:
        for i, b in enumerate(data):
            a = base + i
            await xfer(dut, [OP_AWRITE, a >> 16 & 0xFF, a >> 8 & 0xFF, a & 0xFF, b])
            await wait_ram_idle(dut)
    else:
        await xfer(dut, [OP_AWRITE, base >> 16 & 0xFF, base >> 8 & 0xFF, base & 0xFF] + list(data))
    m.awrite(base, data)
    await wait_ram_idle(dut)


async def arun(dut, m, base, n):
    await xfer(dut, [OP_ARUN, base >> 16 & 0xFF, base >> 8 & 0xFF, base & 0xFF, n >> 8, n & 0xFF])
    m.arun(base, n)
    await wait_ram_idle(dut, limit=2000000)


async def check_c(dut, m, tag=""):
    await check_flash(dut, m, tag)
    a = await astat(dut)
    assert a == m.astat(), f"{tag}: ASTAT 0x{a:02x} != model 0x{m.astat():02x}"


async def matvec_c_on_chip(dut, m, bus, W, x, page, base, tag):
    stream, groups, chunks = pack_stream(W)
    bus.image.update(image_at(page, stream))
    m.flash.update(image_at(page, stream))
    await awrite(dut, m, base, pack_acts(x, chunks))
    await xfer(dut, [OP_FSTART, page >> 8, page & 0xFF])
    m.fstart(page)
    await wait_ready(dut)
    ys = []
    for g in range(groups):
        await xfer(dut, [OP_CLEAR])
        m.clear()
        await arun(dut, m, base, chunks)
        await wait_ready(dut)
        await check_c(dut, m, f"{tag} group {g}")
        ys += m.acc
    for i, row in enumerate(W):
        assert ys[i] == sum(w * v for w, v in zip(row, x)), f"{tag}: model row {i}"
    # After ARUN the array's activation registers must hold exactly the last chunk (as after LOAD_FC):
    # with all-+1 weights loaded over SPI, a CMP adds sum(a) to every row; it must match the model.
    ones = [0xF2] * 4
    await xfer(dut, [OP_LOAD_W] + ones)
    for i, b in enumerate(ones):
        m.write_wbyte(i, b)
    await xfer(dut, [0x30])
    m.compute(clear=False)
    await check_c(dut, m, f"{tag} CMP after ARUN")
    bus.check(tag)
    return ys


# ---------------- tests ----------------
@cocotb.test()
async def test_c_reset_state(dut):
    """ASTAT is 0x00 after reset (TMAC2 answers 0xA3 with STATUS, bit 7 = 1); RAM selects high."""
    await start(dut)
    bus = PmodBus(dut, {})
    m = TMAC2C()
    await check_c(dut, m, "reset")
    out = int(dut.uio_out.value)
    assert (out >> RA_CS) & 1 and (out >> RB_CS) & 1
    assert int(dut.uio_oe.value) == 0b11001001
    bus.check("reset")


@cocotb.test()
async def test_c_ainit_power_up_reset(dut):
    """AINIT sends 66h then 99h; reads/writes before it are refused (NOINIT) and never reach the RAM."""
    await start(dut)
    bus = PmodBus(dut, {})
    m = TMAC2C()
    await xfer(dut, [OP_AWRITE, 0, 0, 0, 0x55])
    m.awrite(0, [0x55])
    await xfer(dut, [OP_ARUN, 0, 0, 0, 0, 1])
    m.arun(0, 1)
    await check_c(dut, m, "before AINIT")
    assert bus.ram.log == [], f"RAM saw {bus.ram.log} before AINIT"
    await ainit(dut, m)
    assert bus.ram.log == [0x66, 0x99] and bus.ram.reset_done
    await check_c(dut, m, "after AINIT")
    bus.check("ainit")


@cocotb.test()
async def test_c_awrite_storage(dut):
    """AWRITE stores bytes at a 24-bit address (incl. across a 1 KB RAM page), each as its own 38h."""
    await start(dut)
    bus = PmodBus(dut, {})
    m = TMAC2C()
    rng = random.Random(11)
    await ainit(dut, m)
    for base, n in ((0x000000, 7), (0x0003FC, 9), (0x7FFFF0, 16)):
        data = [rng.randrange(256) for _ in range(n)]
        await awrite(dut, m, base, data)
        for i, b in enumerate(data):
            assert bus.ram.mem.get(base + i) == b, f"RAM[0x{base + i:06x}]"
    await check_c(dut, m, "awrite")
    assert bus.max_ram_cs_low < APS6404L_3SQR_SN.t_cem_max_ns
    bus.check("awrite")


@cocotb.test()
async def test_c_arun_matvec_all_dividers(dut):
    """y = W x with weights from flash and x from RAM A, at SCK clk/2, /4, /8 (the RAM-mode range)."""
    await start(dut)
    bus = PmodBus(dut, {})
    m = TMAC2C()
    rng = random.Random(21)
    await ainit(dut, m)
    for div in (0, 1, 2):
        await xfer(dut, [OP_FCFG, (1 << 2) | div])
        m.f_div, m.f_samp = div, 1
        n, k = rng.choice(((4, 5), (7, 13), (9, 23)))
        W = rand_matrix(rng, n, k)
        x = [rng.randrange(-128, 128) for _ in range(k)]
        await matvec_c_on_chip(dut, m, bus, W, x, page=0x10 + div, base=rng.randrange(0, 1 << 20),
                               tag=f"div {div}")
    assert bus.max_ram_cs_low < APS6404L_3SQR_SN.t_cem_max_ns, bus.max_ram_cs_low
    bus.check("all dividers")


@cocotb.test()
async def test_c_resume_at_arbitrary_byte(dut):
    """The paused flash stream resumes at the exact next byte: odd chunk counts, a stream that crosses
    256-byte flash pages while paused/resumed, a nonzero start page, and host LOAD_FC continuing a
    stream that AWRITE and ARUN paused."""
    await start(dut)
    bus = PmodBus(dut, {})
    m = TMAC2C()
    rng = random.Random(31)
    await ainit(dut, m)
    # 1) long stream: 8 rows x 205 cols = 2 groups x 41 chunks x 4 bytes = 328 bytes (> 256)
    W = rand_matrix(rng, 8, 205)
    x = [rng.randrange(-128, 128) for _ in range(205)]
    await matvec_c_on_chip(dut, m, bus, W, x, page=0x0123, base=0x00ABC5, tag="long")
    # 2) interleave: LOAD_FC chunks from the host, then AWRITE (pauses the flash), then LOAD_FC again,
    #    then ARUN for the rest, then LOAD_FC: every resume must land on the next byte
    W = rand_matrix(rng, 4, 45)
    stream, _, chunks = pack_stream(W)
    bus.image.update(image_at(0x0200, stream)); m.flash.update(image_at(0x0200, stream))
    x = [rng.randrange(-128, 128) for _ in range(45)]
    xp = pack_acts(x, chunks)
    await xfer(dut, [OP_FSTART, 0x02, 0x00]); m.fstart(0x0200); await wait_ready(dut)
    await xfer(dut, [OP_CLEAR]); m.clear()
    await xfer(dut, [OP_LOAD_FC] + xp[0:10]); m.load_fc(xp[0:10]); await wait_ready(dut)
    await awrite(dut, m, 0x40, xp[10:45])                       # pauses the flash mid-stream
    await check_c(dut, m, "paused by AWRITE")
    await xfer(dut, [OP_LOAD_FC] + xp[10:15]); m.load_fc(xp[10:15]); await wait_ready(dut)
    await arun(dut, m, 0x45, 5)                                  # chunks 3..7 from RAM (odd count)
    await wait_ready(dut)
    await xfer(dut, [OP_LOAD_FC] + xp[40:45]); m.load_fc(xp[40:45]); await wait_ready(dut)
    await check_c(dut, m, "interleaved")
    assert m.acc == [sum(w * v for w, v in zip(row, x)) for row in W]
    # every flash command after the first is a resume at a non-page-aligned byte
    resumes = [a for c, a in bus.f_cmds if a & 0xFF]
    assert resumes, "no resume at a non-page-aligned address was exercised"
    bus.check("resume")


@cocotb.test()
async def test_c_errors_and_blocking(dut):
    """clk/16 refused (DIV); ARUN without a stream refused (STREAM); core-changing opcodes refused
    while a RAM operation runs (BLOCKED); FSTOP aborts ARUN (ABORT) and leaves the RAM deselected;
    AINIT clears the flags."""
    await start(dut)
    bus = PmodBus(dut, {})
    m = TMAC2C()
    await ainit(dut, m)
    await xfer(dut, [OP_ARUN, 0, 0, 0, 0, 3]); m.arun(0, 3)       # no FSTART yet
    await check_c(dut, m, "no stream")
    await xfer(dut, [OP_FCFG, (1 << 2) | 3]); m.f_div = 3
    await xfer(dut, [OP_AWRITE, 0, 0, 0, 1]); m.awrite(0, [1])
    await check_c(dut, m, "clk/16")
    await xfer(dut, [OP_FCFG, (1 << 2) | 2]); m.f_div = 2
    await ainit(dut, m)
    W = rand_matrix(random.Random(5), 4, 200)
    stream, _, chunks = pack_stream(W)
    bus.image.update(image_at(0x0300, stream)); m.flash.update(image_at(0x0300, stream))
    await awrite(dut, m, 0, pack_acts([1] * 200, chunks))
    await xfer(dut, [OP_FSTART, 0x03, 0x00]); m.fstart(0x0300); await wait_ready(dut)
    await xfer(dut, [OP_ARUN, 0, 0, 0, 0, chunks])               # long run at clk/8
    await ClockCycles(dut.clk, 200)
    assert (await astat(dut)) & 0x80, "ARUN finished too early for the blocking test"
    await xfer(dut, [OP_LOAD_W, 0x79, 0x79, 0x79, 0x79])         # refused
    a = await astat(dut)
    assert a & 0x01, f"BLOCKED not set: 0x{a:02x}"
    await xfer(dut, [OP_FSTOP])                                  # aborts the run
    await wait_ram_idle(dut)                                     # the RAM command in flight completes
    a = await astat(dut)
    assert not a & 0x80 and a & 0x02, f"ABORT not reported: 0x{a:02x}"
    assert (int(dut.uio_out.value) >> RA_CS) & 1, "RAM A still selected after abort"
    st, _ = await fstat(dut)
    assert st >> 7 == 0, "flash still open after FSTOP"
    await ainit(dut, m)
    assert (await astat(dut)) == 0x40
    bus.check("errors")


@cocotb.test()
async def test_c_awrite_overrun(dut):
    """At clk/8 a RAM write (16 SCK x 16 clk) is slower than the fastest host byte (128 clk): a byte
    that arrives while the RAM is busy is dropped and OVERRUN is set."""
    await start(dut)
    bus = PmodBus(dut, {})
    m = TMAC2C()
    await xfer(dut, [OP_FCFG, (1 << 2) | 2]); m.f_div = 2
    await ainit(dut, m)
    await xfer(dut, [OP_AWRITE, 0, 0, 0] + list(range(1, 9)))
    await wait_ram_idle(dut)
    a = await astat(dut)
    assert a & 0x08, f"OVERRUN not set: 0x{a:02x}"
    written = [bus.ram.mem.get(i) for i in range(8)]
    assert written[0] == 1 and any(v is None for v in written), written
    bus.check("overrun")


@cocotb.test()
async def test_c_slowest_ram_clock_meets_tcem(dut):
    """The longest RAM burst (10 bytes) at the slowest allowed SCK (clk/8) stays inside tCEM, with SCK
    never paused while /CE is low (both checked by the strict RAM model on every edge)."""
    await start(dut)
    bus = PmodBus(dut, {})
    m = TMAC2C()
    await xfer(dut, [OP_FCFG, (1 << 2) | 2]); m.f_div = 2
    await ainit(dut, m)
    rng = random.Random(41)
    W = rand_matrix(rng, 4, 20)
    x = [rng.randrange(-128, 128) for _ in range(20)]
    await matvec_c_on_chip(dut, m, bus, W, x, page=0x0400, base=0x1000, tag="clk/8")
    assert 0 < bus.max_ram_cs_low < APS6404L_3SQR_SN.t_cem_max_ns, bus.max_ram_cs_low
    dut._log.info(f"longest RAM /CE low at clk/8: {bus.max_ram_cs_low:.0f} ns (tCEM 8000 ns)")
    bus.check("tcem")


@cocotb.test()
async def test_c_dead_ram_chip_still_behaves_like_a(dut):
    """If the RAM path fails on silicon (RAM never drives), ARUN gives wrong numbers but terminates,
    and afterwards every A operation (flash LOAD_FC matvec, BIST, v1 SPI) is exactly as in TMAC2."""
    await start(dut)
    bus = PmodBus(dut, {}, ram_dead=True,
                  ram_timing=PsramTiming(**{**APS6404L_3SQR_SN.__dict__}))
    m = TMAC2C()
    await ainit(dut, m)
    rng = random.Random(51)
    W = rand_matrix(rng, 4, 10)
    stream, _, chunks = pack_stream(W)
    bus.image.update(image_at(0x0500, stream)); m.flash.update(image_at(0x0500, stream))
    await awrite(dut, m, 0, [3] * 10)
    await xfer(dut, [OP_FSTART, 0x05, 0x00]); m.fstart(0x0500); await wait_ready(dut)
    await xfer(dut, [OP_CLEAR]); m.clear()
    await xfer(dut, [OP_ARUN, 0, 0, 0, 0, chunks])
    await wait_ram_idle(dut, limit=2000000)
    # A's flow from here, against a fresh A-only model
    m2 = TMAC2C(flash=m.flash)
    m2.a_init = True
    x = [rng.randrange(-128, 128) for _ in range(10)]
    xp = pack_acts(x, chunks)
    await xfer(dut, [OP_FSTART, 0x05, 0x00]); m2.fstart(0x0500); await wait_ready(dut)
    await xfer(dut, [OP_CLEAR]); m2.clear()
    await xfer(dut, [OP_LOAD_FC] + xp); m2.load_fc(xp); await wait_ready(dut)
    await check_all(dut, m2, "A flow after dead RAM")
    assert m2.acc == [sum(w * v for w, v in zip(row, x)) for row in W]
    bus.check("dead ram")
