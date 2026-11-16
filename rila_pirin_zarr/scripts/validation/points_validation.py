"""
Point validation the way the TopoPyScale authors do it (Finse example: sampling method 'points' at the stations,
then topo_compare.obs_vs_downscaled), NCAR series, on the station point runs of points_setup.py.

A2  Authors' figures per station: observation vs downscaled, hourly 2D histogram with 1:1 line, regression
    (obs = a + b * model, their orientation) and a box N / regression / r / RMSE / bias; under it the time series
    of the daily mean and the difference with its 30-day mean. ERA5 + lapse rate is shown beside TopoSCALE in the
    same form, so the figure also shows what the downscaling adds.
    NOTE: topo_compare.correct_trend computes RMSE = sqrt(sum(obs - model)**2 / n) = |sum of errors| / sqrt(n),
    which is not an RMSE (and its bias is obs - model). Here RMSE = sqrt(mean((model - obs)**2)) and
    bias = model - obs, as in all our tables.
A3  The authors' corrections (topo_compare.correct_trend + correct_seasonal: linear regression obs ~ model, then
    the day-of-year median of the remaining difference, 31-day cyclic running mean), but fitted on one period and
    scored on another (they fit and score on the same data, which is calibration, not validation). Contiguous
    blocks, not a random 80/20 split: neighbouring hours/days are strongly correlated, a random split leaks.
      Musala, Sandanski: always FIT ON THE RELIABLE PERIOD 1980-2025 (ERA5 with satellite data from 1979; dense
        hourly station records: Musala ~26-29k h per decade from the 1980s vs 10-19k before), test block by block:
          a decade inside 1980-2025 -> fit on 1980-2025 without that decade (leave one decade out);
          1959-1969, 1970-1979     -> fit on all of 1980-2025 (tests the transfer to the older, sparser era,
                                      which is how a correction would be applied to 1940-1979).
      METER.AC (2018-2025): leave one year out.
    The same correction is also fitted to ERA5 + lapse, so the comparison stays fair.

Inputs: data/validation/<series>/matched_hourly.parquet (station_compare.py: the observation hours), ERA5 t2m
(era5_baseline.era5_year), data/points/runs[_edh]/<YYYY>/outputs/downscaled/down.zarr.

    python rila_pirin_zarr/scripts/validation/points_validation.py [--series ncar ncar_v2] [--no-correction]
(--series ncar_v2 uses the v2 point runs; observations and ERA5 are the same, read from validation/ncar)
Output data/validation/<series>/points/: points_stats.csv, obs_vs_down_<name>_<id>.png, points_rmse.png,
correction_cv.csv, correction_cv_summary.csv, correction_cv.png
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from scipy import stats as sst  # noqa: E402

from era5_baseline import era5_year, LAPSE, LONG  # noqa: E402
from station_compare import daily_from_matched  # noqa: E402

R = Path(__file__).resolve().parents[2]
VAL = R / 'data' / 'validation'
RUNS = {'ncar': R / 'data' / 'points' / 'runs',           # v1: fork tag rila-pirin-ncar-v1
        'ncar_v2': R / 'data' / 'points' / 'runs_v2'}     # v2: fork branch integrate-fixes (LOG.md 2026-11-15)
VERS = ['era5_lapse', 'ts_point']
LAB = {'era5_lapse': 'ERA5 + lapse -6.5 K/km', 'ts_point': 'TopoSCALE at the station point',
       'era5_lapse_cor': 'ERA5 + lapse, corrected', 'ts_point_cor': 'TopoSCALE point, corrected'}
COL = {'era5_lapse': '#e08a2c', 'ts_point': '#2a9d5c', 'era5_lapse_cor': '#f2c48d', 'ts_point_cor': '#8fd1a9'}
BLOCKS = [(1959, 1969), (1970, 1979), (1980, 1989), (1990, 1999), (2000, 2009), (2010, 2019), (2020, 2025)]
RELIABLE = 1980      # fit only on 1980-2025 (see A3 above)


# ---------------------------------------------------------------- data
def points_hourly(series, sids):
    out = []
    for d in sorted(RUNS[series].glob('[0-9][0-9][0-9][0-9]')):
        z = d / 'outputs' / 'downscaled' / 'down.zarr'
        if not z.exists() or len(list((d / 'outputs' / 'months').glob('*.json'))) < 12:
            continue
        t = xr.open_zarr(z).t.load()
        df = pd.DataFrame(t.transpose('time', 'point_ind').values - 273.15, index=pd.DatetimeIndex(t.time.values),
                          columns=t.point_name.values.astype(str))
        df = df[[c for c in df.columns if c in set(sids)]]
        out.append(df.rename_axis('time').reset_index().melt('time', var_name='id', value_name='ts_point'))
    return pd.concat(out, ignore_index=True)


def load(series, st):
    h = pd.read_parquet(VAL / series.split('_')[0] / 'matched_hourly.parquet', columns=['id', 'time', 'o'])
    pt = points_hourly(series, sorted(h.id.unique()))
    h = h.merge(pt, on=['id', 'time'], how='inner')
    sids = sorted(h.id.unique())
    lat = xr.DataArray(st.loc[sids, 'lat'].values, dims='s')
    lon = xr.DataArray(st.loc[sids, 'lon'].values, dims='s')
    zst = xr.DataArray(st.loc[sids, 'elev'].values, dims='s')
    parts = []
    for y in sorted(h.time.dt.year.unique()):
        _, tb, ob, _ = era5_year(y, lat, lon)
        lap = (tb + LAPSE * (zst - ob)).transpose('time', 's')
        idx = pd.DatetimeIndex(lap.time.values)
        for i, sid in enumerate(sids):
            parts.append(pd.DataFrame({'id': sid, 'time': idx, 'era5_lapse': lap.isel(s=i).values}))
        print(f'{series} {y}: ERA5 read', flush=True)
    return h.merge(pd.concat(parts, ignore_index=True), on=['id', 'time'], how='inner').dropna()


def daily(h, vers):
    q = h.set_index('time')
    parts = [daily_from_matched(q.o, q[v])[['o_mean', 'o_max', 'o_min', 'm_mean', 'm_max', 'm_min']]
             .rename(columns={'m_mean': f'{v}_mean', 'm_max': f'{v}_max', 'm_min': f'{v}_min'}) for v in vers]
    return parts[0].join([p.drop(columns=['o_mean', 'o_max', 'o_min']) for p in parts[1:]])


def metrics(o, m):
    o, m = np.asarray(o, float), np.asarray(m, float)
    e = m - o
    reg = sst.linregress(m, o)              # obs = a + b * model (topo_compare orientation)
    return dict(n=len(o), bias=e.mean(), mae=np.abs(e).mean(), rmse=np.sqrt((e ** 2).mean()), r=reg.rvalue,
                slope=reg.slope, intercept=reg.intercept)


# ---------------------------------------------------------------- A2
def station_figure(h, d, sid, name, tag, out):
    fig = plt.figure(figsize=(12, 9.5))
    gs = fig.add_gridspec(3, 2, height_ratios=[2.2, 1.3, 1], hspace=0.35)
    lo, hi = np.floor(h.o.min() / 5) * 5, np.ceil(h.o.max() / 5) * 5
    for k, v in enumerate(VERS):
        ax = fig.add_subplot(gs[0, k])
        ax.hist2d(h[v], h.o, bins=120, range=[[lo, hi], [lo, hi]], cmap='magma_r', cmin=1)
        mt = metrics(h.o, h[v])
        ax.plot([lo, hi], [lo, hi], c='b', lw=1.5, label='1:1 line')
        ax.plot([lo, hi], mt['intercept'] + mt['slope'] * np.array([lo, hi]), c='r', lw=1.5, label='regression')
        ax.text(0.03, 0.97, f"N = {mt['n']}\ny = {mt['intercept']:.2f} + {mt['slope']:.2f}x\nr = {mt['r']:.3f}\n"
                f"RMSE = {mt['rmse']:.2f} K\nbias (model-obs) = {mt['bias']:+.2f} K", transform=ax.transAxes,
                va='top', fontsize=9, bbox=dict(boxstyle='round', fc='white', ec='0.8'))
        ax.set(xlim=(lo, hi), ylim=(lo, hi), xlabel=f'{LAB[v]} [°C]', ylabel='Observation [°C]',
               title=f'hourly, {LAB[v]}')
        ax.legend(loc='lower right', fontsize=8)
        ax.set_aspect('equal')
    ax = fig.add_subplot(gs[1, :])
    d = d.copy()
    d.index = pd.to_datetime(d.index)
    d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq='D'))     # gaps -> NaN: lines break there
    ix = d.index
    ax.plot(ix, d.o_mean, lw=0.4, c='k', label='Observation')
    ax.plot(ix, d.ts_point_mean, lw=0.4, c=COL['ts_point'], alpha=0.8, label=LAB['ts_point'])
    ax.set(ylabel='daily mean [°C]')
    ax.legend(loc='upper left', fontsize=8, ncol=2)
    ax2 = fig.add_subplot(gs[2, :], sharex=ax)
    for v in VERS:
        dif = pd.Series((d[f'{v}_mean'] - d.o_mean).values, index=ix)
        ax2.plot(ix, dif.rolling('30D').mean(), lw=1, c=COL[v], label=f'{LAB[v]}: 30-day mean')
    ax2.axhline(0, c='k', lw=0.6)
    ax2.set(ylabel='model - obs [K]', ylim=(-5, 5))
    ax2.legend(loc='lower left', fontsize=8, ncol=2)
    fig.suptitle(f'{name}: observation vs downscaled ({tag})', y=0.995)
    fig.savefig(out, dpi=110, bbox_inches='tight')
    plt.close(fig)


def rmse_figure(t, st, tag, out):
    q = t[(t['var'] == 't_mean')].set_index(['id', 'period', 'version'])
    rows = sorted({(i, p) for i, p, _ in q.index}, key=lambda x: (-st.loc[x[0], 'elev'], x[1]))
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(8, 0.35 * len(rows) + 1.5))
    for i, v in enumerate(VERS):
        ax.barh(y + (i - 0.5) * 0.4, [q.loc[(s, p, v), 'rmse'] for s, p in rows], height=0.4, color=COL[v], label=LAB[v])
    ax.set_yticks(y, [f'{st.loc[s, "name"]} ({st.loc[s, "elev"]:.0f} m) {p}' for s, p in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set(xlabel='RMSE of daily mean [K]', title=f'Point runs vs ERA5 + lapse ({tag})')
    ax.legend(fontsize=8)
    fig.savefig(out, dpi=110, bbox_inches='tight')
    plt.close(fig)


# ---------------------------------------------------------------- A3
def fit_correction(tr, v):
    """Authors' trend + seasonal correction, fitted on tr. Returns a function model -> corrected."""
    reg = sst.linregress(tr[v], tr.o)
    cor = reg.intercept + reg.slope * tr[v]
    doy = tr.time.dt.dayofyear
    se = (tr.o - cor).groupby(doy).median().reindex(range(1, 367)).interpolate(limit_direction='both')
    se = pd.concat([se.iloc[-15:], se, se.iloc[:15]]).rolling(31, center=True).mean().iloc[15:15 + 366]
    se.index = range(1, 367)

    def apply(te):
        return reg.intercept + reg.slope * te[v] + se.reindex(te.time.dt.dayofyear).values
    return apply


