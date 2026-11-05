"""Fold SDF INTERCONNECT delays (ignored by Icarus 12) into the load cell's IOPATH delays.
Rise/fall mapping by arc unateness; non-unate arcs get max(r,f) on both edges. Pins with no
IOPATH from them (flop D) cannot be folded: reported as the residual bound."""
import re,sys,collections
src,dst=sys.argv[1],sys.argv[2]
s=open(src).read()
ic=collections.defaultdict(lambda:None); drv={}
for a,b,r,f in re.findall(r'\(INTERCONNECT (\S+) (\S+) \(([\d.]+):[\d.:]+\) \(([\d.]+):[\d.:]+\)\)',s):
    if '.' not in b:   # load is a top-level output port: fold into the driver's output arcs (exact)
        di,dp=a.rsplit('.',1); drv[(di,dp)]=(float(r),float(f)); continue
    inst,pin=b.rsplit('.',1); ic[(inst,pin)]=(float(r),float(f))
NEG=re.compile(r'__(inv|clkinv|clkinvlp|bufinv|nand\d|nor\d|nand\db|nor\db|\w+oi|\w+ai)_\d+$')
def unate(ct,pin,out):
    if re.search(r'__(xor|xnor)',ct) or (re.search(r'__mux',ct) and pin.startswith('S')): return 0
    if 'df' in ct: return 'clk' if pin=='CLK' else 'rst'
    neg=bool(NEG.search(ct)); 
    if pin.endswith('_N'): neg=not neg
    return -1 if neg else 1
used=set(); dused=set(); err=0.0; out=[]
cur_inst=cur_ct=None
for line in s.split('\n'):
    m=re.search(r'\(CELLTYPE "(\w+)"\)',line)
    if m: cur_ct=m.group(1)
    m=re.search(r'\(INSTANCE ([^)]*)\)',line)
    if m: cur_inst=m.group(1)
    if 'INTERCONNECT' in line: continue
    m=re.match(r'(\s*\(IOPATH (\S+) (\S+) )\(([\d.]+):[\d.:]+\) \(([\d.]+):[\d.:]+\)\)',line)
    if m and ic[(cur_inst,m.group(2))]:
        r,f=ic[(cur_inst,m.group(2))]; used.add((cur_inst,m.group(2)))
        orr,off=float(m.group(4)),float(m.group(5)); u=unate(cur_ct,m.group(2),m.group(3))
        if u==1: dr,df=r,f
        elif u==-1: dr,df=f,r
        elif u=='clk': dr=df=r
        elif u=='rst': dr=df=f
        else: dr=df=max(r,f); err=max(err,abs(r-f))
        nr,nf=orr+dr,off+df
        line=f'{m.group(1)}({nr:.3f}:{nr:.3f}:{nr:.3f}) ({nf:.3f}:{nf:.3f}:{nf:.3f}))'
    m=re.match(r'(\s*\(IOPATH (\S+) (\S+) )\(([\d.]+):[\d.:]+\) \(([\d.]+):[\d.:]+\)\)',line)
    if m and (cur_inst,m.group(3)) in drv:
        r,f=drv[(cur_inst,m.group(3))]; nr,nf=float(m.group(4))+r,float(m.group(5))+f; dused.add((cur_inst,m.group(3)))
        line=f'{m.group(1)}({nr:.3f}:{nr:.3f}:{nr:.3f}) ({nf:.3f}:{nf:.3f}:{nf:.3f}))'
    out.append(line)
txt='\n'.join(out)
# the top-level cell held only INTERCONNECTs: drop its now-empty block (an empty ABSOLUTE is an SDF syntax error)
txt,k=re.subn(r'\s*\(CELL\s*\(CELLTYPE "tt_um_\w+"\)\s*\(INSTANCE\)\s*\(DELAY\s*\(ABSOLUTE\s*\)\s*\)\s*\)','',txt)
assert k==1, k
open(dst,'w').write(txt)
left=[(k,v) for k,v in ic.items() if v and k not in used]
pins=collections.Counter(k[1] for k,v in left)
print(f'{src}: folded {len(used)} load pins + {len(dused)}/{len(drv)} output-port wires; non-unate max |r-f| error {err:.3f} ns; unfoldable {len(left)} pins {dict(pins)}, max delay {max(max(v) for k,v in left):.3f} ns')
