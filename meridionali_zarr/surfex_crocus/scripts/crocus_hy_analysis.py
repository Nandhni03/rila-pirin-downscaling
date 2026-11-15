"""
Snow indicators and figures from SURFEX-Crocus, hydrological year 2024-2025 (setup E, 3001 TopoSUB clusters).

v2 (10 Nov 2026): per variant (`old` = forcing of TopoPyScale main, `fix` = branch fix/aspect-azimuth-convention);
aspect classes from the terrain aspect as a compass bearing (v1 read TopoPyScale's 0 = south aspect as degrees from
north: N and S were swapped); flat clusters (< 5 deg) get no aspect class; new indicator wet_snow_days_hourly
(LWC > 0.5 % vol in any layer, hourly output). See common.py for paths.

Inputs per variant (nothing is re-run here):
  - all points, 6-hourly, full output: <run_all>/chunk_NN/output/pro/PRO_2024090100_2025083123.nc
  - all points, hourly, reduced output (HS, SWE, SNOWLIQ, SNOWDZ): <run_hourly>/chunk_NN/output/pro/PRO_*.nc
  - subset (24 points, hourly, full profiles): <out>/subset_hourly/ (scripts/run_subset_hourly.py)
  - forcing (rainfall / snowfall, hourly)

Period: forcing 2024-09-01 00 .. 2025-08-31 23 UTC; September 2024 = spin-up; analysis 2024-10-01 .. 2025-08-31.

Daily values: PRO time stamps are the END of each output step (instantaneous states; fluxes averaged over the step,
LRESETCUMUL=.TRUE.). A day D gets the stamps in (D 00 UTC, D+1 00 UTC]. HS, SWE: daily mean; LWC: daily max;
melt: daily mean rate x 86400. Rainfall/snowfall: hourly forcing summed per calendar day (UTC).

Indicator definitions (per point, analysis period):
  snow day             daily mean HS > 0.05 m
  persistent snow      runs of >= 5 consecutive snow days (same 5-day rule as the MODIS analysis, see README)
  snow onset           first day of the first persistent run
  melt-out             first snow-free day after the last persistent run
  SCD                  number of snow days inside persistent runs (SCD_all: all snow days)
  peak SWE, date       maximum daily mean SWE and its first date
  melt onset           first day, on or after the peak-SWE date, that starts >= 3 consecutive days of SWE loss > 1 mm/d
  snowfall, rainfall   sums of forcing Snowf, Rainf (mm); solid fraction = snowfall / (snowfall + rainfall)
  rain-on-snow (ROS)   day with rainfall >= 10 mm and SWE of the previous day >= 10 mm; consecutive ROS days = 1 event
  wet snow days        wet_snow_days_hourly: snow days with LWC > 0.5 % vol in at least one layer in at least one
                       hour (hourly output); wet_snow_days_any_6h: v1 definition (column LWC > 0, 6-hourly)
  bulk density at peak SWE / HS on the peak-SWE day (kg m-3)
  SW_DJF_Wm2           diagnostic: mean incoming shortwave of the forcing, Dec 2024 - Feb 2025 (W m-2)
  HS>0.8 m before 31 Jan  days 2024-10-01 .. 2025-01-31 with daily mean HS > 0.8 m (ground insulation indicator)

    ~/TopoPyScale-repo-github/venv/bin/python scripts/crocus_hy_analysis.py old|fix
Outputs in <out>: indicators_per_point.csv, indicators_by_class_aspect.csv, subset_hourly_vs_6hourly.csv,
fig_swe_hs_by_class.png, fig_indicators_vs_elevation.png, fig_profiles_<point>.png, checks.txt
"""
import importlib.util
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import BoundaryNorm, ListedColormap, LinearSegmentedColormap

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ANALYSIS_END, ANALYSIS_START, ELEV_LABELS, SUBSET, VARIANTS, points  # noqa: E402

