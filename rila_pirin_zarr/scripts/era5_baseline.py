"""
What the downscaling adds: raw ERA5 against the stations with the SAME hours, valid days and statistics as the
downscaled series (station_compare.py first; this reads its matched_hourly.parquet, so the sampling is identical).

Versions compared (air temperature, degC):
  era5_raw     ERA5 t2m of the nearest 0.25 deg grid cell, unchanged (no downscaling at all)
  era5_lapse   ERA5 t2m bilinear at the station + (-6.5 K/km) * (station elev - ERA5 orography there)
               (orography = z_surf / 9.80665, bilinear): the cheap alternative a downscaling has to beat
  ts_cluster   TopoSCALE, the station's cluster value (what the GeoTIFFs show)
  ts_station   TopoSCALE at station elevation (cluster + daily local lapse rate), the default of our plots
ERA5 t2m and z_surf from data/era5_600-1000hPa/<year>/ERA5.zarr (single levels, CDS; the same ERA5 surface data
as the EDH series, so this baseline holds for both). Instantaneous hh:00 like the model.

Skill score = 1 - RMSE(TopoSCALE) / RMSE(reference): > 0 the downscaling is better, 1 = perfect, < 0 worse.

    python rila_pirin_zarr/scripts/era5_baseline.py [--series ncar]
With point runs (points_setup.py, NCAR 2018-2025) also ts_point = TopoSCALE run at the station itself:
points_bias_rmse_recent.png, points_skill_recent.png, points_monthly_bias_recent.png, era5_stats_recent_points.csv.
Output data/validation/<series>/plots/: era5_stats_{recent,longterm}.csv (every station x version x variable),
era5_station_elevations.csv, era5_bias_rmse_recent.png, era5_skill_recent.png, era5_monthly_bias_recent.png,
era5_longterm_{Musala,Sandanski}.png, era5_daily_scatter_longterm.png
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import xarray as xr  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402

from station_compare import daily_from_matched  # noqa: E402  (same valid-day rule)

R = Path(__file__).resolve().parents[1]
VAL = R / 'data' / 'validation'
ERA = R / 'data' / 'era5_600-1000hPa'
G, LAPSE = 9.80665, -0.0065
VERS = ['era5_raw', 'era5_lapse', 'ts_cluster', 'ts_station']
VERS_P = VERS + ['ts_point']        # + TopoSCALE run at the station (points_setup.py), recent period only
POINTS = R / 'data' / 'points' / 'runs'
LAB = {'era5_raw': 'ERA5 raw (nearest cell)', 'era5_lapse': 'ERA5 + lapse -6.5 K/km',
       'ts_cluster': 'TopoSCALE cluster', 'ts_station': 'TopoSCALE station elev.', 'ts_point': 'TopoSCALE at station point'}
COL = {'era5_raw': '#9e9e9e', 'era5_lapse': '#e08a2c', 'ts_cluster': '#7fa7d6', 'ts_station': '#1f4e9c',
       'ts_point': '#2a9d5c'}
LONG = {'ISD156150': 'Musala', 'ISD157120': 'Sandanski'}
MONTHS = 'JFMAMJJASOND'


def era5_year(y, lat, lon):
    """Hourly t2m (degC) at the stations: nearest cell, and bilinear + lapse. lat/lon/... DataArrays dim 's'."""
    ds = xr.open_zarr(ERA / str(y) / 'ERA5.zarr')[['t2m', 'z_surf']]
    t2m = ds.t2m.load() - 273.15
    oro = ds.z_surf.isel(time=0).load() / G
    raw = t2m.sel(latitude=lat, longitude=lon, method='nearest')
    tb = t2m.interp(latitude=lat, longitude=lon)
    ob = oro.interp(latitude=lat, longitude=lon)
    return raw, tb, ob, oro.sel(latitude=lat, longitude=lon, method='nearest')


def stats(o, m):
    e = m - o
    return dict(n=len(o), bias=e.mean(), mae=e.abs().mean(), rmse=np.sqrt((e ** 2).mean()), r=np.corrcoef(o, m)[0, 1])


def table(h, d, ids, st, vers=VERS):
    """Stats per station x version x variable (hourly, daily t_mean / t_max / t_min) + skill."""
    rows = []
    for sid in ids:
        hh, dd = h[h.id == sid], d[d.id == sid]
        for v in vers:
            base = dict(id=sid, name=st.loc[sid, 'name'], source=st.loc[sid, 'source'], elev=st.loc[sid, 'elev'],
                        version=v)
            rows.append(dict(base, var='hourly', **stats(hh.o, hh[v])))
            for k in ('mean', 'max', 'min'):
                rows.append(dict(base, var=f't_{k}', **stats(dd[f'o_{k}'], dd[f'{v}_{k}'])))
    t = pd.DataFrame(rows)
    rm = t.pivot_table(index=['id', 'var'], columns='version', values='rmse')
    for ts in [v for v in vers if v.startswith('ts_')]:
        for ref in ('era5_raw', 'era5_lapse'):
            sk = (1 - rm[ts] / rm[ref]).rename(f'skill_{ts}_vs_{ref}')
            t = t.merge(sk.reset_index(), on=['id', 'var'])
    return t


def daily(h, vers=VERS):
    out = []
    for sid, q in h.groupby('id'):
        q = q.set_index('time')
        parts = [daily_from_matched(q.o, q[v])[['o_mean', 'o_max', 'o_min', 'm_mean', 'm_max', 'm_min']]
                 .rename(columns={'m_mean': f'{v}_mean', 'm_max': f'{v}_max', 'm_min': f'{v}_min'}) for v in vers]
        d = parts[0].join([p.drop(columns=['o_mean', 'o_max', 'o_min']) for p in parts[1:]])
        d.insert(0, 'id', sid)
        out.append(d.rename_axis('d').reset_index())
    return pd.concat(out, ignore_index=True)


def points_hourly(sids):
    """Hourly t (degC) of the point runs (points_setup.py), every year with a complete year_summary."""
    out = []
    for d in sorted(POINTS.glob('[0-9][0-9][0-9][0-9]')):
        z = d / 'outputs' / 'downscaled' / 'down.zarr'
        if not z.exists() or len(list((d / 'outputs' / 'months').glob('*.json'))) < 12:
            continue
        t = xr.open_zarr(z).t.load()
        names = t.point_name.values.astype(str)
        df = pd.DataFrame(t.transpose('time', 'point_ind').values - 273.15, index=pd.DatetimeIndex(t.time.values),
                          columns=names)
        df = df[[c for c in df.columns if c in set(sids)]]
        out.append(df.rename_axis('time').reset_index().melt('time', var_name='id', value_name='ts_point'))
    return pd.concat(out, ignore_index=True) if out else None


def short(st, sid):
    s = st.loc[sid]
    return f'{s["name"]} ({s.elev:.0f} m{", NOAA" if s.source == "NOAA ISD" else ""})'


def plot_bias_rmse(t, st, ids, tag, out, vers=VERS):
    q = t[t['var'] == 't_mean'].set_index(['id', 'version'])
    y = np.arange(len(ids))
    w = 0.8 / len(vers)
    fig, axs = plt.subplots(1, 2, figsize=(12, 0.42 * len(ids) + 1.8), sharey=True)
    for i, v in enumerate(vers):
        for ax, k in zip(axs, ('bias', 'rmse')):
            ax.barh(y + (i - (len(vers) - 1) / 2) * w, [q.loc[(s, v), k] for s in ids], height=w, color=COL[v], label=LAB[v])
    axs[0].axvline(0, c='k', lw=0.8)
    axs[0].set(xlabel='bias, model - station [K]', title='bias of daily mean')
    axs[1].set(xlabel='RMSE [K]', title='RMSE of daily mean')
    axs[0].set_yticks(y, [short(st, s) for s in ids], fontsize=8)
    axs[0].invert_yaxis()
    for ax in axs:
        ax.grid(axis='x', lw=0.4, alpha=0.5)
    axs[1].legend(fontsize=8, loc='lower right')
    fig.suptitle(f'{tag}: daily mean air temperature, raw ERA5 vs downscaled (same days)')
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def plot_skill(t, st, ids, tag, out, ts='ts_station'):
    cols = [('hourly', 'hourly'), ('t_mean', 'daily mean'), ('t_max', 'daily max'), ('t_min', 'daily min')]
    fig, axs = plt.subplots(1, 2, figsize=(11, 0.38 * len(ids) + 2.0), sharey=True)
    for ax, ref in zip(axs, ('era5_raw', 'era5_lapse')):
        q = t[t.version == ts].pivot_table(index='id', columns='var', values=f'skill_{ts}_vs_{ref}')
        q = q.reindex(ids)[[c for c, _ in cols]]
        im = ax.imshow(q.values, cmap='RdBu', norm=TwoSlopeNorm(0, -1, 1), aspect='auto')
        for i in range(q.shape[0]):
            for j in range(q.shape[1]):
                x = q.values[i, j]
                ax.text(j, i, f'{x:+.2f}', ha='center', va='center', fontsize=7,
                        color='white' if abs(x) > 0.6 else 'black')
        ax.set_xticks(range(len(cols)), [c for _, c in cols], fontsize=8)
        ax.set_title(f'vs {LAB[ref]}', fontsize=10)
    axs[0].set_yticks(range(len(ids)), [short(st, s) for s in ids], fontsize=8)
    fig.colorbar(im, ax=axs, shrink=0.8, label='skill = 1 - RMSE(TopoSCALE) / RMSE(ERA5); blue = downscaling better')
    fig.suptitle(f'{tag}: skill of {LAB[ts]} over raw ERA5', fontsize=11)
    fig.savefig(out, dpi=120, bbox_inches='tight')
    plt.close(fig)


def plot_monthly(d, st, ids, tag, out, show=('era5_raw', 'era5_lapse', 'ts_station')):
    d = d.assign(mo=pd.to_datetime(d.d).dt.month)
    tabs = {v: d.assign(e=d[f'{v}_mean'] - d.o_mean).pivot_table(index='id', columns='mo', values='e').reindex(ids)
            for v in show}
    vmax = max(4.0, min(10.0, max(np.nanpercentile(np.abs(x.values), 95) for x in tabs.values())))
    fig, axs = plt.subplots(1, len(show), figsize=(5.3 * len(show), 0.38 * len(ids) + 1.8), sharey=True)
    for ax, v in zip(axs, show):
        x = tabs[v].values
        im = ax.imshow(x, cmap='RdBu_r', norm=TwoSlopeNorm(0, -vmax, vmax), aspect='auto')
        for i in range(x.shape[0]):
            for j in range(x.shape[1]):
                if np.isfinite(x[i, j]):
                    ax.text(j, i, f'{x[i, j]:+.1f}', ha='center', va='center', fontsize=6,
                            color='white' if abs(x[i, j]) > 0.6 * vmax else 'black')
        ax.set_xticks(range(12), list(MONTHS), fontsize=8)
        ax.set_title(LAB[v], fontsize=10)
    axs[0].set_yticks(range(len(ids)), [short(st, s) for s in ids], fontsize=8)
    fig.colorbar(im, ax=axs, shrink=0.8, label=f'model - station [K] (colour clipped at +-{vmax:.0f})')
    fig.suptitle(f'{tag}: monthly bias of daily mean temperature', fontsize=11)
    fig.savefig(out, dpi=120, bbox_inches='tight')
    plt.close(fig)


def plot_longterm(d, sid, name, tag, out):
    q = d[d.id == sid].assign(y=pd.to_datetime(d.d).dt.year)
    agg = {'n': ('o_mean', 'size'), 'o': ('o_mean', 'mean')}
    agg.update({v: (f'{v}_mean', 'mean') for v in VERS})
    yr = q.groupby('y').agg(**agg)
    yr = yr[yr.n >= 150]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    a1.plot(yr.index, yr.o, 'k.-', label='station')
    for v in ('era5_raw', 'era5_lapse', 'ts_station'):
        a1.plot(yr.index, yr[v], '.-', color=COL[v], label=LAB[v])
        a2.plot(yr.index, yr[v] - yr.o, '.-', color=COL[v], label=LAB[v])
    a2.axhline(0, c='grey', lw=0.8)
    a1.set(ylabel='mean of valid days [degC]',
           title=f'{tag} {name}: years with >= 150 valid days (same days for every version)')
    a2.set(ylabel='bias, model - station [K]')
    a1.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def plot_scatter(d, st, ids, tag, out):
    show = ['era5_raw', 'era5_lapse', 'ts_station']
    fig, axs = plt.subplots(len(ids), 3, figsize=(10, 3.4 * len(ids)), squeeze=False)
    for r, sid in enumerate(ids):
        q = d[d.id == sid]
        lo = np.floor(min(q.o_mean.min(), *(q[f'{v}_mean'].min() for v in show)) / 5) * 5
        hi = np.ceil(max(q.o_mean.max(), *(q[f'{v}_mean'].max() for v in show)) / 5) * 5
        for c, v in enumerate(show):
            a = axs[r, c]
            k = stats(q.o_mean, q[f'{v}_mean'])
            a.scatter(q.o_mean, q[f'{v}_mean'], s=1, alpha=0.25, c=COL[v], lw=0)
            a.plot([lo, hi], [lo, hi], c='0.3', lw=1)
            a.set(xlim=(lo, hi), ylim=(lo, hi), aspect='equal')
            a.set_title(f'{short(st, sid)}\n{LAB[v]}', fontsize=8.5)
            a.text(0.03, 0.97, f'N {k["n"]}\nbias {k["bias"]:+.2f} K\nRMSE {k["rmse"]:.2f} K\nr {k["r"]:.3f}',
                   transform=a.transAxes, va='top', fontsize=7)
            a.tick_params(labelsize=7)
    fig.supxlabel('station daily mean [degC]')
    fig.supylabel('model daily mean [degC]')
    fig.suptitle(f'{tag}: daily mean temperature, raw ERA5 vs downscaled')
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--series', nargs='+', default=['ncar'])
    a = p.parse_args()
    st = pd.read_csv(VAL / 'stations.csv').set_index('id')
    for series in a.series:
        od = VAL / series / 'plots'
        od.mkdir(parents=True, exist_ok=True)
        h = pd.read_parquet(VAL / series / 'matched_hourly.parquet').rename(columns={'m': 'ts_cluster',
                                                                                     'st_m': 'ts_station'})
        sids = sorted(h.id.unique())
        lat = xr.DataArray(st.loc[sids, 'lat'].values, dims='s')
        lon = xr.DataArray(st.loc[sids, 'lon'].values, dims='s')
        zst = st.loc[sids, 'elev'].values
        parts, elev_rows = [], None
        for y in sorted(h.time.dt.year.unique()):
            raw, tb, ob, onear = era5_year(y, lat, lon)
            lap = (tb + LAPSE * (xr.DataArray(zst, dims='s') - ob)).transpose('time', 's')
            raw = raw.transpose('time', 's')
            idx = pd.DatetimeIndex(raw.time.values)
            for i, sid in enumerate(sids):
                parts.append(pd.DataFrame({'id': sid, 'time': idx, 'era5_raw': raw.isel(s=i).values,
                                           'era5_lapse': lap.isel(s=i).values}))
            if elev_rows is None:
                elev_rows = pd.DataFrame({'id': sids, 'name': st.loc[sids, 'name'].values, 'station_elev': zst,
                                          'era5_cell_elev_nearest': onear.values, 'era5_elev_bilinear': ob.values,
                                          'cluster_elev': st.loc[sids, 'cluster_elev'].values})
                elev_rows['dz_station_minus_era5'] = elev_rows.station_elev - elev_rows.era5_elev_bilinear
                elev_rows.round(1).to_csv(od / 'era5_station_elevations.csv', index=False)
            print(f'{series} {y}: ERA5 read', flush=True)
        e = pd.concat(parts, ignore_index=True)
        h = h.merge(e, on=['id', 'time'], how='left').dropna()
        pt = points_hourly(sids)
        if series == 'ncar' and pt is not None:      # the point runs use the NCAR ERA5 stores
            h = h.merge(pt, on=['id', 'time'], how='left')
        d = daily(h)
        tag = series.upper()

        # recent: 2018-2025, stations with >= 200 valid days (as station_plots.py)
        dr = d[pd.to_datetime(d.d).dt.year.between(2018, 2025)]
        n = dr.groupby('id').size()
        ids = sorted(n[n >= 200].index, key=lambda s: -st.loc[s, 'elev'])
        hr = h[h.time.dt.year.between(2018, 2025) & h.id.isin(ids)]
        tr = table(hr, dr, ids, st)
        if 'ts_point' in h:
            hp = hr.dropna(subset=['ts_point'])
            dp = daily(hp, VERS_P)
            np_ = dp.groupby('id').size()
            idp = [s for s in ids if np_.get(s, 0) >= 200]
            tp_ = table(hp[hp.id.isin(idp)], dp[dp.id.isin(idp)], idp, st, VERS_P)
            tp_.round(3).to_csv(od / 'era5_stats_recent_points.csv', index=False)
            plot_bias_rmse(tp_, st, idp, f'{tag} 2018-2025, with point runs', od / 'points_bias_rmse_recent.png',
                           VERS_P)
            plot_skill(tp_, st, idp, f'{tag} 2018-2025', od / 'points_skill_recent.png', ts='ts_point')
            plot_monthly(dp[dp.id.isin(idp)], st, idp, f'{tag} 2018-2025', od / 'points_monthly_bias_recent.png',
                         show=('era5_lapse', 'ts_station', 'ts_point'))
            sp = tp_[tp_['var'] == 't_mean'].pivot_table(index=['name', 'elev'], columns='version', values='rmse')
            print(f'\n=== {series} 2018-2025 with point runs: RMSE of daily t_mean [K] ===')
            print(sp[VERS_P].sort_index(level='elev').round(2).to_string())
        tr.round(3).to_csv(od / 'era5_stats_recent.csv', index=False)
        plot_bias_rmse(tr, st, ids, f'{tag} 2018-2025', od / 'era5_bias_rmse_recent.png')
        plot_skill(tr, st, ids, f'{tag} 2018-2025', od / 'era5_skill_recent.png')
        plot_monthly(dr, st, ids, f'{tag} 2018-2025', od / 'era5_monthly_bias_recent.png')

        # longterm: NOAA Musala and Sandanski, all years done
        ids_l = [s for s in LONG if s in set(d.id)]
        yrs = f'{pd.to_datetime(d.d).dt.year.min()}-{pd.to_datetime(d.d).dt.year.max()}'
        tl = table(h[h.id.isin(ids_l)], d[d.id.isin(ids_l)], ids_l, st)
        tl.round(3).to_csv(od / 'era5_stats_longterm.csv', index=False)
        for sid in ids_l:
            plot_longterm(d, sid, LONG[sid], f'{tag} {yrs}', od / f'era5_longterm_{LONG[sid]}.png')
        plot_scatter(d[d.id.isin(ids_l)], st, ids_l, f'{tag} {yrs}', od / 'era5_daily_scatter_longterm.png')

        show = pd.concat([tr.assign(period='2018-2025'), tl.assign(period=yrs)])
        show = show[show['var'] == 't_mean'].pivot_table(index=['period', 'name', 'elev'], columns='version',
                                                         values='rmse')[VERS].round(2)
        print(f'\n=== {series}: RMSE of daily t_mean [K] ===')
        print(show.sort_index(level=['period', 'elev']).to_string())
        print(elev_rows.round(0).to_string(index=False))


if __name__ == '__main__':
    main()
