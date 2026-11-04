import sys
import pandas as pd
import FinanceDataReader as fdr

raw_dir, out_path = sys.argv[1], sys.argv[2]
for sid in ['IR3TIB01KRM156N', 'IRSTCI01KRM156N']:
    try:
        df = fdr.DataReader(f'FRED:{sid}', '2014-06-01', '2026-11-03')
        s = df.iloc[:, 0]
        print(f'FDR FRED:{sid}: rows={len(s)} first={s.index.min().date()} last={s.index.max().date()} nan={int(s.isna().sum())}')
    except Exception as e:
        print(f'FDR FRED:{sid} FAILED: {e!r}')
    raw = pd.read_csv(f'{raw_dir}/{sid}.csv', parse_dates=['observation_date'])
    raw[sid] = pd.to_numeric(raw[sid], errors='coerce')
    r = raw.set_index('observation_date')[sid]
    print(f'  raw: rows={len(r)} first={r.index.min().date()} last={r.index.max().date()} nan={int(r.isna().sum())} min={r.min()} max={r.max()}')
    for p in ['2015-01', '2020-06', '2023-10', '2025-12', '2026-09']:
        v = r.loc[p]
        print(f'   {p}: {v.iloc[0] if len(v) else "NA"}')

sid = 'IR3TIB01KRM156N'
raw = pd.read_csv(f'{raw_dir}/{sid}.csv', parse_dates=['observation_date'])
raw['rate_pct'] = pd.to_numeric(raw[sid], errors='coerce')
out = raw.dropna(subset=['rate_pct'])[['observation_date', 'rate_pct']].rename(columns={'observation_date': 'date'})
out['date'] = out['date'].dt.strftime('%Y-%m-%d')
out['source'] = 'FRED IR3TIB01KRM156N (OECD MEI, Korea 3-month interbank rate, monthly average, annual %)'
out['frequency'] = 'monthly'
out.to_csv(out_path, index=False)
print('saved', len(out), out['date'].iloc[0], out['date'].iloc[-1])
