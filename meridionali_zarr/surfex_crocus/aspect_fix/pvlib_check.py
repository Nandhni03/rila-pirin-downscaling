"""
Independent check of TopoPyScale shortwave on slopes against pvlib, 10-20 Dec 2024.

For true north- and south-facing clusters (slope > 15 deg, aspect consistent between linear and circular mean),
pvlib computes the clear-sky (Ineichen) beam on the tilted surface, cos(AOI) and POA global (isotropic sky), with
the cluster's surface azimuth taken in BOTH readings of TopoPyScale's `aspect`:
  H_ipw:   aspect is 0 = south, positive towards east (IPW, the solar-azimuth convention) -> azimuth_N = 180 - aspect
  H_north: aspect is degrees clockwise from north                                         -> azimuth_N = aspect
The TopoPyScale direct SW on the slope, divided by the horizontal direct, is mu_slope / mu0 * (1 - shade); the
store only has SW_direct (on slope) so we compare:
  (a) hours with TopoPyScale SW_direct > 0 while pvlib beam on the slope is 0 (geometrically impossible), and
  (b) correlation / mean ratio of hourly TopoPyScale SW (total) with pvlib POA global (clear sky, so TopoPyScale
      is expected lower on cloudy hours; the relevant number is which hypothesis correlates and which one gives
      direct SW where the slope cannot see the sun).

    python pvlib_check.py <store down.zarr> <df_centroids.pck> [--points p1,p2,...] [--label old]
"""
import argparse
import sys

import numpy as np
import pandas as pd
import pvlib

from TopoPyScale import topo_scale_zarr as tz

T0, T1 = '2024-12-10 00:00', '2024-12-20 23:00'


def pick(df, n=3):
    a = np.degrees(df.aspect.values) % 360
    c = np.degrees(np.arctan2(df.aspect_sin.values, df.aspect_cos.values)) % 360
    ok = np.abs((a - c + 180) % 360 - 180) <= 20
    s = np.degrees(df.slope.values)
    # IPW reading (0 = south): true south = aspect near 0/360, true north = near 180
    south = np.flatnonzero(ok & (s > 15) & ((c < 40) | (c > 320)))
    north = np.flatnonzero(ok & (s > 15) & (np.abs(c - 180) < 20))
    rng = np.random.default_rng(0)
    return {'S (IPW reading)': rng.choice(south, n, replace=False), 'N (IPW reading)': rng.choice(north, n, replace=False)}


def pvlib_poa(row, times, az_north):
    loc = pvlib.location.Location(row.lat, row.lon, altitude=row.elevation)
    sp = loc.get_solarposition(times)
    cs = loc.get_clearsky(times, model='ineichen', solar_position=sp)
    tilt = np.degrees(row.slope)
    poa = pvlib.irradiance.get_total_irradiance(tilt, az_north, sp.apparent_zenith, sp.azimuth,
                                                cs.dni, cs.ghi, cs.dhi, model='isotropic')
    aoi = pvlib.irradiance.aoi(tilt, az_north, sp.apparent_zenith, sp.azimuth)
    beam = np.where((aoi < 90) & (sp.apparent_zenith < 90), poa.poa_direct, 0.0)
    return pd.DataFrame({'beam': beam, 'global': poa.poa_global.values, 'elev': sp.apparent_elevation.values},
                        index=times)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('store')
    p.add_argument('centroids')
    p.add_argument('--points')
    p.add_argument('--label', default='')
    a = p.parse_args()
    df = pd.read_pickle(a.centroids)
    ds = tz.open_downscaled_store(a.store).sel(time=slice(T0, T1))
    groups = pick(df) if not a.points else {'given': np.array([int(x) for x in a.points.split(',')])}
    rows = []
    for g, idx in groups.items():
        for i in idx:
            r = df.iloc[i]
            # ERA5/TopoPyScale hourly SW is the mean over the hour ending at the stamp -> evaluate pvlib at mid-hour
            times = pd.DatetimeIndex(ds.time.values) - pd.Timedelta('30min')
            tps = ds.isel(point_name=i)
            sw, swdir = tps.SW.values, tps.SW_direct.values
            asp = np.degrees(r.aspect) % 360
            for hyp, azn in (('H_ipw', (180 - asp) % 360), ('H_north', asp)):
                pv = pvlib_poa(r, times.tz_localize('UTC'), azn)
                day = pv['elev'].values > 0
                impossible = int(((swdir > 5) & (pv.beam.values <= 0) & day).sum())
                n_dir = int(((swdir > 5) & day).sum())
                corr = np.corrcoef(sw[day], pv['global'].values[day])[0, 1]
                rows.append({'run': a.label, 'group': g, 'cluster': int(r.point_ind), 'elev_m': round(r.elevation),
                             'slope_deg': round(np.degrees(r.slope), 1), 'aspect_raw_deg': round(asp, 1),
                             'hypothesis': hyp, 'surface_azimuth_from_N': round(azn, 1),
                             'TPS_SW_mean': round(float(sw.mean()), 1), 'pvlib_clear_POA_mean': round(float(pv['global'].mean()), 1),
                             'TPS_direct_mean': round(float(swdir.mean()), 1), 'pvlib_clear_beam_mean': round(float(pv.beam.mean()), 1),
                             'bias_TPS_minus_pvlib': round(float(sw.mean() - pv['global'].mean()), 1),
                             'corr_hourly': round(float(corr), 3),
                             'hours_TPS_direct>5': n_dir, 'of_which_pvlib_beam_0': impossible})
    out = pd.DataFrame(rows)
    with pd.option_context('display.width', 250, 'display.max_columns', 30):
        print(out.to_string(index=False))
    out.to_csv(sys.stdout if False else f'pvlib_check_{a.label or "run"}.csv', index=False)


if __name__ == '__main__':
    main()
