"""
Validation figures from station_compare.py output (data/validation/<series>/). Only reads those tables.

  1. Authors' view (TopoPyScale ex1_norway_finse/compare_downscaling_to_observation.ipynb,
     topo_compare.obs_vs_downscaled): HOURLY model vs station as a 2-D density (hexbin), 1:1 line, regression
     line, box with N, y = a + b x, r, RMSE, bias. Bias here = model - station (the authors' function uses
     station - model; the sign is flipped on purpose so every figure and table of ours means the same).
  2. Andrei's view (meridionali_zarr/station_compare.py, 9 Nov 2026): DAILY t_mean scatter grid, one panel per
     station, and a monthly bias heatmap (stations x months). Our daily t_mean is the mean of the station's hours
     (the true daily mean on hourly days), not (Tmax + Tmin) / 2.
  Model = value at station elevation (cluster + local lapse adjustment) unless --model cluster.

Two periods:
  recent    2018-2025, every station with >= 200 valid days (METER.AC + NOAA): the stations are comparable
  longterm  1940-2025, NOAA Musala and Sandanski only; heatmap rows = decades

    python rila_pirin_zarr/scripts/validation/station_plots.py [--series ncar_v2 ncar edh] [--model station|cluster]
Output data/validation/<series>/plots/: hourly_density_<period>.png, daily_scatter_<period>.png,
monthly_heatmap_<period>.png, hourly_stats_<period>.csv
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LogNorm, TwoSlopeNorm  # noqa: E402

R = Path(__file__).resolve().parents[2]
VAL = R / 'data' / 'validation'
LONG = ['ISD156150', 'ISD157120']
MONTHS = 'JFMAMJJASOND'


def metrics(o, m):
    o, m = np.asarray(o), np.asarray(m)
    b, a = np.polyfit(o, m, 1)
    e = m - o
    return dict(n=len(o), bias=e.mean(), rmse=np.sqrt((e ** 2).mean()), mae=np.abs(e).mean(),
                r=np.corrcoef(o, m)[0, 1], slope=b, intercept=a)


def label(st, sid):
    s = st.loc[sid]
    src = 'NOAA' if s.source == 'NOAA ISD' else 'MAC'
    return f'{s["name"]} ({s.elev:.0f} m, {src})'


def grid(n, size=3.0):
    nc = min(n, 5) if n > 4 else n
    nr = int(np.ceil(n / nc))
    fig, ax = plt.subplots(nr, nc, figsize=(size * nc, size * nr), squeeze=False)
    for a in ax.flat[n:]:
        a.set_visible(False)
    return fig, ax.flat


def panel_limits(o, m):
    lo, hi = np.floor(min(o.min(), m.min()) / 5) * 5, np.ceil(max(o.max(), m.max()) / 5) * 5
    return lo, hi


def hourly_density(h, st, ids, col, title, out):
    fig, axs = grid(len(ids))
    rows = []
    for a, sid in zip(axs, ids):
        d = h[h.id == sid]
        k = metrics(d.o, d[col])
        rows.append(dict(id=sid, name=st.loc[sid, 'name'], source=st.loc[sid, 'source'], elev=st.loc[sid, 'elev'],
                         first=d.time.min().date(), last=d.time.max().date(), **k))
        lo, hi = panel_limits(d.o, d[col])
        a.hexbin(d.o, d[col], gridsize=45, extent=(lo, hi, lo, hi), cmap='magma_r', norm=LogNorm(), mincnt=1)
        a.plot([lo, hi], [lo, hi], c='0.3', lw=1, label='1:1')
        a.plot([lo, hi], k['intercept'] + k['slope'] * np.array([lo, hi]), c='tab:blue', lw=1.2, label='regression')
        a.set(xlim=(lo, hi), ylim=(lo, hi), aspect='equal')
        a.set_title(label(st, sid), fontsize=8.5)
        a.text(0.03, 0.97, f'N {k["n"]}\ny = {k["intercept"]:.2f} + {k["slope"]:.2f}x\nr {k["r"]:.3f}\n'
               f'RMSE {k["rmse"]:.2f}\nbias {k["bias"]:+.2f}', transform=a.transAxes, va='top', fontsize=7,
               bbox=dict(boxstyle='round', fc='white', ec='0.8', alpha=0.85))
        a.tick_params(labelsize=7)
    axs[0].legend(loc='lower right', fontsize=6.5)
    fig.supxlabel('station hourly air temperature [degC]')
    fig.supylabel('model hourly t [degC]')
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return pd.DataFrame(rows)


def daily_scatter(d, st, ids, col, title, out):
    fig, axs = grid(len(ids))
    for a, sid in zip(axs, ids):
        q = d[d.id == sid]
        k = metrics(q.o_mean, q[col])
        lo, hi = panel_limits(q.o_mean, q[col])
        a.scatter(q.o_mean, q[col], s=4 if len(q) < 3000 else 1, alpha=0.5 if len(q) < 3000 else 0.25,
                  c='tab:orange', lw=0)
        a.plot([lo, hi], [lo, hi], c='0.3', lw=1)
        a.set(xlim=(lo, hi), ylim=(lo, hi), aspect='equal')
        a.set_title(label(st, sid), fontsize=8.5)
        a.text(0.03, 0.97, f'N {k["n"]}\nbias {k["bias"]:+.2f} K\nRMSE {k["rmse"]:.2f} K\nr {k["r"]:.3f}',
               transform=a.transAxes, va='top', fontsize=7)
        a.tick_params(labelsize=7)
    fig.supxlabel('station daily mean [degC]')
    fig.supylabel('model daily mean [degC]')
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def heatmap(tab, title, out, cbar_label):
    v = np.nanmax(np.abs(tab.values))
    fig, ax = plt.subplots(figsize=(9, 0.38 * len(tab) + 1.6))
    im = ax.imshow(tab.values, cmap='RdBu_r', norm=TwoSlopeNorm(0, -max(v, 0.5), max(v, 0.5)), aspect='auto')
    for i in range(tab.shape[0]):
        for j in range(tab.shape[1]):
            x = tab.values[i, j]
            if np.isfinite(x):
                ax.text(j, i, f'{x:+.1f}', ha='center', va='center', fontsize=7,
                        color='white' if abs(x) > 0.6 * v else 'black')
    ax.set_xticks(range(12), list(MONTHS))
    ax.set_yticks(range(len(tab)), tab.index)
    ax.tick_params(labelsize=8)
    fig.colorbar(im, ax=ax, shrink=0.8, label=cbar_label)
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--series', nargs='+', default=['ncar', 'edh'])
    p.add_argument('--model', default='station', choices=['station', 'cluster'])
    a = p.parse_args()
    st = pd.read_csv(VAL / 'stations.csv').set_index('id')
    hcol = 'st_m' if a.model == 'station' else 'm'
    dcol = 'st_m_mean' if a.model == 'station' else 'm_mean'
    what = 'model at station elevation' if a.model == 'station' else 'model = cluster value'
    for series in a.series:
        od = VAL / series / 'plots'
        od.mkdir(parents=True, exist_ok=True)
        h = pd.read_parquet(VAL / series / 'matched_hourly.parquet')
        d = pd.read_csv(VAL / series / 'matched_daily.csv', parse_dates=['d'])
        yrs = f'{d.d.dt.year.min()}-{d.d.dt.year.max()}'

        # recent: 2018-2025, stations with >= 200 valid days, ordered by elevation (high first)
        dr = d[d.d.dt.year.between(2018, 2025)]
        n = dr.groupby('id').size()
        ids = sorted(n[n >= 200].index, key=lambda s: -st.loc[s, 'elev'])
        hr = h[h.time.dt.year.between(2018, 2025) & h.id.isin(ids)]
        tag = series.upper()
        hs = hourly_density(hr, st, ids, hcol, f'{tag} 2018-2025: hourly air temperature, {what} '
                            '(bias = model - station)', od / 'hourly_density_recent.png')
        hs.round(3).to_csv(od / 'hourly_stats_recent.csv', index=False)
        daily_scatter(dr, st, ids, dcol, f'{tag} 2018-2025: daily mean temperature, {what}',
                      od / 'daily_scatter_recent.png')
        dr = dr.assign(e=dr[dcol] - dr.o_mean, mo=dr.d.dt.month)
        tab = dr.pivot_table(index='id', columns='mo', values='e', aggfunc='mean').reindex(ids)
        tab.index = [label(st, s) for s in ids]
        heatmap(tab, f'{tag} 2018-2025: monthly bias of daily mean temperature, {what}', od / 'monthly_heatmap_recent.png',
                'model - station [K]; blue = model colder')

        # longterm: Musala, Sandanski, all years
        ids_l = [s for s in LONG if s in set(d.id)]
        hl = h[h.id.isin(ids_l)]
        hs = hourly_density(hl, st, ids_l, hcol, f'{tag} {yrs}: hourly air temperature, NOAA stations, {what}',
                            od / 'hourly_density_longterm.png')
        hs.round(3).to_csv(od / 'hourly_stats_longterm.csv', index=False)
        dl = d[d.id.isin(ids_l)]
        daily_scatter(dl, st, ids_l, dcol, f'{tag} {yrs}: daily mean temperature, {what}',
                      od / 'daily_scatter_longterm.png')
        dl = dl.assign(e=dl[dcol] - dl.o_mean, mo=dl.d.dt.month, dec=dl.d.dt.year // 10 * 10)
        for sid in ids_l:
            q = dl[dl.id == sid]
            cnt = q.groupby('dec').size()
            q = q[q.dec.isin(cnt[cnt >= 200].index)]          # decades with >= 200 valid days
            tab = q.pivot_table(index='dec', columns='mo', values='e', aggfunc='mean')
            tab.index = [f'{x}s (n={cnt[x]})' for x in tab.index]
            nm = st.loc[sid, 'name']
            heatmap(tab, f'{tag} {nm}: monthly bias of daily mean temperature per decade, {what}',
                    od / f'monthly_heatmap_longterm_{nm}.png', 'model - station [K]; blue = model colder')
        print(f'{series}: {len(ids)} recent stations, plots in {od}', flush=True)


if __name__ == '__main__':
    main()
