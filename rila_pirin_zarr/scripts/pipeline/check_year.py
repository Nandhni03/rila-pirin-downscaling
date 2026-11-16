"""
Checks one downscaled NCAR year, and compares it with the first series (v1) when both exist. Read-only.
Adapted from A. Ionita's meridionali_zarr/scripts/check_year_fixed.py (aspect-fix rerun, 11 Nov 2026).

    python rila_pirin_zarr/scripts/pipeline/check_year.py 2024 [--series v2]
Checks (exit 0 = all pass):
  1. 12/12 months 'ok' in outputs/months/*.json (run_year's own hourly QA + daily statistics)
  2. time axis: every hour of the year, no duplicates, no gaps
  3. no NaN in any variable
  4. Dec-Feb mean SW per elevation class x aspect sector (circular cluster aspect, slope >= 5 deg):
     S > E, S > W, E > N, W > N in every class (physical order at 42 N)
  5. SW_direct max < 1400 W m-2 (no spikes above the solar constant)
Reported, not pass/fail: E-W balance in DJF ((W - E) / mean of E and W per class), and against v1 (data/runs):
  t difference (mean, max |dt|, clusters with any change), SW difference per sector.
Aspect convention (verified 2026-11-15, LOG.md): TopoPyScale aspect 0 = south, + towards east; bearing = 180 - aspect.
Writes data/logs/check_<series>/check_<year>.txt and sw_djf_<year>.csv; prints one SUMMARY line.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

R = Path(__file__).resolve().parents[2]
RUNS = {'v1': R / 'data' / 'runs', 'v2': R / 'data' / 'runs_v2'}
CLASSES = [-np.inf, 1000, 1500, 2000, np.inf]
CLABELS = ['<1000', '1000-1500', '1500-2000', '>2000']


def sectors(c):
    bearing = (180.0 - np.degrees(c.aspect.values)) % 360.0
    s = np.where((bearing >= 315) | (bearing < 45), 'N', np.where(bearing < 135, 'E', np.where(bearing < 225, 'S', 'W')))
    return np.where(np.degrees(c.slope.values) < 5, 'flat', s)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('year', type=int)
    p.add_argument('--series', default='v2', choices=list(RUNS))
    a = p.parse_args()
    y = a.year
    out = RUNS[a.series] / str(y) / 'outputs'
    logd = R / 'data' / 'logs' / f'check_{a.series}'
    logd.mkdir(parents=True, exist_ok=True)
    lines, ok = [], True

    def rep(name, passed, txt):
        nonlocal ok
        if passed is not None:
            ok &= bool(passed)
        tag = 'INFO' if passed is None else ('PASS' if passed else 'FAIL')
        lines.append(f'{tag}  {name}: {txt}')

    st = [json.loads(f.read_text()).get('status', '') for f in sorted((out / 'months').glob('*.json'))]
    n_ok = sum(1 for s in st if str(s).startswith('ok'))
    rep('months ok', n_ok == 12, f'{n_ok}/12')

    ds = xr.open_zarr(out / 'downscaled' / 'down.zarr')
    t = pd.DatetimeIndex(ds.time.values)
    exp = pd.date_range(f'{y}-01-01 00:00', f'{y}-12-31 23:00', freq='h')
    rep('time axis', len(t) == len(exp) and bool((t == exp).all()),
        f'{len(t)} h (expected {len(exp)}), duplicates {int(t.duplicated().sum())}')

    nan = {v: int(ds[v].isnull().sum().compute()) for v in ds.data_vars}
    bad = {k: v for k, v in nan.items() if v}
    rep('no NaN', not bad, f'all {len(nan)} variables' if not bad else str(bad))

    c = pd.read_pickle(out / 'df_centroids.pck').sort_values('point_ind')
    assert (c.point_ind.values == ds.point_ind.values).all()
    sec = sectors(c)
    elev = pd.cut(c.elevation.values, CLASSES, labels=CLABELS)
    djf_sel = ds.time.dt.month.isin([1, 2, 12])
    djf = ds.SW.sel(time=djf_sel).mean('time').compute().values
    tab = (pd.DataFrame({'elev': elev, 'sector': sec, 'SW': djf}).query('sector != "flat"')
           .groupby(['elev', 'sector'], observed=True).SW.median().unstack()[['N', 'E', 'S', 'W']])
    tab.round(1).to_csv(logd / f'sw_djf_{y}.csv')
    order = bool(((tab.S > tab.E) & (tab.S > tab.W) & (tab.E > tab.N) & (tab.W > tab.N)).all())
    rep('DJF SW order S > E,W > N', order,
        ' | '.join(f'{i}: N {r.N:.0f} E {r.E:.0f} S {r.S:.0f} W {r.W:.0f}' for i, r in tab.iterrows()))
    ew = ((tab.W - tab.E) / ((tab.W + tab.E) / 2) * 100)
    rep('DJF (W-E)/mean', None, ' | '.join(f'{i}: {v:+.0f} %' for i, v in ew.items()))

    swmax = float(ds.SW_direct.max().compute())
    rep('SW_direct max', swmax < 1400, f'{swmax:.0f} W m-2')

    oy = RUNS['v1' if a.series == 'v2' else 'v2'] / str(y)
    other = oy / 'outputs' / 'downscaled' / 'down.zarr'
    if (oy / 'DONE').exists():                       # only a finished year of the other series
        o = xr.open_zarr(other)
        dt = (ds.t - o.t).compute()
        changed = int((np.abs(dt) > 1e-4).any('time').sum())
        rep(f't minus {"v1" if a.series == "v2" else "v2"}', None,
            f'mean {float(dt.mean()):+.3f} K, max |dt| {float(np.abs(dt).max()):.2f} K, clusters changed {changed}/'
            f'{dt.sizes["point_ind"]}' + (f' (elevation {c.elevation.values[(np.abs(dt) > 1e-4).any("time").values].min():.0f}-'
                                          f'{c.elevation.values[(np.abs(dt) > 1e-4).any("time").values].max():.0f} m)'
                                          if changed else ''))
        dsw = (ds.SW.sel(time=djf_sel).mean('time') - o.SW.sel(time=djf_sel).mean('time')).compute().values
        d = pd.DataFrame({'sector': sec, 'dSW': dsw}).groupby('sector').dSW.median()
        rep('DJF SW minus other', None, ' | '.join(f'{k} {v:+.1f}' for k, v in d.items()) + ' W m-2 (median per sector)')
        rep('SW_direct max other', None, f'{float(o.SW_direct.max().compute()):.0f} W m-2')

    (logd / f'check_{y}.txt').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print(f'SUMMARY {a.series} {y} {"ALL PASS" if ok else "FAILED"}; DJF SW S {tab.S.min():.0f}-{tab.S.max():.0f}, '
          f'N {tab.N.min():.0f}-{tab.N.max():.0f} W m-2; SW_direct max {swmax:.0f}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
