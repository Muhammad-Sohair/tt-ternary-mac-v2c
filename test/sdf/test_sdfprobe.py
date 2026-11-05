"""Proves what of the SDF is annotated: times of clk, clkbuf_0_clk.A, .X edges, watched concurrently."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer
from cocotb.utils import get_sim_time

async def watch(sig, name, log, out):
    for _ in range(3):
        await RisingEdge(sig); out.append((get_sim_time("ps"), name))

@cocotb.test()
async def sdf_probe(dut):
    dut.ena.value = 1; dut.ui_in.value = 0; dut.uio_in.value = 0; dut.rst_n.value = 0
    dut.clk.value = 0
    await Timer(100, "ns")
    cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
    cb = dut.user_project.clkbuf_0_clk
    ev = []
    for s, n in ((dut.clk, "clk"), (cb.A, "A"), (cb.X, "X"), (dut.user_project.clkbuf_1_0_0_clk.A, "L1.A")):
        cocotb.start_soon(watch(s, n, dut._log, ev))
    await Timer(70, "ns")
    for t, n in sorted(ev): dut._log.info(f"{t/1000:.3f} ns  {n}")
