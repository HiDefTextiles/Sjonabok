# Picture sheets for variants.py: consensus figures with their fits, and size variants.
# Usage: python consensus_sheets.py [OUTDIR]  (default work/submotifs)
import sys,csv,numpy as np
sys.path.insert(0,'.')
import subjects as S
from PIL import Image, ImageDraw
BLUE=(16,9,159); PINK=(214,31,105); WH=(255,255,255); INK=(38,38,38)
U={u.id:u for u in S.Corpus('../../patterns/txt',S.PILOT_KINDS+S.BAND_KINDS).units}
Mo={m['submotif']:m for m in csv.DictReader(open('work/submotifs/motifs.csv'))}
C={c['submotif']:c for c in csv.DictReader(open('work/submotifs/consensus.csv'))}
P={}
for p in csv.DictReader(open('work/submotifs/places.csv')): P.setdefault(p['submotif'],[]).append(p)
pieces=list(csv.DictReader(open('work/submotifs/pieces.csv')))
OUTDIR=sys.argv[1] if len(sys.argv)>1 else 'work/submotifs'
W=130
def tile(sheet,dr,rgb,cx,cy,label,col=INK):
    I=Image.fromarray(rgb); z=max(1,(W-10)//max(I.size)); I=I.resize((I.width*z,I.height*z),Image.NEAREST); I.thumbnail((W-10,W-24)); sheet.paste(I,(cx+4,cy+18)); dr.text((cx+4,cy+3),label,fill=col)
def cut(p):
    c=np.asarray(U[p['chart']].cells)[int(p['row']):int(p['row'])+int(p['height']),int(p['col']):int(p['col'])+int(p['width'])]
    return np.where(c[...,None]==1,BLUE,WH).astype('uint8')
def cons(m): return np.asarray(Image.open(f'work/submotifs/consensus/{m}.png').convert('RGB'))
# sheet 1: same 20 as before; columns: first found | consensus | best fits x2 | worst kept | stretch
inner=[];got=set()
for p in pieces:
    m=Mo[p['submotif']]
    if p['how']=='inner' and int(m['cells'])>=40 and int(m['manuscripts'])>=3 and m['generic']=='0' and p['submotif'] not in got:
        inner.append(p); got.add(p['submotif'])
inner=sorted(inner,key=lambda p:-int(Mo[p['submotif']]['charts']))[:20]
cols=6; sh=Image.new('RGB',(cols*W,len(inner)*W+30),WH); dr=ImageDraw.Draw(sh)
for i,t in enumerate(['first found','consensus','fits well','fits well','weakest kept','dropped (stretch)']): dr.text((i*W+4,8),t,fill=BLUE)
for r,p in enumerate(inner):
    m=p['submotif']; y=r*W+30; c=C[m]
    tile(sh,dr,cut(p),0,y,f"#{m}")
    tile(sh,dr,cons(m),W,y,f"fit {c['fit']}, {c['charts']} charts")
    pl=sorted(P[m],key=lambda q:-float(q['fit'])); kept=[q for q in pl if q['kept']=='1']; drop=[q for q in pl if q['kept']=='0']
    for k,q in enumerate(kept[:2]): tile(sh,dr,cut(q),(2+k)*W,y,f"{q['chart'][:16]} {q['fit']}")
    if kept: q=kept[-1]; tile(sh,dr,cut(q),4*W,y,f"{q['chart'][:16]} {q['fit']}")
    if drop: q=drop[0]; tile(sh,dr,cut(q),5*W,y,f"{q['chart'][:16]} {q['fit']}",PINK)
sh.save(OUTDIR+'/consensus-figures.png')
# sheet 2: kinds with several sizes, consensus pictures small to large
K=[k for k in csv.DictReader(open('work/submotifs/kinds.csv')) if '|' in k['submotifs']]
K.sort(key=lambda k:-int(k['charts'])); K=K[:20]
cols=1+max(len(k['submotifs'].split('|')) for k in K); cols=min(cols,8)
sh=Image.new('RGB',(cols*W,len(K)*W),WH); dr=ImageDraw.Draw(sh)
for r,k in enumerate(K):
    ms=sorted(k['submotifs'].split('|'),key=lambda m:int(C[m]['cells']))[:cols-1]
    dr.text((4,r*W+20),f"kind {k['kind']}",fill=BLUE); dr.text((4,r*W+36),f"{len(k['submotifs'].split('|'))} sizes",fill=INK); dr.text((4,r*W+52),f"{k['charts']} charts",fill=INK); dr.text((4,r*W+68),f"{k['smallest']}-{k['largest']} cells",fill=INK)
    for j,m in enumerate(ms): tile(sh,dr,cons(m),(j+1)*W,r*W,f"#{m}: {C[m]['cells']} cells")
sh.save(OUTDIR+'/size-variants.png')
