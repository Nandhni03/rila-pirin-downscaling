"""
Daily air temperature of the downscaled series against the stations (stations_prepare.py first). Only reads the
model stores; years without a DONE marker are skipped, so it can run while the downscaling goes on.

Model at a station: the hourly t of the cluster the station pixel belongs to, taken two ways
    cluster   the cluster value, unchanged (what the GeoTIFFs show)
    station   cluster value + Gamma * (station elevation - cluster centre elevation), Gamma = the day's local lapse
              rate from the daily t_mean of the 50 nearest clusters (least squares on elevation, clipped to
              +-1.5 K / 100 m), the method of Andrei's station_compare.py / lapse_map_test.py.
Matched sampling: the model is taken only at the hours the station reported. A day counts when the station has
all 8 synoptic hours (00, 03, ... 21 UTC) or >= 20 hours. t_mean = mean of those hours (the true daily mean when
the day is hourly, the 8-synoptic mean otherwise), t_max / t_min = max / min of the same hours. So old 3-hourly
records and new hourly ones are each compared like with like.
Lag test: r of observed t_min with the model's t_min on the same day, the day before and the day after.

    python rila_pirin_zarr/scripts/validation/station_compare.py [--series ncar_v2 ncar edh] [--years 1940 2025]
Output data/validation/<series>/: matched_daily.csv (all stations, days), matched_hourly.parquet (every station hour:
o, m = cluster, st_m = station elevation; plots in station_plots.py), station_stats.csv, monthly_bias.csv,
decade_bias.csv, lag_test.csv, bias_vs_elevation.png, monthly_bias.png, longterm_<station>.png
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402

R = Path(__file__).resolve().parents[2]
VAL = R / 'data' / 'validation'
RUNS = {'ncar': R / 'data' / 'runs', 'ncar_v2': R / 'data' / 'runs_v2',   # v1 / v2 (LOG.md 2026-11-15)
        'edh': R / 'data' / 'runs_edh'}                                      # dropped 2026-11-15
K, CLIP = 50, 0.015          # neighbours, |Gamma| limit in K/m
SYN = set(range(0, 24, 3))


def lapse_neighbours(cen, pts):
    """For each station cluster: the K nearest cluster centres (by x, y), itself included."""
    xy = cen[['x', 'y']].values
    out = {}
    for p in pts:
        d = np.hypot(*(xy - xy[p]).T)
        out[p] = np.argsort(d)[:K]
    return out


def daily_gamma(t_mean, elev, nb):
    """t_mean (point, day) K, elev (point,) m -> Gamma (day,) K/m for one neighbourhood, least squares."""
    z = elev[nb] - elev[nb].mean()
    tt = t_mean[nb] - t_mean[nb].mean(axis=0)
    return np.clip((z[:, None] * tt).sum(0) / (z ** 2).sum(), -CLIP, CLIP)


def model_year(run, pts, cen, nbs):
    """Hourly model t (degC) at the station clusters, and the hourly Gamma (from the day's value)."""
    out = run / 'outputs' / 'downscaled'
    t = xr.open_zarr(out / 'down.zarr').t.sel(point_ind=pts).load()
    dm = xr.open_zarr(out / 'daily.zarr').t_mean.sel(point_name=cen.point_name.values).load()   # same order as cen
    elev = cen.elevation.values
    days = pd.DatetimeIndex(dm.time.values)
    tm = dm.transpose('point_name', 'time').values
    gam = pd.DataFrame({p: daily_gamma(tm, elev, nbs[p]) for p in pts}, index=days)
    th = pd.DataFrame(t.transpose('time', 'point_ind').values - 273.15, index=pd.DatetimeIndex(t.time.values),
                      columns=pts)
    gh = gam.reindex(th.index.floor('D')).set_axis(th.index)
    return th, gh


def daily_from_matched(obs, mod):
    """obs, mod: Series on the same hourly index -> daily t_mean / t_max / t_min for valid days."""
    df = pd.DataFrame({'o': obs, 'm': mod}).dropna()
    df['d'] = df.index.floor('D')
    df['syn'] = df.index.hour.isin(SYN)
    g = df.groupby('d')
    ok = (g.size() >= 20) | (g.syn.sum() == 8)
    agg = g.agg(o_mean=('o', 'mean'), o_max=('o', 'max'), o_min=('o', 'min'),
                m_mean=('m', 'mean'), m_max=('m', 'max'), m_min=('m', 'min'), n_hours=('o', 'size'))
    return agg[ok]


def stats(d, o, m):
    e = d[m] - d[o]
    return pd.Series(dict(n=len(d), bias=e.mean(), mae=e.abs().mean(), rmse=np.sqrt((e ** 2).mean()),
                          r=d[o].corr(d[m])))


def main():
    a = argparse.ArgumentParser()
    a.add_argument('--series', nargs='+', default=['ncar', 'edh'])
    a.add_argument('--years', nargs=2, type=int, default=[1940, 2025])
    a = a.parse_args()
    st = pd.read_csv(VAL / 'stations.csv')
    st = st[st.in_mask].reset_index(drop=True)
    cen = pd.read_pickle(R / 'data' / 'terrain' / 'outputs' / 'df_centroids.pck').sort_values('point_ind')
    cen = cen.reset_index(drop=True)
    pts = sorted(st.point_ind.astype(int).unique())
    nbs = lapse_neighbours(cen, pts)
    obs = {s.id: pd.read_csv(VAL / 'obs_hourly' / f'{s.id}.csv', parse_dates=['time_utc']).set_index('time_utc').t_c
           for s in st.itertuples()}

    for series in a.series:
        od = VAL / series
        od.mkdir(parents=True, exist_ok=True)
        rows, hrows = [], []
        years = [y for y in range(a.years[0], a.years[1] + 1) if (RUNS[series] / str(y) / 'DONE').exists()]
        for y in years:
            th, gh = model_year(RUNS[series] / str(y), pts, cen, nbs)
            for s in st.itertuples():
                o = obs[s.id]
                o = o[(o.index >= th.index[0]) & (o.index <= th.index[-1])]
                if o.empty:
                    continue
                p = int(s.point_ind)
                mc = th[p].reindex(o.index)
                ms = mc + gh[p].reindex(o.index) * (s.elev - s.cluster_elev)
                dc, ds_ = daily_from_matched(o, mc), daily_from_matched(o, ms)
                if dc.empty:
                    continue
                d = dc.join(ds_[['m_mean', 'm_max', 'm_min']].add_prefix('st_'))
                d.insert(0, 'id', s.id)
                rows.append(d.reset_index())
                h = pd.DataFrame({'o': o, 'm': mc, 'st_m': ms}).dropna()
                h.insert(0, 'id', s.id)
                hrows.append(h.rename_axis('time').reset_index())
            print(f'{series} {y}: {sum(len(r) for r in rows)} station-days so far', flush=True)
        if not rows:
            print(f'{series}: no DONE years in range')
            continue
        md = pd.concat(rows, ignore_index=True)
        md = md.merge(st[['id', 'name', 'source', 'elev', 'cluster_elev']], on='id')
        md.to_csv(od / 'matched_daily.csv', index=False)
        pd.concat(hrows, ignore_index=True).to_parquet(od / 'matched_hourly.parquet', index=False)

        res = []
        for (sid, name, src, z), d in md.groupby(['id', 'name', 'source', 'elev']):
            for v in ('mean', 'max', 'min'):
                for how, m in (('cluster', f'm_{v}'), ('station', f'st_m_{v}')):
                    res.append(dict(id=sid, name=name, source=src, elev=z, var=f't_{v}', model=how,
                                    first=d.d.min().date(), last=d.d.max().date(), **stats(d, f'o_{v}', m)))
        ss = pd.DataFrame(res)
        ss.round(3).to_csv(od / 'station_stats.csv', index=False)

        md['month'] = pd.to_datetime(md.d).dt.month
        md['decade'] = pd.to_datetime(md.d).dt.year // 10 * 10
        for v in ('mean', 'max', 'min'):
            md[f'e_{v}'] = md[f'st_m_{v}'] - md[f'o_{v}']
        md.groupby(['id', 'name', 'month'])[['e_mean', 'e_max', 'e_min']].mean().round(3).to_csv(od / 'monthly_bias.csv')
        dec = md[md.source == 'NOAA ISD'].groupby(['name', 'decade'])
        dec[['e_mean', 'e_max', 'e_min']].agg(['mean', 'count']).round(3).to_csv(od / 'decade_bias.csv')

        lag = []
        for (sid, name), d in md.groupby(['id', 'name']):
            d = d.set_index(pd.to_datetime(d.d)).asfreq('D')
            for k, lab in ((0, 'same day'), (1, 'model day before'), (-1, 'model day after')):
                lag.append(dict(id=sid, name=name, lag=lab, r_tmin=d.o_min.corr(d.st_m_min.shift(k)),
                                r_tmax=d.o_max.corr(d.st_m_max.shift(k))))
        pd.DataFrame(lag).round(4).to_csv(od / 'lag_test.csv', index=False)

        # plots
        sm = ss[(ss.model == 'station')].pivot_table(index=['name', 'elev', 'source'], columns='var', values='bias')
        sm = sm.reset_index()
        fig, ax = plt.subplots(figsize=(7, 5))
        for v, c in (('t_mean', 'k'), ('t_max', 'tab:red'), ('t_min', 'tab:blue')):
            for src, mk in (('METER.AC', 'o'), ('NOAA ISD', 's')):
                q = sm[sm.source == src]
                ax.scatter(q[v], q.elev, c=c, marker=mk, s=28, label=f'{v} ({src})')
        ax.axvline(0, c='grey', lw=0.8)
        ax.set(xlabel='model - station [K]', ylabel='station elevation [m]', title=f'{series.upper()}: bias vs elevation')
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(od / 'bias_vs_elevation.png', dpi=130)
        plt.close(fig)

        mb = md.groupby(['id', 'month']).e_mean.mean().unstack(0)
        fig, ax = plt.subplots(figsize=(8, 5))
        for c in mb:
            if c.startswith('MAC'):
                ax.plot(mb.index, mb[c], lw=0.9, color='0.65')
        ax.plot([], [], lw=0.9, color='0.65', label='METER.AC stations')
        for sid, n, c in (('ISD156150', 'Musala (NOAA)', 'tab:blue'), ('ISD157120', 'Sandanski (NOAA)', 'tab:red')):
            if sid in mb:
                ax.plot(mb.index, mb[sid], lw=2.2, color=c, label=n)
        ax.axhline(0, c='k', lw=0.8)
        ax.set(xlabel='month', ylabel='t_mean bias, model - station [K]', xticks=range(1, 13),
               title=f'{series.upper()}: monthly t_mean bias at station elevation')
        ax.legend()
        fig.tight_layout()
        fig.savefig(od / 'monthly_bias.png', dpi=130)
        plt.close(fig)

        for n in ('Musala', 'Sandanski'):
            d = md[(md.name == n) & (md.source == 'NOAA ISD')]
            if d.empty:
                continue
            yr = d.groupby(pd.to_datetime(d.d).dt.year).agg(o=('o_mean', 'mean'), m=('st_m_mean', 'mean'),
                                                             e=('e_mean', 'mean'), emax=('e_max', 'mean'),
                                                             emin=('e_min', 'mean'), n=('o_mean', 'size'))
            yr = yr[yr.n >= 150]
            fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
            a1.plot(yr.index, yr.o, 'k.-', label='station')
            a1.plot(yr.index, yr.m, 'r.-', label='model (station elevation)')
            a1.set(ylabel='mean of valid days [degC]', title=f'{series.upper()} {n}: years with >= 150 valid days '
                   '(same days in both; not a calendar-year mean)')
            a1.legend()
            for v, c in (('e', 'k'), ('emax', 'tab:red'), ('emin', 'tab:blue')):
                a2.plot(yr.index, yr[v], '.-', color=c, label={'e': 't_mean', 'emax': 't_max', 'emin': 't_min'}[v])
            a2.axhline(0, c='grey', lw=0.8)
            a2.set(ylabel='bias, model - station [K]')
            a2.legend(ncol=3)
            fig.tight_layout()
            fig.savefig(od / f'longterm_{n}.png', dpi=130)
            plt.close(fig)
            yr.round(3).to_csv(od / f'longterm_{n}.csv')

        show = ss[(ss['var'] == 't_mean')].pivot_table(index=['name', 'elev', 'source', 'n'], columns='model',
                                                       values=['bias', 'rmse', 'r']).round(2)
        print(f'\n=== {series}: t_mean, {len(years)} years ({years[0]}-{years[-1]}) ===')
        print(show.sort_index(level='elev').to_string())


if __name__ == '__main__':
    main()