T0 = pd.Timestamp('2024-09-01')          # 'hours since' origin of PRO and FORCING
DAYS = pd.date_range(ANALYSIS_START, ANALYSIS_END, freq='D')
HS_SNOW, PERSIST, ROS_RAIN, ROS_SWE = 0.05, 5, 10.0, 10.0
INSUL_HS, INSUL_END = 0.8, pd.Timestamp('2025-01-31')
MELT_LOSS, MELT_DAYS = 1.0, 3
WET_LWC_PCT = 0.5                         # % volume, any layer, hourly
ASPECTS = ('N', 'E', 'S', 'W')

# palette (dataviz reference instance): categorical slots 1-2 for N / S, blue ramp for sequential fields
C_N, C_S, C_GREY = '#2a78d6', '#eb6834', '#8a8983'
INK, INK2, GRID = '#2b2b29', '#5f5e59', '#e4e3df'
BLUE_RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
plt.rcParams.update({'font.size': 9, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2,
                     'ytick.color': INK2, 'axes.titlesize': 10, 'axes.titlecolor': INK, 'axes.grid': True,
                     'grid.color': GRID, 'grid.linewidth': 0.6, 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.facecolor': 'white', 'savefig.dpi': 150})


# ----------------------------------------------------------------------------------------------- reading
def day_index(hours):
    """Index into DAYS of each output stamp (stamp = end of step -> day of (stamp - 1 s)); -1 outside the period."""
    t = T0 + pd.to_timedelta(np.asarray(hours, float), 'h') - pd.Timedelta('1s')
    d = (t.normalize() - DAYS[0]).days.values
    return np.where((d >= 0) & (d < len(DAYS)), d, -1)


def daily(a, didx, how):
    """a: (time, points) -> (days, points) mean or max over the stamps of each day."""
    df = pd.DataFrame(a[didx >= 0])
    g = df.groupby(didx[didx >= 0])
    r = (g.mean() if how == 'mean' else g.max()).reindex(range(len(DAYS)))
    return r.values


def read_pro(f):
    """Daily HS, SWE, LWC max, melt, TG1 of one PRO file: dict of (days, points) arrays."""
    with xr.open_dataset(f, decode_times=False) as d:
        didx = day_index(d.time.values)
        p0 = dict(Number_of_Patches=0)
        lwc = (d.SNOWLIQ.isel(**p0) * d.SNOWDZ.isel(**p0)).sum('snow_layer', skipna=True)  # kg m-2
        return {'HS': daily(d.DSN_T_ISBA.values, didx, 'mean'),
                'SWE': daily(d.WSN_T_ISBA.values, didx, 'mean'),
                'LWC': daily(lwc.transpose('time', 'Number_of_points').values, didx, 'max'),
                'MELT': daily(d.SNOMLT_ISBA.values * 86400, didx, 'mean'),
                'TG1': daily(d.TG1.isel(**p0).values - 273.15, didx, 'mean')}


def read_all_points(n, run_all):
    out = {k: np.full((len(DAYS), n), np.nan) for k in ('HS', 'SWE', 'LWC', 'MELT', 'TG1')}
    for c in sorted(run_all.glob('chunk_*')):
        pts = pd.read_csv(c / 'points.csv').point.values
        r = read_pro(next((c / 'output' / 'pro').glob('PRO_*.nc')))
        for k in out:
            out[k][:, pts] = r[k]
        print(f'  {c.name}: {len(pts)} points', flush=True)
    return out


def read_wet_hourly(f, block=1000):
    """Daily max over hours of the max layer LWC (% vol) of one hourly PRO file: (days, points)."""
    with xr.open_dataset(f, decode_times=False) as d:
        didx = day_index(d.time.values)
        parts = []
        for i0 in range(0, d.sizes['time'], block):
            liq = d.SNOWLIQ.isel(Number_of_Patches=0, time=slice(i0, i0 + block)).values   # (t, layer, pts) kg m-3
            parts.append(np.nanmax(np.where(np.isnan(liq), -1.0, liq), axis=1) / 10.0)       # % vol; -0.1 = no snow
        return daily(np.concatenate(parts), didx, 'max')


def read_all_wet(n, run_hourly):
    out = np.full((len(DAYS), n), np.nan)
    for c in sorted(run_hourly.glob('chunk_*')):
        pts = pd.read_csv(c / 'points.csv').point.values
        out[:, pts] = read_wet_hourly(next((c / 'output' / 'pro').glob('PRO_*.nc')))
        print(f'  hourly {c.name}: {len(pts)} points', flush=True)
    return out


def read_precip(forcing, idx=None):
    """Daily rainfall and snowfall (mm) from the hourly forcing, (days, points)."""
    with xr.open_dataset(forcing) as f:
        t = pd.DatetimeIndex(f.time.values)
        d = (t.normalize() - DAYS[0]).days.values
        out = {}
        for k, v in (('RAIN', 'Rainf'), ('SNOW', 'Snowf')):
            a = f[v] if idx is None else f[v].isel(Number_of_points=idx)
            a = a.transpose('time', 'Number_of_points').values * 3600.0
            m = (d >= 0) & (d < len(DAYS))
            out[k] = pd.DataFrame(a[m]).groupby(d[m]).sum().reindex(range(len(DAYS))).values
        # diagnostic: mean incoming SW (forcing DIR_SWdown, = TopoPyScale SW on the slope; SCA_SWdown = 0), Dec-Feb
        w = np.flatnonzero((t >= '2024-12-01') & (t < '2025-03-01'))
        sw = f.DIR_SWdown.isel(time=w) if idx is None else f.DIR_SWdown.isel(time=w, Number_of_points=idx)
        out['SW_DJF'] = sw.mean('time').values
    return out


# ----------------------------------------------------------------------------------------------- indicators
def runs(b):
    """(start, end_inclusive) of True runs in a 1-D boolean array."""
    b = np.concatenate([[False], b, [False]]).astype(int)
    s = np.flatnonzero(np.diff(b) == 1)
    e = np.flatnonzero(np.diff(b) == -1) - 1
    return list(zip(s, e))


def indicators(D):
    """Per-point indicators from daily arrays (days, points). Dates as Timestamps, NaT if undefined."""
    n = D['HS'].shape[1]
    rows = []
    jan31 = (INSUL_END - DAYS[0]).days
    for p in range(n):
        hs, swe, lwc = D['HS'][:, p], D['SWE'][:, p], D['LWC'][:, p]
        rain, snow = D['RAIN'][:, p], D['SNOW'][:, p]
        snowday = hs > HS_SNOW
        pr = [r for r in runs(snowday) if r[1] - r[0] + 1 >= PERSIST]
        r = {'snowfall_mm': snow.sum(), 'rainfall_mm': rain.sum(), 'SW_DJF_Wm2': D['SW_DJF'][p]}
        r['solid_fraction'] = r['snowfall_mm'] / (r['snowfall_mm'] + r['rainfall_mm'])
        r['SCD_all'] = int(snowday.sum())
        r['SCD'] = int(sum(e - s + 1 for s, e in pr))
        r['snow_onset'] = DAYS[pr[0][0]] if pr else pd.NaT
        r['melt_out'] = (DAYS[pr[-1][1] + 1] if pr[-1][1] + 1 < len(DAYS) else pd.NaT) if pr else pd.NaT
        r['snow_at_end'] = bool(snowday[-1])
        ip = int(np.nanargmax(swe)) if np.nanmax(swe) > 0 else None
        r['peak_SWE_mm'] = float(np.nanmax(swe))
        r['peak_SWE_date'] = DAYS[ip] if ip is not None and swe[ip] > 1 else pd.NaT
        r['HS_at_peak_m'] = hs[ip] if ip is not None else np.nan
        r['density_at_peak'] = swe[ip] / hs[ip] if ip is not None and hs[ip] > 0.01 else np.nan
        r['HS_max_m'] = float(np.nanmax(hs))
        mo = pd.NaT
        if ip is not None and swe[ip] > 1:
            loss = np.diff(swe[ip:]) < -MELT_LOSS          # loss[i]: SWE(ip+i+1) < SWE(ip+i) - 1
            for s, e in runs(loss):
                if e - s + 1 >= MELT_DAYS:
                    mo = DAYS[ip + s + 1]
                    break
        r['melt_onset'] = mo
        ros = np.zeros(len(DAYS), bool)
        ros[1:] = (rain[1:] >= ROS_RAIN) & (swe[:-1] >= ROS_SWE)
        r['ROS_days'] = int(ros.sum())
        r['ROS_events'] = len(runs(ros))
        r['wet_snow_days_any_6h'] = int((snowday & (lwc > 0)).sum())
        r['wet_snow_days_hourly'] = int((snowday & (D['WETPCT'][:, p] > WET_LWC_PCT)).sum()) if 'WETPCT' in D \
            else np.nan
        r['days_HS_gt_0.8_before_31Jan'] = int((hs[:jan31 + 1] > INSUL_HS).sum())
        r['snowmelt_mm'] = np.nansum(D['MELT'][:, p])
        rows.append(r)
    return pd.DataFrame(rows)


DATE_COLS = ['snow_onset', 'peak_SWE_date', 'melt_onset', 'melt_out']
NUM_COLS = ['SCD', 'SCD_all', 'peak_SWE_mm', 'HS_max_m', 'density_at_peak', 'snowfall_mm', 'rainfall_mm',
            'solid_fraction', 'ROS_events', 'ROS_days', 'wet_snow_days_hourly', 'wet_snow_days_any_6h',
            'days_HS_gt_0.8_before_31Jan', 'SW_DJF_Wm2']


def summarise(ind):
    """Median and IQR by elevation class x aspect (N, S, all aspects). Dates via day of hydrological year."""
    rows = []
    groups = [(ec, ac) for ec in ELEV_LABELS for ac in ASPECTS + ('flat', 'all')]
    for ec, ac in groups:
        g = ind[ind.elev_class == ec]
        if ac != 'all':
            g = g[g.aspect_class == ac]
        r = {'elev_class': ec, 'aspect': ac, 'n_points': len(g), 'elev_median_m': g.elevation.median()}
        for c in DATE_COLS:
            doy = (g[c] - DAYS[0]).dt.days.dropna()
            r[f'n_{c}'] = len(doy)
            for q, nm in ((0.5, 'median'), (0.25, 'p25'), (0.75, 'p75')):
                r[f'{c}_{nm}'] = (DAYS[0] + pd.Timedelta(days=round(doy.quantile(q)))).date() if len(doy) else None
        for c in NUM_COLS:
            for q, nm in ((0.5, 'median'), (0.25, 'p25'), (0.75, 'p75')):
                r[f'{c}_{nm}'] = round(g[c].quantile(q), 3)
        r['n_snow_at_end'] = int(g.snow_at_end.sum())
        rows.append(r)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------- figures
def fig_swe_hs(D, meta, f):
    fig, ax = plt.subplots(2, 4, figsize=(13, 6), sharex=True, sharey='row', constrained_layout=True)
    for j, ec in enumerate(ELEV_LABELS):
        for ac, col in (('N', C_N), ('S', C_S)):
            m = ((meta.elev_class == ec) & (meta.aspect_class == ac)).values
            for i, (k, lab) in enumerate((('SWE', 'SWE (mm)'), ('HS', 'Snow depth HS (m)'))):
                a = D[k][:, m]
                mean = np.nanmean(a, 1)
                q1, q3 = np.nanpercentile(a, [25, 75], axis=1)
                ax[i, j].fill_between(DAYS, q1, q3, color=col, alpha=0.15, lw=0)
                ax[i, j].plot(DAYS, mean, color=col, lw=2, label=f'{ac}-facing (n={m.sum()})')
                ax[i, 0].set_ylabel(lab)
        ax[0, j].set_title(f'{ec} m')
        ax[0, j].legend(frameon=False, loc='upper left', fontsize=8)
        ax[1, j].xaxis.set_major_formatter(mdates.DateFormatter('%b'))
        ax[1, j].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[10, 12, 2, 4, 6, 8]))
    for a in ax.flat:
        a.set_ylim(bottom=0)
    fig.suptitle('Crocus HY 2024-2025, setup E: daily SWE and snow depth by elevation class and aspect '
                 '(line: mean; band: 25-75 %)', color=INK)
    fig.savefig(f)
    plt.close(fig)


