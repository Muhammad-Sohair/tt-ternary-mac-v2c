# SPDX-License-Identifier: Apache-2.0
"""Pin-level model of a QSPI PSRAM (the RAM chips on the TT QSPI Pmod), for the option-C testbench.

The protocol engine (Psram) is pure Python and simulator-free: feed it every pin change with a time
stamp, read back what the RAM drives on IO0..IO3, and collect protocol and timing errors. A cocotb
adapter (PsramPins) connects one or two engines and the flash model to the shared uio bus.

Every timing value and every protocol choice that depends on the datasheet lives in PsramTiming.
PsramTiming has NO defaults for datasheet values on purpose: the numbers come from
notes/v2c_01_datasheets.md (Track 1) and are passed in by the tests. Until then only the unit
tests below use clearly-labelled placeholder values, to exercise the engine itself.

Commands modelled (opcode -> behaviour), all mode 0, MSB first:
  SPI mode : 0x03 read, 0x0B fast read, 0xEB quad read, 0x02 write, 0x38 quad write,
             0x35 enter QPI, 0x66/0x99 reset enable/reset
  QPI mode : same opcodes sent 4 bits per clock; 0xF5 exit QPI
Which of these the real part supports, its wait cycles and wrap rules are [PENDING DATASHEET].
"""

from dataclasses import dataclass, field


@dataclass
class PsramTiming:
    # --- datasheet values: no defaults, must come from v2c_01 -------------------------------
    t_cem_max_ns: float        # max /CS low time (refresh); exceeding it is an error
    t_cph_min_ns: float        # min /CS high time between commands
    t_valid_ns: float          # clock-to-output valid after the SCK fall (incl. board/pad delay)
    t_hold_ns: float           # output hold after the SCK fall
    wait_fast_read: int        # wait clocks for 0x0B (SPI)
    wait_quad_read: int        # wait clocks for 0xEB (SPI command, quad address/data)
    wait_qpi_read: int         # wait clocks for 0xEB in QPI mode
    page_bytes: int            # page size for the burst rule below
    linear_burst_crosses_page: bool  # True: linear burst continues into the next page
    size_bytes: int = 8 * 1024 * 1024
    commands: frozenset = field(default_factory=lambda: frozenset(
        {0x03, 0x0B, 0xEB, 0x02, 0x38, 0x35, 0xF5, 0x66, 0x99}))


