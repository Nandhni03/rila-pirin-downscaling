"""
Continuity across year boundaries of the re-downscaled setup-E stores (aspect-fix rerun, 11 Nov 2026).
For each boundary y -> y+1 and each variable: the step 31 Dec 23:00 -> 1 Jan 00:00 at every point, compared with
the ordinary hour-to-hour steps of the last day of December (same points). A boundary is flagged if its largest step
exceeds the largest ordinary step of 31 Dec by more than a factor 2 (and by a meaningful absolute amount).
    ../venv/bin/python meridionali_zarr/scripts/check_year_boundaries.py 2011 2025
Writes data/logs/rerun_fix/year_boundaries.csv; exit 0 = no flagged boundary.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

y0, y1 = int(sys.argv[1]), int(sys.argv[2])
D = Path(__file__).resolve().parents[1] / 'data'
VARS = ['t', 'q', 'p', 'LW', 'ws', 'SW', 'tp']
MIN_ABS = {'t': 1.0, 'q': 5e-4, 'p': 100.0, 'LW': 20.0, 'ws': 2.0, 'SW': 50.0, 'tp': 1.0}
rows = []
for y in range(y0, y1):
    a = xr.open_zarr(D / f'meridionali_E_{y}/outputs/downscaled/down.zarr')[VARS].sel(time=f'{y}-12-31')
    b = xr.open_zarr(D / f'meridionali_E_{y + 1}/outputs/downscaled/down.zarr')[VARS].sel(time=f'{y + 1}-01-01T00:00')
    a, b = a.load(), b.load()
    for v in VARS:
        step = np.abs(b[v].values - a[v].isel(time=-1).values)                       # per point
        ordinary = np.abs(np.diff(a[v].values, axis=1)).max(axis=1)                 # per point, within 31 Dec
        rows.append(dict(boundary=f'{y}->{y + 1}', var=v, max_step=step.max(), median_step=np.median(step),
                         max_ordinary_31dec=ordinary.max(),
                         n_points_step_gt_2x_ordinary=int(((step > 2 * ordinary) & (step > MIN_ABS[v])).sum())))
df = pd.DataFrame(rows)
df.to_csv(D / 'logs/rerun_fix/year_boundaries.csv', index=False, float_format='%.4g')
flag = df[(df.max_step > 2 * df.max_ordinary_31dec) & (df.max_step > df['var'].map(MIN_ABS))]
pd.set_option('display.width', 200)
print(df.pivot(index='boundary', columns='var', values='n_points_step_gt_2x_ordinary'))
print('t max step per boundary (K):', ' '.join(f'{r.boundary} {r.max_step:.2f}' for r in df[df['var'] == 't'].itertuples()))
print('FLAGGED:' if len(flag) else 'no boundary flagged', '' if not len(flag) else '\n' + flag.to_string())
sys.exit(1 if len(flag) else 0)
