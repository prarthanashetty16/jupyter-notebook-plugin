import sys,json; sys.path.insert(0,'.')
from pathlib import Path
import numpy as np, pandas as pd
from benchmarks.evaluate import load_joined
from benchmarks.suite import build_grid, JoinInput
df=load_joined(Path('benchmarks/results/dev-v5'))
grid={p.id:p for p in build_grid('full',splits=('dev',),max_size=10_000_000)}
a=pd.read_csv('benchmarks/results/dev-v5/actuals.csv').set_index('point_id')
rows=[]
for pid,g in df[df.op=='merge'].groupby('point_id'):
    p=grid.get(pid)
    if p is None or 'how="inner"' not in p.source and 'how=' in p.source: continue
    if 'how="inner"' not in p.source and 'how=' in p.source: continue
    j=p.inputs[0]
    if not (g.tier==1).any(): continue
    t1=g[g.tier==1].iloc[0]
    if t1.ram_class!='valid': continue
    f=json.loads(t1.features)
    nl=p.size; nr=j.right_rows
    true=int(a.loc[pid,'out_rows'])
    est=f.get('out_rows',[0,0,0])[1] if f.get('out_rows_source')=='tier1' else float('nan')
    rows.append(dict(point=pid,nl=nl,nr=nr,overlap=j.overlap,fanout=j.fanout,dist=j.right_key_dist,true_rows=true,est_rows=est,row_err=est/true,
        ram_actual=t1.ram_value/2**20,exp=t1.ram_expected/2**20,fold=t1.ram_expected/t1.ram_value,M_over_nl=true/nl,M_over_in=true/(nl+nr),unique=f.get('right_unique'),elided=f.get('left_elided')))
t=pd.DataFrame(rows).sort_values('fold')
pd.set_option('display.width',250)
print(t.drop(columns=['dist']).round(2).to_string(index=False))
t.to_csv('/tmp/merge_inner.csv',index=False)
