import sys, pickle
import pandas as pd

raw_path, pkl_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
raw = pd.read_csv(raw_path, parse_dates=['observation_date'])
raw = raw.rename(columns={'observation_date': 'date', 'DTB3': 'rate_pct'})
raw['rate_pct'] = pd.to_numeric(raw['rate_pct'], errors='coerce')
print('raw rows', len(raw), 'blank', int(raw['rate_pct'].isna().sum()),
      'first', raw['date'].min().date(), 'last', raw['date'].max().date())

res = pickle.load(open(pkl_path, 'rb'))
fdr = res['fdr_FRED:DTB3']
r = raw.set_index('date')['rate_pct']
blank_dates = r[r.isna()].index
both = pd.concat([r.rename('raw'), fdr.rename('fdr')], axis=1)
print('FDR values on raw-blank dates (first 5):')
print(both.loc[blank_dates].head(5))
print('ffill(raw) == fdr on all dates?', bool((r.ffill().reindex(fdr.index) - fdr).abs().max() < 1e-9))
nonblank = both.dropna()
print('max abs diff on non-blank dates', float((nonblank.raw - nonblank.fdr).abs().max()))

# compare with yahoo ^IRX
irx = res['yf_^IRX']
irx.index = pd.to_datetime(irx.index).tz_localize(None) if getattr(irx.index, 'tz', None) else pd.to_datetime(irx.index)
j = pd.concat([r.rename('dtb3'), irx.rename('irx')], axis=1).dropna()
d = (j.irx - j.dtb3)
print('IRX - DTB3 on common dates: n', len(j), 'mean', round(d.mean(), 4), 'abs max', round(d.abs().max(), 4))
print('IRX dates not in DTB3 nonblank:', len(set(irx.index) - set(r.dropna().index)))

out = raw.dropna(subset=['rate_pct']).copy()
out['date'] = out['date'].dt.strftime('%Y-%m-%d')
out['source'] = 'FRED DTB3 (fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3), secondary-market 3M T-bill, discount basis, annual %'
out.to_csv(out_path, index=False)
print('saved', len(out), 'rows', out['date'].iloc[0], out['date'].iloc[-1])
