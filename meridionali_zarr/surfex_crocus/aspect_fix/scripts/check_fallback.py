"""
Checks of the per-time-step vertical fallback (commit 0631d84) on real data.

Runs compared (all with the SW fixes; Efix = before 0631d84, Efix2 = with it):
  Efix_2024-09_2024-12, Efix_2025-01_2025-08      whole-period fallback decision
  Efix2_2024-09_2024-12, Efix2_2025-01_2025-08    per-time-step decision
  Efix2_2024-01_2024-12                           per-time-step decision, full year 2024
Checks:
  1. period independence: Efix2 Sep-Dec 2024 alone == Efix2 full-year 2024 sliced to Sep-Dec (all variables, bit-identical)
  2. points with no time step below the lowest level: Efix2 == Efix (all variables, bit-identical)
  3. points with some time steps below: number of time steps below, change of t vs the whole-period decision
  4. no NaN, time axis complete
Writes aspect_fix/checks/fallback_*.csv and fallback_summary.txt; exit 1 if a check fails.

    PYTHONPATH=~/SurfexCrocus/aspect_fix/TopoPyScale_fix python scripts/check_fallback.py
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from TopoPyScale import topo_scale_zarr as tz

FIX = Path(__file__).resolve().parents[1]
D = Path.home() / 'TopoPyScale-repo-github/downscaling/meridionali_zarr/data'
OUT = FIX / 'checks'
VARS = ['t', 'q', 'p', 'u', 'v', 'ws', 'wd', 'LW', 'SW', 'SW_direct', 'SW_diffuse', 'tp']


def st(name, t0=None, t1=None):
    ds = tz.open_downscaled_store(D / name / 'outputs/downscaled/down.zarr')
    return ds.sel(time=slice(t0, t1)) if t0 else ds


def fallback_steps(name):
    """{point_name: number of time steps below the lowest level} from the run log."""
    txt = (FIX / 'logs' / f'downscale_{name}.log').read_text()
    return {m.group(1): int(m.group(2)) for m in
            re.finditer(r'WARNING: Point (\S+) is below the .*? geopotential at (\d+) of \d+ time steps', txt)}


def main():
    L, ok_all = [], True

    def rep(name, ok, txt):
        nonlocal ok_all
        ok_all &= bool(ok)
        L.append(f'[{"PASS" if ok else "FAIL"}] {name}: {txt}')
        print(L[-1], flush=True)

    # 1. period independence
    a = st('meridionali_Efix2_2024-09_2024-12')
    b = st('meridionali_Efix2_2024-01_2024-12', '2024-09-01', '2024-12-31 23:00')
    diffs = {v: float(np.abs(a[v].values - b[v].values).max()) for v in VARS}
    rep('1. period independence (Sep-Dec 2024 alone vs inside full-year 2024)', all(d == 0 for d in diffs.values()),
        ', '.join(f'{v} {d:.1e}' for v, d in diffs.items()))

    # 2./3. per point, both periods
    rows = []
    for old_n, new_n in (('meridionali_Efix_2024-09_2024-12', 'meridionali_Efix2_2024-09_2024-12'),
                         ('meridionali_Efix_2025-01_2025-08', 'meridionali_Efix2_2025-01_2025-08')):
        o, n = st(old_n), st(new_n)
        fb_new, fb_old = fallback_steps(new_n), fallback_steps(old_n)   # old log: format of the former warning
        old_txt = (FIX / 'logs' / f'downscale_{old_n}.log').read_text()
        fb_old_pts = set(re.findall(r'WARNING: Point (\S+) is -?[\d.]+ m lower than', old_txt))
        names = n.point_name.values.astype(str)
        nt = n.sizes['time']
        rep(f'4. {new_n}: complete, no NaN', nt == o.sizes['time'] and
            all(int(n[v].isnull().sum()) == 0 for v in VARS), f'{nt} h')
        never = np.array([p not in fb_new for p in names])
        d_never = {v: float(np.abs(n[v].values[never] - o[v].values[never]).max()) for v in VARS}
        rep(f'2. {new_n}: points never below the lowest level ({never.sum()}) identical to {old_n}',
            all(d == 0 for d in d_never.values()), ', '.join(f'{v} {d:.0e}' for v, d in d_never.items()))
        rep(f'   {new_n}: points with steps below = points in whole-period fallback before',
            set(fb_new) == fb_old_pts, f'{len(fb_new)} now (per step) vs {len(fb_old_pts)} before')
        dt = n.t.values - o.t.values
        for k, p in enumerate(names):
            if p in fb_new:
                rows.append({'period': new_n.split('Efix2_')[1], 'point_name': p, 'steps_total': nt, 'steps_below': fb_new[p],
                             'share_below_pct': round(100 * fb_new[p] / nt, 1),
                             'dt_mean_K': round(float(dt[k].mean()), 3), 'dt_max_abs_K': round(float(np.abs(dt[k]).max()), 2),
                             'steps_changed': int((np.abs(dt[k]) > 1e-9).sum())})
    r = pd.DataFrame(rows)
    df = pd.read_pickle(D / 'meridionali_Efix2_2024-09_2024-12/outputs/df_centroids.pck')
    r = r.merge(pd.DataFrame({'point_name': df.point_name.astype(str), 'elevation': df.elevation.round(0)}), on='point_name')
    r.to_csv(OUT / 'fallback_points.csv', index=False)
    # per point: changed steps must be <= steps not below (only the formerly forced, now interpolated, steps change)
    cons = (r.steps_changed <= r.steps_total - r.steps_below).all()
    rep('3. only time steps above the lowest level changed (changed <= steps not below)', cons,
        f'{len(r)} point-periods')
    s = r.groupby('period').agg(points=('point_name', 'size'), elev_min=('elevation', 'min'),
                                elev_max=('elevation', 'max'), share_below_median=('share_below_pct', 'median'),
                                share_below_max=('share_below_pct', 'max'), dt_mean_median=('dt_mean_K', 'median'),
                                dt_mean_min=('dt_mean_K', 'min'), dt_mean_max=('dt_mean_K', 'max'),
                                dt_max_abs=('dt_max_abs_K', 'max'))
    s.to_csv(OUT / 'fallback_summary_by_period.csv')
    L.append('\n' + s.to_string())
    print(s.to_string())
    (OUT / 'fallback_summary.txt').write_text('\n'.join(L) + '\n')
    print('ALL CHECKS PASSED' if ok_all else 'SOME CHECKS FAILED')
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()
