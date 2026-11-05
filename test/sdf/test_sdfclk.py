"""Clock insertion delay to every flop CLK pin in the SDF sim (compare with STA clock latency)."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.utils import get_sim_time

@cocotb.test()
async def sdf_clk(dut):
    dut.ena.value = 1; dut.ui_in.value = 0; dut.uio_in.value = 0; dut.rst_n.value = 0; dut.clk.value = 0
    await Timer(100, "ns")
    names = open("flops.txt", encoding="ascii").read().split()
    t = {}
    async def w(n):
        await RisingEdge(dut.user_project._id(n, extended=False).CLK); t[n] = get_sim_time("ps") - t0[0]
    t0 = [0]
    for n in names: cocotb.start_soon(w(n))
    await Timer(20, "ns"); t0[0] = get_sim_time("ps"); dut.clk.value = 1
    await Timer(10, "ns")
    v = sorted(t.values())
    for n in ("_8004_", "_7931_"): dut._log.info(f"{n} rise insertion {t[n]/1000:.3f} ns")
    dut._log.info(f"flops {len(v)}/{len(names)}: insertion min {v[0]/1000:.3f} max {v[-1]/1000:.3f} skew {(v[-1]-v[0])/1000:.3f} ns")