def fig_vs_elevation(ind, f):
    fig, ax = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for k, (c, lab) in enumerate((('peak_SWE_mm', 'Peak SWE (mm)'), ('SCD', 'SCD (days, 5-day rule)'),
                                  ('density_at_peak', 'Bulk density at peak SWE (kg m$^{-3}$)'))):
        for ac, col, z in (('other', C_GREY, 1), ('N', C_N, 3), ('S', C_S, 2)):
            g = ind[~ind.aspect_class.isin(['N', 'S'])] if ac == 'other' else ind[ind.aspect_class == ac]
            ax[k].scatter(g.elevation, g[c], s=8, color=col, alpha=0.6, lw=0, zorder=z,
                          label={'other': 'E / W / flat'}.get(ac, f'{ac}-facing'))
        ax[k].set_xlabel('Cluster elevation (m)')
        ax[k].set_ylabel(lab)
    ax[0].legend(frameon=False, markerscale=2)
    fig.suptitle('Crocus HY 2024-2025: indicators vs elevation, all 3001 points', color=INK)
    fig.savefig(f)
    plt.close(fig)


def grain_cmap():
    p = Path.home() / 'git' / 'snowtools' / 'snowtools' / 'plots' / 'stratiprofile' / 'Dictionnaries.py'
    spec = importlib.util.spec_from_file_location('snowtools_dict', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    cols = [m.color_grain[i] for i in range(15)]
    return ListedColormap(cols), m.MEPRA_labels


def fig_profiles(pro, i, label, f, dz=0.01):
    """Time-height sections (daily at 12 UTC) of density, temperature, LWC, grain type for subset point i."""
    with xr.open_dataset(pro, decode_times=False) as d:
        t = T0 + pd.to_timedelta(d.time.values, 'h')
        sel = np.flatnonzero((t.hour == 12) & (t >= DAYS[0]) & (t <= DAYS[-1] + pd.Timedelta('1D')))
        g = d.isel(time=sel, Number_of_points=i, Number_of_Patches=0)
        th = g.SNOWDZ.values                                  # (time, layer); layer 1 = top
        fields = {'rho': g.RSN_VEG.values, 'T': g.SNOWTEMP.values - 273.15,
                  'lwc': g.SNOWLIQ.values / 10.0,             # kg m-3 -> % by volume
                  'type': g.SNOWTYPE.values}
        dates = t[sel].normalize()
    th = np.nan_to_num(th)
    top = np.nancumsum(th[:, ::-1], 1)[:, ::-1]               # height of each layer top above ground
    hmax = max(top[:, 0].max(), 0.1)
    z = np.arange(dz / 2, hmax + dz, dz)
    grid = {k: np.full((len(z), len(dates)), np.nan) for k in fields}
    for j in range(len(dates)):
        n = int((th[j] > 0).sum())
        if n == 0:
            continue
        tops = top[j, :n][::-1]                               # bottom layer first, ascending tops
        k = np.searchsorted(tops, z)
        ok = k < n
        lay = (n - 1 - k[ok])                                 # back to top-first layer index
        for key, v in fields.items():
            grid[key][ok, j] = v[j, lay]
    seq = LinearSegmentedColormap.from_list('blue', BLUE_RAMP)
    gc, glab = grain_cmap()
    x = mdates.date2num(np.append(dates, dates[-1] + pd.Timedelta('1D')))
    ye = np.append(z - dz / 2, z[-1] + dz / 2)
    fig, ax = plt.subplots(4, 1, figsize=(11, 10), sharex=True, constrained_layout=True)
    specs = [('rho', 'Density (kg m$^{-3}$)', seq, dict(vmin=50, vmax=550)),
             ('T', 'Temperature (°C)', seq.reversed(), dict(vmin=-20, vmax=0)),
             ('lwc', 'Liquid water content (% vol.)', seq, dict(vmin=0, vmax=5)),
             ('type', 'Grain type (ICSSG / MEPRA)', gc, dict(norm=BoundaryNorm(np.arange(-0.5, 15), 15)))]
    for a, (k, lab, cm, kw) in zip(ax, specs):
        cm = cm.copy()
        cm.set_bad('white')
        im = a.pcolormesh(x, ye, np.ma.masked_invalid(grid[k]), cmap=cm, shading='flat', rasterized=True, **kw)
        a.grid(False)
        a.set_ylabel('Height (m)')
        a.set_title(lab, loc='left')
        cb = fig.colorbar(im, ax=a, pad=0.01, aspect=15)
        if k == 'type':
            cb.set_ticks(range(15))
            cb.set_ticklabels(glab, fontsize=7)
    ax[-1].xaxis_date()
    ax[-1].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    fig.suptitle(f'Crocus snowpack profiles (daily at 12 UTC), {label}', color=INK)
    fig.savefig(f)
    plt.close(fig)


# ----------------------------------------------------------------------------------------------- main
VARIANT = None


def main():
    global VARIANT
    VARIANT = sys.argv[1]
    cfg = VARIANTS[VARIANT]
    OUT, FORCING = cfg['out'], cfg['forcing']
    OUT.mkdir(exist_ok=True)
    meta = points()
    print(f'[{VARIANT}] reading all-points PRO (6-hourly) ...', flush=True)
    D = read_all_points(len(meta), cfg['run_all'])
    print(f'[{VARIANT}] reading all-points PRO (hourly, reduced) ...', flush=True)
    D['WETPCT'] = read_all_wet(len(meta), cfg['run_hourly'])
    D.update(read_precip(FORCING))
    ind = pd.concat([meta, indicators(D)], axis=1)
    ind.round(4).to_csv(OUT / 'indicators_per_point.csv', index=False)
    summ = summarise(ind)
    summ.to_csv(OUT / 'indicators_by_class_aspect.csv', index=False)

    # subset: hourly full output vs the 6-hourly run for the same points
    sub_dir = OUT / 'subset_hourly'
    sub = pd.read_csv(SUBSET)
    pro_h = next((sub_dir / 'output' / 'pro').glob('PRO_*.nc'))
    Dh = read_pro(pro_h)
    Dh.update(read_precip(next(sub_dir.glob('FORCING_*.nc'))))
    Dh['WETPCT'] = read_wet_hourly(pro_h)
    ih = indicators(Dh)
    i6 = ind.iloc[sub.point.values].reset_index(drop=True)
    cmp = sub[['point', 'elev_class', 'aspect_class', 'elevation']].copy()
    for c in NUM_COLS + DATE_COLS:
        cmp[f'{c}_hourly'] = ih[c]
        cmp[f'{c}_6h'] = i6[c].values
    cmp.to_csv(OUT / 'subset_hourly_vs_6hourly.csv', index=False)

    # daily HS / SWE of all points, for the old-vs-new comparison (scripts/compare_old_new.py)
    xr.Dataset({'HS': (('day', 'point'), D['HS'].astype('float32')),
                'SWE': (('day', 'point'), D['SWE'].astype('float32'))},
               coords={'day': DAYS, 'point': meta.point.values}).to_netcdf(OUT / 'daily_hs_swe.nc')

    # figures
    fig_swe_hs(D, meta, OUT / 'fig_swe_hs_by_class.png')
    fig_vs_elevation(ind, OUT / 'fig_indicators_vs_elevation.png')
    reps = []
    for ec, ac in (('1500-2000', 'N'), ('>2000', 'N'), ('>2000', 'S')):
        g = sub[(sub.elev_class == ec) & (sub.aspect_class == ac)].sort_values('elevation')
        k = g.index[len(g) // 2]                              # middle-elevation point of the 3 (same for both variants)
        reps.append(int(k))
        r = sub.loc[k]
        lab = (f'cluster {r.point_ind} ({r.elevation:.0f} m, {ac}-facing, bearing {r.bearing:.0f}°, '
               f'slope {r.slope_deg:.0f}°), {VARIANT} forcing')
        fig_profiles(pro_h, k, lab, OUT / f'fig_profiles_{ec.replace(">", "gt").replace("<", "lt")}_{ac}'
                                         f'_cluster{r.point_ind}.png')

    # checks for the README
    L = [f'variant: {VARIANT}; forcing {FORCING}']
    hs_all = D['HS']
    L.append(f'points: {len(meta)}, days: {len(DAYS)} ({DAYS[0].date()} .. {DAYS[-1].date()})')
    L.append(f'NaN in daily HS/SWE/hourly-LWC: {int(np.isnan(hs_all).sum())}/{int(np.isnan(D["SWE"]).sum())}/'
             f'{int(np.isnan(D["WETPCT"]).sum())}')
    L.append(f'flat clusters (slope < 5 deg): {int(meta.flat.sum())}; non-flat clusters illuminated in another sector '
             f'by the old downscaling: {int(meta.old_sector_differs.sum())}')
    L.append('aspect classes: ' + meta.groupby(['elev_class', 'aspect_class'], observed=True).size()
             .unstack().to_string().replace('\n', ' | '))
    hi = ind[ind.elevation > 2000]
    L.append(f'>2000 m: {len(hi)} points; SCD min {hi.SCD.min()}, peak SWE min {hi.peak_SWE_mm.min():.0f} mm; '
             f'no persistent snow: {int(hi.snow_onset.isna().sum())}; SCD < 120 d: {int((hi.SCD < 120).sum())}')
    L.append(f'snow left on 31 Aug 2025 (HS > 0.05 m): {int(ind.snow_at_end.sum())} points, elevations '
             f'{ind[ind.snow_at_end].elevation.round().astype(int).tolist()[:20]}')
    L.append(f'peak SWE: max {ind.peak_SWE_mm.max():.0f} mm (cluster {ind.loc[ind.peak_SWE_mm.idxmax(), "point_ind"]}, '
             f'{ind.loc[ind.peak_SWE_mm.idxmax(), "elevation"]:.0f} m); > 1000 mm: {int((ind.peak_SWE_mm > 1000).sum())}')
    L.append(f'HS max: {ind.HS_max_m.max():.2f} m; > 3 m: {int((ind.HS_max_m > 3).sum())}')
    dn = ind.density_at_peak.dropna()
    L.append(f'density at peak SWE (HS>0.01): {dn.min():.0f}..{dn.max():.0f} kg m-3, median {dn.median():.0f}; '
             f'< 100: {int((dn < 100).sum())}, > 500: {int((dn > 500).sum())}')
    lo = ind[ind.elevation < 1000]
    L.append(f'<1000 m: no persistent snow at {int(lo.snow_onset.isna().sum())} of {len(lo)} points')
    L.append(f'solid fraction: {ind.solid_fraction.min():.2f}..{ind.solid_fraction.max():.2f}; '
             f'annual precipitation (Oct-Aug) {(ind.snowfall_mm + ind.rainfall_mm).min():.0f}..'
             f'{(ind.snowfall_mm + ind.rainfall_mm).max():.0f} mm')
    tg = D['TG1']
    L.append(f'TG1 (soil 0.5 cm) daily mean range: {np.nanmin(tg):.1f}..{np.nanmax(tg):.1f} degC')
    for c in ('SCD', 'peak_SWE_mm', 'wet_snow_days_hourly', 'ROS_events', 'density_at_peak'):
        dlt = (cmp[f'{c}_hourly'] - cmp[f'{c}_6h']).abs()
        L.append(f'subset (full hourly) vs all-points runs, |diff| {c}: median {dlt.median():.2f}, max {dlt.max():.2f}')
    for c in DATE_COLS:
        dd = (cmp[f'{c}_hourly'] - cmp[f'{c}_6h']).dt.days.abs()
        L.append(f'subset (full hourly) vs 6-hourly, |diff| {c} (days): median {dd.median():.1f}, max {dd.max():.0f}')
    L.append(f'profile points (subset index): {reps}')
    (OUT / 'checks.txt').write_text('\n'.join(L) + '\n')
    print('\n'.join(L))
    with pd.option_context('display.width', 250, 'display.max_columns', 30):
        print(summ[summ.aspect.isin(['N', 'S', 'all'])][
            ['elev_class', 'aspect', 'n_points', 'snow_onset_median', 'peak_SWE_mm_median',
             'peak_SWE_date_median', 'melt_out_median', 'SCD_median', 'wet_snow_days_hourly_median',
             'density_at_peak_median', 'days_HS_gt_0.8_before_31Jan_median', 'SW_DJF_Wm2_median']].to_string(index=False))


if __name__ == '__main__':
    main()
