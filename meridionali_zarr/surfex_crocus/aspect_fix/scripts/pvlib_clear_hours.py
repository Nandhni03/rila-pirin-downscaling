"""Diagnostic for check (b): TopoPyScale direct SW on the slope vs pvlib clear-sky beam on the slope, CLEAR hours only
(clear = the nearest flat cluster's SW >= 0.8 x pvlib clear-sky GHI), Nov 2024 - Feb 2025, old vs new."""
import numpy as np, pandas as pd, pvlib, xarray as xr
from TopoPyScale import topo_scale_zarr as tz
D = '/home/andreiionita27/TopoPyScale-repo-github/downscaling/meridionali_zarr/data/'
def store(names):
    p = [tz.open_downscaled_store(D + n + '/outputs/downscaled/down.zarr') for n in names]
    return xr.concat(p, 'time', data_vars='minimal', coords='minimal', compat='override', join='override').sel(time=slice('2024-11-01', '2025-02-28 23:00'))
old, new = store(['meridionali_E_2024', 'meridionali_E_2025']), store(['meridionali_Efix_2024-09_2024-12', 'meridionali_Efix_2025-01_2025-08'])
df = pd.read_pickle(D + 'meridionali_Efix_2024-09_2024-12/outputs/df_centroids.pck')
b = (180 - np.degrees(df.aspect)) % 360
flat = np.flatnonzero(df.flat.values)
t = pd.DatetimeIndex(new.time.values); tm = (t - pd.Timedelta('30min')).tz_localize('UTC')
rows = []
for cl in (2092, 1762, 2655, 129, 433, 269):
    i = int(np.flatnonzero(df.point_ind.values == cl)[0]); r = df.iloc[i]
    j = flat[np.argmin(np.hypot(df.x.values[flat] - r.x, df.y.values[flat] - r.y))]; rf = df.iloc[j]
    sp = pvlib.solarposition.get_solarposition(tm, r.lat, r.lon, r.elevation)
    cs = pvlib.location.Location(r.lat, r.lon, altitude=r.elevation).get_clearsky(tm, solar_position=sp)
    csf = pvlib.location.Location(rf.lat, rf.lon, altitude=rf.elevation).get_clearsky(tm)
    beam = pvlib.irradiance.beam_component(np.degrees(r.slope), b.iloc[i], sp.apparent_zenith, sp.azimuth, cs.dni).values
    hcols = [c for c in df.columns if c.startswith('hori_azi_')]; az = np.array([float(c[9:]) for c in hcols])
    hz = r[hcols].values.astype(float)[pd.Index(az).get_indexer(((180 - sp.azimuth.values) + 180) % 360 - 180, method='nearest')]
    beam = np.where(hz > np.radians(sp.apparent_elevation.values), 0, beam)       # same horizon shading
    for lab, s in (('old', old), ('new', new)):
        swf = s.SW.isel(point_name=j).values; d = s.SW_direct.isel(point_name=i).values
        clear = (sp.apparent_elevation.values > 5) & (swf >= 0.8 * csf.ghi.values) & (csf.ghi.values > 50)
        rows.append(dict(cluster=cl, facing='N' if (b.iloc[i] > 315 or b.iloc[i] < 45) else 'S', run=lab, clear_hours=int(clear.sum()),
                         TPS_direct=d[clear].mean().round(1), pvlib_beam=beam[clear].mean().round(1),
                         bias=(d[clear] - beam[clear]).mean().round(1),
                         corr=np.round(np.corrcoef(d[clear], beam[clear])[0, 1], 3) if beam[clear].std() > 1 else np.nan))
out = pd.DataFrame(rows); print(out.to_string(index=False)); out.to_csv('checks/pvlib_clear_hours_direct.csv', index=False)
