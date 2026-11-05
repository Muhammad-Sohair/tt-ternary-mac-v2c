# SDF back-annotated gate-level simulation (Icarus 12)

Results and the method's limits: `notes/v2c_06_signoff_evidence.md`.

1. Put the run's netlist here as `gate_level_netlist.v` and its per-corner SDF in `corners/<corner>.sdf`
   (from the LibreLane `56-openroad-stapostpnr/<corner>/` step, or `final/sdf/`).
2. `python patch_lib.py $PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v`
   (ties the timing models' `*_delayed` nets; Icarus does not run timing checks).
3. `python fold_ic.py corners/<c>.sdf corners/<c>_folded.sdf` (Icarus ignores INTERCONNECT).
4. Copy `../*.py` next to this Makefile, then e.g.
   `GATES=yes TMAC_GL_SLOW=1 make CORNER=max_ss_100C_1v60 COCOTB_TEST_MODULES=test_c`.
5. Check the log has no `SDF ERROR` / `SDF WARNING`. `test_sdfprobe` / `test_sdfclk` (needs `flops.txt`, one
   flop instance per line) prove the delays landed.
