# SPDX-License-Identifier: Apache-2.0
"""Floating Pmod inputs (no Pmod, uio_in high-Z) must not reach the datapath in any operation that does not
read the flash or the RAM: the v1 SPI flow and BIST give exact results, and no output pin is ever X.
Run at RTL and at gate level (GATES=yes): owner's check (b), notes/v2c_05."""

import cocotb
from cocotb.triggers import ClockCycles, RisingEdge
from cocotb.types import LogicArray

from test import read_raw, start, xfer
from tmac_model import TMAC, bist_expected


@cocotb.test()
async def test_float_inputs_v1_flow(dut):
    await start(dut)
    dut.uio_in.value = LogicArray("ZZZZZZZZ")
    bad = []

    async def watch():
        while True:
            await RisingEdge(dut.clk)
            for name in ("uo_out", "uio_out", "uio_oe"):
                if not getattr(dut, name).value.is_resolvable:
                    bad.append((name, str(getattr(dut, name).value)))
    cocotb.start_soon(watch())
    m = TMAC()
    W = [0xF2, 0x79, 0x80, 0x01]
    for i, b in enumerate(W):
        m.write_wbyte(i, b)
    await xfer(dut, [0x10] + W)
    a = [5, -3, 127, -128, 9]
    for i, v in enumerate(a):
        m.write_act(i, v & 0xFF)
    await xfer(dut, [0x20] + [v & 0xFF for v in a])
    await xfer(dut, [0x31])
    m.compute(clear=True)
    await ClockCycles(dut.clk, 5)
    raw = await read_raw(dut)
    assert raw == m.acc, f"{raw} != {m.acc}"
    await xfer(dut, [0x60])
    await ClockCycles(dut.clk, 2000)
    sig = await xfer(dut, [0x61], 2)
    assert (sig[1] << 8 | sig[2]) == bist_expected()
    assert not bad, f"X/Z on outputs: {bad[:5]}"
