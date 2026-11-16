"""
Continuity across year boundaries (each year is downscaled on its own, so a jump at 1 Jan 00:00 would show a
problem in the per-year inputs or caches). Adapted from A. Ionita's meridionali_zarr/scripts/check_year_boundaries.py.
For each boundary y -> y+1 and each variable: the step 31 Dec 23:00 -> 1 Jan 00:00 at every cluster, compared with
the ordinary hour-to-hour steps of 31 Dec (same clusters). A boundary is flagged if its largest step exceeds the
largest ordinary step of 31 Dec by more than a factor 2 and by a meaningful absolute amount (MIN_ABS). Read-only.

    python rila_pirin_zarr/scripts/pipeline/check_year_boundaries.py 1940 2025 [--series v2]
Writes data/logs/check_<series>/year_boundaries.csv; exit 0 = no flagged boundary.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

R = Path(__file__).resolve().parents[2]
RUNS = {'v1': R / 'data' / 'runs', 'v2': R / 'data' / 'runs_v2'}
VARS = ['t', 'q', 'p', 'LW', 'ws', 'SW', 'tp']
MIN_ABS = {'t': 1.0, 'q': 5e-4, 'p': 100.0, 'LW': 20.0, 'ws': 2.0, 'SW': 50.0, 'tp': 1.0}

p = argparse.ArgumentParser()
p.add_argument('y0', type=int)
p.add_argument('y1', type=int)
p.add_argument('--series', default='v2', choices=list(RUNS))
a = p.parse_args()
store = lambda y: RUNS[a.series] / str(y) / 'outputs' / 'downscaled' / 'down.zarr'
rows = []
for y in range(a.y0, a.y1):
    if not ((RUNS[a.series] / str(y) / 'DONE').exists() and (RUNS[a.series] / str(y + 1) / 'DONE').exists()):
        print(f'{y}->{y + 1} skipped (a year not DONE)')
        continue
    da = xr.open_zarr(store(y))[VARS].sel(time=f'{y}-12-31').load()
    db = xr.open_zarr(store(y + 1))[VARS].sel(time=f'{y + 1}-01-01T00:00').load()
    assert (da.point_ind.values == db.point_ind.values).all()
    for v in VARS:
        tax = da[v].dims.index('time')
        step = np.abs(db[v].values - da[v].isel(time=-1).values)                          # per cluster
        ordinary = np.abs(np.diff(da[v].values, axis=tax)).max(axis=tax)                  # per cluster, within 31 Dec
        rows.append(dict(boundary=f'{y}->{y + 1}', var=v, max_step=step.max(), median_step=np.median(step),
                         max_ordinary_31dec=ordinary.max(),
                         n_points_step_gt_2x_ordinary=int(((step > 2 * ordinary) & (step > MIN_ABS[v])).sum())))
df = pd.DataFrame(rows)
out = R / 'data' / 'logs' / f'check_{a.series}'
out.mkdir(parents=True, exist_ok=True)
df.to_csv(out / 'year_boundaries.csv', index=False, float_format='%.4g')
flag = df[(df.max_step > 2 * df.max_ordinary_31dec) & (df.max_step > df['var'].map(MIN_ABS))]
pd.set_option('display.width', 200)
pd.set_option('display.max_rows', 200)
print(df.pivot(index='boundary', columns='var', values='n_points_step_gt_2x_ordinary'))
t = df[df['var'] == 't']
print(f'{len(t)} boundaries; t max step: median {t.max_step.median():.2f} K, max {t.max_step.max():.2f} K '
      f'({t.loc[t.max_step.idxmax(), "boundary"]}); ordinary 31 Dec max median {t.max_ordinary_31dec.median():.2f} K')
print('FLAGGED:\n' + flag.to_string() if len(flag) else 'no boundary flagged')
sys.exit(1 if len(flag) else 0)