class Psram:
    """One PSRAM chip. Call pins(t_ns, cs_n, sck, io_from_bus) on every change; .drive is the
    nibble the RAM puts on IO0..IO3 (bit k = IOk) and .oe which lines it drives (0 = none)."""

    def __init__(self, timing: PsramTiming, name="ram"):
        self.t, self.name = timing, name
        self.mem = {}
        self.errors, self.log = [], []
        self.qpi = False
        self.cs, self.sck = 1, 0
        self.t_cs_fall = self.t_cs_rise = None
        self.drive, self.oe = 0xF, 0
        self.pending = []                     # (time, nibble, oe) output events

    # ---- bus side ----
    def outputs_at(self, t_ns):
        """What the RAM drives at time t_ns: (nibble, oe_mask). Garbage between hold and valid."""
        nib, oe = self.drive, self.oe
        for when, n, o in self.pending:
            if when <= t_ns:
                nib, oe = n, o
        return nib, oe

    def pins(self, t_ns, cs_n, sck, io):
        # settle output events up to now
        keep = []
        for ev in self.pending:
            if ev[0] <= t_ns:
                self.drive, self.oe = ev[1], ev[2]
            else:
                keep.append(ev)
        self.pending = keep

        if cs_n != self.cs:
            if sck:
                self.errors.append(f"{self.name}: SCK high on a /CS edge (not mode 0)")
            if cs_n == 0:
                if self.t_cs_rise is not None and t_ns - self.t_cs_rise < self.t.t_cph_min_ns:
                    self.errors.append(f"{self.name}: /CS high {t_ns - self.t_cs_rise:.1f} ns < tCPH")
                self.t_cs_fall = t_ns
                self._start()
            else:
                if self.t_cs_fall is not None and t_ns - self.t_cs_fall > self.t.t_cem_max_ns:
                    self.errors.append(f"{self.name}: /CS low {t_ns - self.t_cs_fall:.0f} ns > tCEM")
                self.t_cs_rise = t_ns
                self._end()
                self.drive, self.oe, self.pending = 0xF, 0, []
            self.cs = cs_n
        elif not cs_n and sck != self.sck:
            if self.t_cs_fall is not None and t_ns - self.t_cs_fall > self.t.t_cem_max_ns:
                self.errors.append(f"{self.name}: clocked {t_ns - self.t_cs_fall:.0f} ns after /CS fall > tCEM")
            if sck:
                self._rise(io)
            else:
                self._fall(t_ns)
        self.sck = sck

    # ---- protocol ----
    def _start(self):
        self.phase, self.bits, self.sreg = "cmd", 0, 0
        self.cmd, self.addr, self.wait_left, self.wbyte, self.wnib = None, 0, 0, 0, 0

    def _width(self):
        if self.phase == "cmd":
            return 4 if self.qpi else 1
        quad = self.qpi or self.cmd in (0xEB, 0x38)
        return 4 if quad else 1

    def _rise(self, io):
        """SCK rising: the RAM samples inputs."""
        if self.phase in ("cmd", "addr"):
            w = self._width()
            val = io & 0xF if w == 4 else io & 1
            self.sreg = (self.sreg << w) | val
            self.bits += w
            if self.phase == "cmd" and self.bits == 8:
                self.cmd, self.sreg, self.bits = self.sreg, 0, 0
                self.log.append(self.cmd)
                if self.cmd not in self.t.commands:
                    self.errors.append(f"{self.name}: unsupported command 0x{self.cmd:02x}")
                    self.phase = "ignore"
                elif self.cmd == 0x35:
                    self.qpi, self.phase = True, "done"
                elif self.cmd == 0xF5:
                    if not self.qpi:
                        self.errors.append(f"{self.name}: 0xF5 outside QPI")
                    self.qpi, self.phase = False, "done"
                elif self.cmd in (0x66, 0x99):
                    if self.cmd == 0x99:
                        self.qpi = False
                    self.phase = "done"
                else:
                    self.phase = "addr"
            elif self.phase == "addr" and self.bits == 24:
                self.addr, self.start_addr = self.sreg % self.t.size_bytes, self.sreg % self.t.size_bytes
                if self.cmd in (0x02, 0x38):
                    self.phase = "wdata"
                else:
                    self.wait_left = {0x03: 0, 0x0B: self.t.wait_fast_read,
                                      0xEB: self.t.wait_qpi_read if self.qpi else self.t.wait_quad_read}[self.cmd]
                    self.phase = "wait" if self.wait_left else "rdata"
                    self.nib_i = 0
        elif self.phase == "wait":
            self.wait_left -= 1
            if self.wait_left == 0:
                self.phase, self.nib_i = "rdata", 0
        elif self.phase == "wdata":
            w = self._width()
            self.wbyte = (self.wbyte << w) | (io & (0xF if w == 4 else 1))
            self.wnib += w
            if self.wnib == 8:
                self.mem[self.addr] = self.wbyte
                self._advance()
                self.wbyte, self.wnib = 0, 0
        elif self.phase in ("done", "ignore"):
            pass

    def _fall(self, t_ns):
        """SCK falling: the RAM shifts out the next output unit (read data only)."""
        if self.phase != "rdata":
            return
        quad = self.qpi or self.cmd == 0xEB
        byte = self.mem.get(self.addr, 0)
        if quad:
            nib = (byte >> 4) if self.nib_i % 2 == 0 else (byte & 0xF)
            oe = 0xF
        else:
            bit = (byte >> (7 - self.nib_i % 8)) & 1
            nib, oe = bit << 1, 0b0010       # single-bit reads come out on IO1 (SO)
        self.pending.append((t_ns + self.t.t_hold_ns, 0x5 ^ (self.nib_i & 0xF), oe))  # garbage after hold
        self.pending.append((t_ns + self.t.t_valid_ns, nib, oe))
        self.nib_i += 1
        per_byte = 2 if quad else 8
        if self.nib_i % per_byte == 0:
            self._advance()

    def _advance(self):
        nxt = self.addr + 1
        if nxt % self.t.page_bytes == 0 and not self.t.linear_burst_crosses_page:
            nxt -= self.t.page_bytes          # wrap inside the page
        self.addr = nxt % self.t.size_bytes

    def _end(self):
        if self.phase in ("cmd", "addr") and self.bits:
            self.errors.append(f"{self.name}: /CS rose mid-{self.phase} after {self.bits} bits")
        if self.phase == "wdata" and self.wnib:
            self.errors.append(f"{self.name}: /CS rose mid-byte in a write")


def check_exclusive_select(cs_flash, cs_a, cs_b):
    """The flash and both RAMs share SCK and IO0..IO3 [PENDING DATASHEET: confirm in v2c_01]:
    at most one /CS may be low."""
    return (cs_flash == 0) + (cs_a == 0) + (cs_b == 0) <= 1


