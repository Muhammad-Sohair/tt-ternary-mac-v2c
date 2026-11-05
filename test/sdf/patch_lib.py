"""Make the sky130_fd_sc_hd timing models usable in Icarus 12 SDF simulation.
Icarus does not evaluate timing checks, so the X_delayed nets that $setuphold/$recrem would drive stay
undriven and every flop is dead. Each `wire X_delayed;` becomes `wire X_delayed = X;` (zero extra delay).
Setup/hold/recovery/removal checking therefore stays with STA (all 9 corners, signed off).
usage: python patch_lib.py $PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v"""
import re, sys
s = open(sys.argv[1]).read()
pat = re.compile(r'wire(\s+)(\w+?)_delayed(\s*);')
n = len(pat.findall(s))
open('sky130_fd_sc_hd_sdf.v', 'w').write(pat.sub(lambda m: f'wire{m.group(1)}{m.group(2)}_delayed = {m.group(2)}{m.group(3)};', s))
print('patched', n, 'delayed nets')
