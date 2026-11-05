# SPDX-License-Identifier: Apache-2.0
"""How many clock edges does a reset need? rst_n goes through a 2-flop synchroniser (rst_sync) and every
register's reset, including the asynchronous reset of qspi_fetch.ptr, comes from its output, so a reset
without clock edges does nothing. This drives rst_n low for exactly n rising edges (clock stopped
otherwise), releases it, restarts the clock, and checks FCFG (set to a non-default value beforehand).
RTL and GATES=yes.

Run: make COCOTB_TEST_MODULES=test_reset
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

import test as A

FCFG_RESET = 0x05


class Clk:
    def __init__(self, dut):
        self.dut, self.c = dut, None

    def on(self):
        self.c = Clock(self.dut.clk, 20, unit="ns")
        self.c.start()

    def off(self):
        self.c.stop()
        self.c = None


async def reset_with_edges(dut, clk, n):
    """rst_n low across exactly n rising clk edges; the clock is stopped around it, then restarted."""
    clk.off()
    dut.clk.value = 0
    await Timer(30, "ns")
    dut.rst_n.value = 0
    await Timer(20, "ns")
    for _ in range(n):
        dut.clk.value = 1
        await Timer(10, "ns")
        dut.clk.value = 0
        await Timer(10, "ns")
    dut.rst_n.value = 1
    await Timer(20, "ns")
    clk.on()
    await ClockCycles(dut.clk, 10)
    await FallingEdge(dut.clk)


async def normal_reset(dut):
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_reset_needs_clock_edges(dut):
    dut.ena.value = 1
    dut.uio_in.value = 0
    A._ui["v"] = 0b0010
    dut.ui_in.value = 0b0010
    clk = Clk(dut)
    clk.on()
    await normal_reset(dut)
    assert (await A.fstat(dut))[1] == FCFG_RESET
    results = {}
    for n in (0, 1, 2, 3, 10):
        await A.xfer(dut, [A.OP_FCFG, 0x0A])
        assert (await A.fstat(dut))[1] == 0x0A
        await reset_with_edges(dut, clk, n)
        st = await A.fstat(dut)
        results[n] = st[1] == FCFG_RESET
        dut._log.info(f"rst_n low for {n} clock edges: FCFG {st[1]:#04x} -> reset {'yes' if results[n] else 'NO'}")
        await normal_reset(dut)
    assert results[0] is False, "a reset with no clock edges took effect: this check could not catch it"
    assert results[3] and results[10], results
    dut._log.info(f"minimum edges with rst_n low (clock running afterwards): "
                  f"{min(n for n, ok in results.items() if ok)}; the devkit script holds 10,000")
