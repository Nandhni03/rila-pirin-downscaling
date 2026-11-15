"""
Part 3.2 checks of the SW/aspect fix on Sep 2024 - Aug 2025 (old stores = meridionali_E_2024/2025, new stores =
meridionali_Efix_*). Writes aspect_fix/checks/*.csv and check_summary.txt; exits 1 if a check fails.

    PYTHONPATH=~/SurfexCrocus/aspect_fix/TopoPyScale_fix python scripts/check_fix.py

Aspect classes use the TERRAIN aspect (circular mean, new df_centroids), converted to a bearing:
N 315-45, E 45-135, S 135-225, W 225-315; flat clusters (slope < 5 deg) excluded.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib
import xarray as xr

from TopoPyScale import solar_geom as sg
from TopoPyScale import topo_scale_zarr as tz

D = Path.home() / 'TopoPyScale-repo-github/downscaling/meridionali_zarr/data'
OLD = [D / 'meridionali_E_2024/outputs', D / 'meridionali_E_2025/outputs']
NEW = [D / 'meridionali_Efix_2024-09_2024-12/outputs', D / 'meridionali_Efix_2025-01_2025-08/outputs']
OUT = Path(__file__).resolve().parents[1] / 'checks'
P0, P1 = pd.Timestamp('2024-09-01'), pd.Timestamp('2025-08-31 23:00')
ELEV = pd.IntervalIndex.from_breaks([-1, 1000, 1500, 2000, 9999])
LAB = ['<1000', '1000-1500', '1500-2000', '>2000']


def store(dirs):
    parts = [tz.open_downscaled_store(d / 'downscaled' / 'down.zarr') for d in dirs]
    ds = xr.concat(parts, 'time', data_vars='minimal', coords='minimal', compat='override', join='override')
    return ds.sel(time=slice(P0, P1))


def classes(df):
    b = sg.aspect_to_bearing_deg(df.aspect.values)
    a = np.where((b >= 315) | (b < 45), 'N', np.where(b < 135, 'E', np.where(b < 225, 'S', 'W')))
    a = np.where(df.flat.values, 'flat', a)
    e = pd.cut(df.elevation, [-1, 1000, 1500, 2000, 9999], labels=LAB)
    return pd.DataFrame({'elev_class': e.values, 'aspect_class': a, 'bearing': b}, index=df.index)


def season_sw(ds, cls, t0, t1, var='SW'):
    m = ds[var].sel(time=slice(t0, t1)).mean('time').values
    x = cls.assign(v=m)
    x = x[x.aspect_class != 'flat']
    return x.groupby(['elev_class', 'aspect_class'], observed=True).v.median().unstack()[['S', 'E', 'W', 'N']]


def main():
    OUT.mkdir(exist_ok=True)
    L, ok_all = [], True

    def rep(name, ok, txt):
        nonlocal ok_all
        ok_all &= bool(ok)
        L.append(f'[{"PASS" if ok else "FAIL"}] {name}: {txt}')
        print(L[-1], flush=True)

    df_new = pd.read_pickle(NEW[0] / 'df_centroids.pck')
    df_new2 = pd.read_pickle(NEW[1] / 'df_centroids.pck')
    df_old = pd.read_pickle(OLD[0] / 'df_centroids.pck')
    same = all(np.array_equal(df_new[c].values, df_new2[c].values) for c in ('point_ind', 'aspect', 'elevation'))
    rep('df_centroids of both new runs identical, aspect_R/flat kept after compute_horizon',
        same and {'aspect_R', 'flat'} <= set(df_new.columns), f'columns aspect_R, flat present: '
        f'{ {"aspect_R", "flat"} <= set(df_new.columns)}')
    cls = classes(df_new)
    old, new = store(OLD), store(NEW)
    rep('time axis', new.sizes['time'] == old.sizes['time'] == 8760 and
        (pd.Series(new.time.values).diff().dropna() == pd.Timedelta('1h')).all(),
        f'{new.sizes["time"]} hourly steps, {pd.Timestamp(new.time.values[0])} .. {pd.Timestamp(new.time.values[-1])}')
    rep('same points', np.array_equal(new.point_name.values.astype(str), old.point_name.values.astype(str)), '')

    # (f) non-shortwave variables unchanged (cluster membership unchanged by construction)
    rows = []
    for v in ('t', 'q', 'p', 'u', 'v', 'ws', 'wd', 'LW', 'tp'):
        d = float(np.abs(new[v].values - old[v].values).max())
        rows.append((v, d))
    tol = {'wd': 1e-3}
    bad = [f'{v} {d:.2e}' for v, d in rows if d > tol.get(v, 1e-6)]
    rep('(f) non-SW variables unchanged', not bad, '; '.join(f'{v} max|diff| {d:.1e}' for v, d in rows))

    # SW sanity: NaN, cap
    nn = int(new.SW.isnull().sum()) + int(new.SW_direct.isnull().sum())
    mx_old, mx_new = float(old.SW_direct.max()), float(new.SW_direct.max())
    rep('SW: no NaN, SW_direct <= S0 = 1370 W m-2', nn == 0 and mx_new <= 1370.5,
        f'NaN {nn}; SW_direct max old {mx_old:.0f}, new {mx_new:.0f} W m-2; hours > 1361 old '
        f'{int((old.SW_direct > 1361).sum())}, new {int((new.SW_direct > 1361).sum())}')

    # (c) DJF and (d) June: SW by elevation class x terrain aspect
    djf_new = season_sw(new, cls, '2024-12-01', '2025-02-28 23:00')
    djf_old = season_sw(old, cls, '2024-12-01', '2025-02-28 23:00')
    jun_new = season_sw(new, cls, '2025-06-01', '2025-06-30 23:00')
    jun_old = season_sw(old, cls, '2025-06-01', '2025-06-30 23:00')
    for nm, t in (('DJF_new', djf_new), ('DJF_old', djf_old), ('JUN_new', jun_new), ('JUN_old', jun_old)):
        t.round(1).to_csv(OUT / f'sw_{nm}.csv')
    order = ((djf_new.S > djf_new.E) & (djf_new.S > djf_new.W) & (djf_new.E > djf_new.N) & (djf_new.W > djf_new.N))
    ew = (djf_new.W - djf_new.E).abs() / djf_new[['E', 'W']].mean(1)
    rep('(c) DJF SW: S > E,W > N in every class', order.all(), '\n' + djf_new.round(1).to_string())
    rep('(c) DJF SW: E ~ W (|W-E| / mean < 10 %)', (ew < 0.10).all(),
        ', '.join(f'{c}: {100 * v:.1f} %' for c, v in ew.items()) + f' (old: ' +
        ', '.join(f'{100 * v:.1f} %' for v in ((djf_old.W - djf_old.E).abs() / djf_old[['E', 'W']].mean(1)).values) + ')')
    rdjf = (djf_new.S - djf_new.N) / djf_new[['S', 'N']].mean(1)
    rjun = (jun_new.S - jun_new.N) / jun_new[['S', 'N']].mean(1)
    rep('(d) June N/S difference much smaller than DJF (relative S-N)', (rjun < 0.5 * rdjf).all(),
        ', '.join(f'{c}: DJF {100 * a:.0f} %, June {100 * b:.0f} %' for c, a, b in zip(rdjf.index, rdjf, rjun)))

    # (b) pvlib, N and S clusters, 10-20 Dec 2024 (clear-sky pvlib at mid-hour vs TopoPyScale SW on the slope)
    pv_rows = []
    rng = np.random.default_rng(0)
    for g in ('N', 'S'):
        cand = cls[(cls.aspect_class == g) & (np.degrees(df_new.slope) > 15) & (df_new.aspect_R > 0.8)].index
        for i in rng.choice(cand, 3, replace=False):
            r = df_new.loc[i]
            k = int(np.flatnonzero(df_new.index == i)[0])
            for lab, ds, dfx in (('old', old, df_old), ('new', new, df_new)):
                s = ds.isel(point_name=k).sel(time=slice('2024-12-10', '2024-12-20 23:00'))
                t = pd.DatetimeIndex(s.time.values) - pd.Timedelta('30min')
                loc = pvlib.location.Location(r.lat, r.lon, altitude=r.elevation)
                sp = loc.get_solarposition(t.tz_localize('UTC'))
                cs = loc.get_clearsky(t.tz_localize('UTC'), solar_position=sp)
                poa = pvlib.irradiance.get_total_irradiance(np.degrees(r.slope), cls.bearing[i], sp.apparent_zenith,
                                                            sp.azimuth, cs.dni, cs.ghi, cs.dhi, model='isotropic')
                day = sp.apparent_elevation.values > 0
                sw = s.SW.values
                pv_rows.append({'group': g, 'cluster': int(r.point_ind), 'run': lab, 'elev_m': round(r.elevation),
                                'slope_deg': round(np.degrees(r.slope), 1), 'bearing_terrain': round(cls.bearing[i]),
                                'TPS_SW_mean': sw.mean().round(1), 'pvlib_clear_mean': poa.poa_global.mean().round(1),
                                'ratio_TPS_pvlib': round(sw.sum() / poa.poa_global.sum(), 3),
                                'corr_hourly': round(np.corrcoef(sw[day], poa.poa_global.values[day])[0, 1], 3)})
    pv = pd.DataFrame(pv_rows)
    pv.to_csv(OUT / 'pvlib_check_old_vs_new.csv', index=False)
    print(pv.to_string(index=False))
    pn = pv[pv.run == 'new'].groupby('group')[['ratio_TPS_pvlib', 'corr_hourly']].median()
    rep('(b) pvlib: N and S similar correlation (new)', abs(pn.corr_hourly.N - pn.corr_hourly.S) < 0.15 and
        pn.corr_hourly.min() > 0.6, pn.round(3).to_string().replace('\n', ' | '))

    # (e) horizon: deep-valley clusters, shading where horizon > solar elevation (not mirrored)
    hcols = [c for c in df_new.columns if c.startswith('hori_azi_')]
    az_bins = np.array([float(c[9:]) for c in hcols])
    hmax = df_new[hcols].max(1)
    e_rows = []
    for i in hmax.sort_values(ascending=False).index[:2]:
        r = df_new.loc[i]
        k = int(np.flatnonzero(df_new.index == i)[0])
        s = new.isel(point_name=k)
        t = pd.DatetimeIndex(s.time.values) - pd.Timedelta('30min')
        sp = pvlib.solarposition.get_solarposition(t.tz_localize('UTC'), r.lat, r.lon, r.elevation, method='nrel_numpy')
        az = 180 - sp.azimuth.values
        az = (az + 180) % 360 - 180
        el = np.radians(sp.elevation.values)
        cosi = sg.cos_illumination(np.cos(np.radians(sp.zenith.values)).clip(0), np.radians(sp.zenith.values),
                                   np.radians(az), r.slope, r.aspect)
        hz = r[hcols].values.astype(float)
        idx = pd.Index(az_bins).get_indexer(az, method='nearest')
        az_mirror = ((180 - az) + 180) % 360 - 180          # N<->S mirror in the 0 = south convention (E, W stay)
        idx_m = pd.Index(az_bins).get_indexer(az_mirror, method='nearest')
        sh, sh_m = hz[idx] > el, hz[idx_m] > el
        up = (el > 0) & (cosi > 0.05)
        dirp = s.SW_direct.values > 1.0
        e_rows.append({'cluster': int(r.point_ind), 'elev_m': round(r.elevation), 'max_horizon_deg':
                       round(np.degrees(hmax[i]), 1), 'sun_up_hours': int(up.sum()),
                       'shaded_hours': int((up & sh).sum()), 'direct_while_shaded': int((up & sh & dirp).sum()),
                       'no_direct_while_lit': int((up & ~sh & ~dirp).sum()),
                       'agreement_correct': round(float(((sh == ~dirp) & up).sum() / up.sum()), 3),
                       'agreement_mirrored': round(float(((sh_m == ~dirp) & up).sum() / up.sum()), 3)})
    ed = pd.DataFrame(e_rows)
    ed.to_csv(OUT / 'horizon_check.csv', index=False)
    print(ed.to_string(index=False))
    rep('(e) horizon: no direct SW while horizon > solar elevation; correct beats mirrored',
        (ed.direct_while_shaded == 0).all() and (ed.agreement_correct > ed.agreement_mirrored).all(),
        ed[['cluster', 'shaded_hours', 'direct_while_shaded', 'agreement_correct', 'agreement_mirrored']]
        .to_string(index=False).replace('\n', ' | '))

    # (g) aspect consistency after the circular mean
    kc = np.degrees(np.arctan2(df_new.aspect_sin, df_new.aspect_cos)) % 360     # k-means centroid direction
    dk = np.abs((np.degrees(df_new.aspect) % 360 - kc + 180) % 360 - 180)
    nf = ~df_new.flat
    old_inc = np.abs((np.degrees(df_old.aspect) % 360 - kc + 180) % 360 - 180)
    rep('(g) aspect-inconsistent clusters (> 45 deg from the k-means centroid direction, non-flat)',
        int((dk[nf] > 45).sum()) <= 10,
        f'old (arithmetic mean) {int((old_inc[nf] > 45).sum())}, new (circular) {int((dk[nf] > 45).sum())}; '
        f'flat {int(df_new.flat.sum())}; aspect_R < 0.5: {int((df_new.aspect_R < 0.5).sum())}')

    (OUT / 'check_summary.txt').write_text('\n'.join(L) + '\n')
    print('ALL CHECKS PASSED' if ok_all else 'SOME CHECKS FAILED')
    sys.exit(0 if ok_all else 1)


if __name__ == '__main__':
    main()
