# SDF back-annotated gate-level sim of the sign-off netlist (timing cell models, no FUNCTIONAL/UNIT_DELAY)
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
CORNER ?= max_ss_100C_1v60
SIM_BUILD = sim_build/$(CORNER)
SRC_DIR = $(PWD)/../src
COMPILE_ARGS += -gspecify -DGL_TEST -DUSE_POWER_PINS -DSIM
COMPILE_ARGS += -I$(PWD)/sim_build/$(CORNER)
VERILOG_SOURCES += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v
VERILOG_SOURCES += $(PWD)/sky130_fd_sc_hd_sdf.v   # made by patch_lib.py
VERILOG_SOURCES += $(PWD)/gate_level_netlist.v $(PWD)/tb.v
COMPILE_ARGS += -I$(SRC_DIR)
TOPLEVEL = tb
COCOTB_TEST_MODULES ?= test
include $(shell cocotb-config --makefiles)/Makefile.sim
$(SIM_BUILD)/sim.vvp: $(SIM_BUILD)/sdf_path.vh
$(SIM_BUILD)/sdf_path.vh:
	mkdir -p $(SIM_BUILD)
	echo '`define SDF_FILE "$(PWD)/corners/$(CORNER)_folded.sdf"' > $@