def folds(hs, sid):
    if sid in LONG:
        yr = hs.time.dt.year
        for a, b in BLOCKS:
            te = yr.between(a, b)
            tr = (yr >= RELIABLE) & ~te
            if te.sum() > 2000 and tr.sum() > 2000:
                scheme = ('fit 1980-2025, test older decade' if b < RELIABLE else
                          'fit 1980-2025, leave one decade out')
                yield f'test {a}-{b}', scheme, tr, te
    else:
        for y in sorted(hs.time.dt.year.unique()):
            te = hs.time.dt.year == y
            if te.sum() > 2000 and (~te).sum() > 2000:
                yield f'out {y}', 'leave-one-year-out', ~te, te


def correction_cv(h, st):
    rows = []
    for sid, hs in h.groupby('id'):
        hs = hs.reset_index(drop=True)
        for fold, scheme, trm, tem in folds(hs, sid):
            tr, te = hs[trm], hs[tem].copy()
            for v in VERS:
                te[f'{v}_cor'] = fit_correction(tr, v)(te)
            vv = VERS + [f'{v}_cor' for v in VERS]
            dd = daily(te, vv)
            for v in vv:
                rows.append(dict(id=sid, name=st.loc[sid, 'name'], elev=st.loc[sid, 'elev'], scheme=scheme, fold=fold,
                                 version=v, n_train_h=int(trm.sum()), n_test_h=int(tem.sum()),
                                 rmse_hourly=metrics(te.o, te[v])['rmse'], bias_hourly=(te[v] - te.o).mean(),
                                 rmse_t_mean=metrics(dd.o_mean, dd[f'{v}_mean'])['rmse'],
                                 rmse_t_max=metrics(dd.o_max, dd[f'{v}_max'])['rmse'],
                                 rmse_t_min=metrics(dd.o_min, dd[f'{v}_min'])['rmse']))
        print(f'  correction CV {st.loc[sid, "name"]}: done', flush=True)
    return pd.DataFrame(rows)


