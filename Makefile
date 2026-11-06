SIM ?= icarus
TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(CURDIR)/sync_fifo.sv
COMPILE_ARGS += -g2012

COCOTB_TOPLEVEL = sync_fifo
COCOTB_TEST_MODULES = test_sync_fifo

include $(shell cocotb-config --makefiles)/Makefile.sim