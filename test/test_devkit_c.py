# SPDX-License-Identifier: Apache-2.0
"""Runs the board script's RAM stages (devkit/tmac_bringup.py run_ram: R1-R3), unmodified, against
the RTL, as test_devkit.py does for the S and F stages. The fake board is test_devkit.FakeTT; with
project 0 selected the script programs the flash through the bit-level W25Q model, and with TMAC2C
selected the chip talks to the strict shared-bus model of test_c.PmodBus (A's flash protocol checks,
the APS6404L engine with datasheet timing, one device selected at a time). Both share one flash image.

Run: mingw32-make COCOTB_TEST_MODULES=test_devkit_c   (RTL only)
"""

import cocotb
from cocotb.task import bridge

import test_devkit as TD
from test_c import PmodBus
from tmac_model import pack_matrix, COLS, ROWS

B = TD.B


@cocotb.test()
async def test_devkit_ram_stages(dut):
    """R1 (ASTAT 0x00, AINIT -> 0x40), R2 (activations 1..5 from RAM: row 0 = 15), R3 (random ARUN
    matvecs at /8 and /4, bit-exact) on the RTL, with every RAM datasheet rule asserted."""
    dut.ui_in.value = 0b0010
    dut.uio_in.value = 0
    dut.ena.value = 0
    dut.rst_n.value = 0
    mem = {}
    w25q = TD.W25Q(mem, qe=True)
    tt = TD.FakeTT(dut, w25q)
    B.time = TD.FakeTime(tt)
    bus = PmodBus(dut, {})
    bus.image = mem                                      # the chip reads what the script programmed

    def run():
        W = [[1] * COLS] + [[0] * COLS for _ in range(ROWS - 1)]
        B.flash_board(tt)
        B.fl_write(tt, B.FLASH_PAGE << 8, pack_matrix(W))    # F2's image, which R2 reuses
        B.flash_chip(tt)
        return B.run_ram(tt)

    out = await bridge(run)()
    dut._log.info(f"R stages: {out}")
    assert out == {"R1": True, "R2": True, "R3": True}, out
    assert bus.ram.log[:2] == [0x66, 0x99], bus.ram.log[:4]
    assert not w25q.errors, w25q.errors[:5]
    assert not tt.errors, tt.errors[:5]
    bus.check("devkit R stages")