def cv_figure(s, st, tag, out):
    order = ['era5_lapse', 'era5_lapse_cor', 'ts_point', 'ts_point_cor']
    q = s.set_index(['id', 'scheme', 'version'])
    rows = sorted({(i, sc) for i, sc, _ in q.index}, key=lambda x: (-st.loc[x[0], 'elev'], x[1]))
    y = np.arange(len(rows))
    w = 0.2
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(rows) + 1.6))
    for i, v in enumerate(order):
        ax.barh(y + (i - 1.5) * w, [q.loc[(r[0], r[1], v), 'rmse_t_mean'] for r in rows], height=w, color=COL[v],
                label=LAB[v])
    ax.set_yticks(y, [f'{st.loc[i, "name"]} ({st.loc[i, "elev"]:.0f} m), {sc}' for i, sc in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set(xlabel='RMSE of daily mean on the TEST period [K] (mean over folds)',
           title=f'Trend + seasonal correction (topo_compare), fitted on train, scored on test ({tag})')
    ax.legend(fontsize=8, loc='lower right')
    fig.savefig(out, dpi=110, bbox_inches='tight')
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--series', nargs='+', default=['ncar'])
    p.add_argument('--no-correction', action='store_true')
    a = p.parse_args()
    st = pd.read_csv(VAL / 'stations.csv').set_index('id')
    for series in a.series:
        od = VAL / series / 'points'
        od.mkdir(parents=True, exist_ok=True)
        tag = series.upper()
        h = load(series, st)
        rows = []
        for sid, hs in h.groupby('id'):
            hs = hs.sort_values('time')
            periods = {'2018-2025': hs[hs.time.dt.year.between(2018, 2025)]}
            if sid in LONG:
                y0, y1 = hs.time.dt.year.min(), hs.time.dt.year.max()
                periods[f'{y0}-{y1}'] = hs
            for per, hp in periods.items():
                d = daily(hp, VERS)
                if len(d) < 200:
                    continue
                for v in VERS:
                    base = dict(id=sid, name=st.loc[sid, 'name'], elev=st.loc[sid, 'elev'], period=per, version=v)
                    rows.append(dict(base, var='hourly', **metrics(hp.o, hp[v])))
                    for k in ('mean', 'max', 'min'):
                        rows.append(dict(base, var=f't_{k}', **metrics(d[f'o_{k}'], d[f'{v}_{k}'])))
            hp = hs if sid in LONG else periods['2018-2025']
            d = daily(hp, VERS)
            if len(d) >= 200:
                name = st.loc[sid, 'name']
                station_figure(hp, d, sid, name, f'{tag}, {hp.time.dt.year.min()}-{hp.time.dt.year.max()}',
                               od / f'obs_vs_down_{name}_{sid}.png')
        t = pd.DataFrame(rows)
        t.round(4).to_csv(od / 'points_stats.csv', index=False)
        rmse_figure(t, st, tag, od / 'points_rmse.png')
        show = t[t['var'] == 't_mean'].pivot_table(index=['period', 'name', 'elev'], columns='version', values='rmse')
        print(f'\n=== {series} point runs: RMSE of daily t_mean [K] ===')
        print(show[VERS].sort_index(level=['period', 'elev']).round(2).to_string(), flush=True)

        if a.no_correction:
            continue
        cv = correction_cv(h, st)
        cv.round(4).to_csv(od / 'correction_cv.csv', index=False)
        s = cv.groupby(['id', 'name', 'elev', 'scheme', 'version'])[
            ['rmse_hourly', 'bias_hourly', 'rmse_t_mean', 'rmse_t_max', 'rmse_t_min']].mean().reset_index()
        s.round(3).to_csv(od / 'correction_cv_summary.csv', index=False)
        cv_figure(s, st, tag, od / 'correction_cv.png')
        print(f'\n=== {series}: correction CV, RMSE of daily t_mean on test [K], mean over folds ===')
        print(s.pivot_table(index=['scheme', 'name', 'elev'], columns='version', values='rmse_t_mean')
              [['era5_lapse', 'era5_lapse_cor', 'ts_point', 'ts_point_cor']].sort_index(level=['scheme', 'elev'])
              .round(2).to_string(), flush=True)


if __name__ == '__main__':
    main()