# ---------------- simulator-free self-tests of the engine (pytest) ----------------
# PLACEHOLDER timing: NOT datasheet values. Only to exercise the engine's logic.
_PLACEHOLDER = PsramTiming(t_cem_max_ns=8000, t_cph_min_ns=20, t_valid_ns=7, t_hold_ns=1,
                           wait_fast_read=8, wait_quad_read=6, wait_qpi_read=6,
                           page_bytes=1024, linear_burst_crosses_page=False)


class _Master:
    """Bit-banged mode-0 master for the self-tests (half period 40 ns)."""

    def __init__(self, ram, t0=0.0):
        self.ram, self.t = ram, t0

    def _set(self, cs, sck, io=0):
        self.t += 40
        self.ram.pins(self.t, cs, sck, io)

    def select(self):
        self._set(0, 0)

    def deselect(self):
        self._set(1, 0)

    def clock(self, io=0):
        self._set(0, 0, io)
        nib, _ = self.ram.outputs_at(self.t + 39)   # sample just before this clock's rising edge
        self._set(0, 1, io)
        self._set(0, 0, io)
        return nib

    def send(self, value, nbits, width):
        for i in range(nbits // width - 1, -1, -1):
            self.clock((value >> (i * width)) & ((1 << width) - 1))


def _cmd(m, op, qpi):
    m.send(op, 8, 4 if qpi else 1)


def test_quad_write_then_quad_read():
    r = Psram(_PLACEHOLDER)
    m = _Master(r)
    m.select(); _cmd(m, 0x38, False); m.send(0x000100, 24, 4); m.send(0xA55A1234, 32, 4); m.deselect()
    m.select(); _cmd(m, 0xEB, False); m.send(0x000100, 24, 4)
    for _ in range(_PLACEHOLDER.wait_quad_read):
        m.clock()
    got = [m.clock() for _ in range(8)]
    m.deselect()
    data = 0
    for n in got:
        data = (data << 4) | n
    assert data == 0xA55A1234, hex(data)
    assert not r.errors, r.errors


def test_qpi_mode_and_exit():
    r = Psram(_PLACEHOLDER)
    m = _Master(r)
    m.select(); _cmd(m, 0x35, False); m.deselect()
    assert r.qpi
    m.select(); _cmd(m, 0x38, True); m.send(0x10, 24, 4); m.send(0x7E, 8, 4); m.deselect()
    m.select(); _cmd(m, 0xEB, True); m.send(0x10, 24, 4)
    for _ in range(_PLACEHOLDER.wait_qpi_read):
        m.clock()
    hi, lo = m.clock(), m.clock()
    m.deselect()
    assert (hi << 4 | lo) == 0x7E
    m.select(); _cmd(m, 0xF5, True); m.deselect()
    assert not r.qpi and not r.errors, r.errors


def test_cs_low_limit_is_flagged():
    t = PsramTiming(**{**_PLACEHOLDER.__dict__, "t_cem_max_ns": 500})
    r = Psram(t)
    m = _Master(r)
    m.select(); _cmd(m, 0xEB, False); m.send(0, 24, 4)
    for _ in range(20):
        m.clock()
    m.deselect()
    assert any("tCEM" in e for e in r.errors), r.errors


def test_page_wrap_rule():
    r = Psram(_PLACEHOLDER)
    m = _Master(r)
    m.select(); _cmd(m, 0x38, False); m.send(1023, 24, 4); m.send(0x1122, 16, 4); m.deselect()
    assert r.mem[1023] == 0x11 and r.mem[0] == 0x22 and 1024 not in r.mem
    t = PsramTiming(**{**_PLACEHOLDER.__dict__, "linear_burst_crosses_page": True})
    r2 = Psram(t)
    m2 = _Master(r2)
    m2.select(); _cmd(m2, 0x38, False); m2.send(1023, 24, 4); m2.send(0x1122, 16, 4); m2.deselect()
    assert r2.mem[1024] == 0x22


def test_short_cs_high_and_partial_command():
    r = Psram(_PLACEHOLDER)
    r.pins(0, 0, 0, 0)
    r.pins(10, 1, 0, 0)
    r.pins(15, 0, 0, 0)                       # 5 ns high < tCPH
    r.pins(60, 0, 1, 1)
    r.pins(100, 1, 0, 0)                      # /CS up after 1 command bit
    assert any("tCPH" in e for e in r.errors) and any("mid-cmd" in e for e in r.errors), r.errors


def test_exclusive_select():
    assert check_exclusive_select(0, 1, 1) and check_exclusive_select(1, 1, 1)
    assert not check_exclusive_select(0, 0, 1)
