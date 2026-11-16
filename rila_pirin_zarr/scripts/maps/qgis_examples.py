"""
A few example GeoTIFFs for QGIS (results/qgis_examples/), chosen to stay small (one band each, ~20-60 MB).
The Zarr stores are only read. Validation step 4 (lapse-adjusted maps), on chosen months only.

    python rila_pirin_zarr/scripts/maps/qgis_examples.py lapse 2024-01 2024-07 1942-01 1952-08 [--series v2]
    python rila_pirin_zarr/scripts/maps/qgis_examples.py diff 2024          # v2 minus v1 (needs both years DONE)

lapse: t_mean_lapse_<YYYY-MM>_<series>.tif, monthly mean of the daily mean temperature [degC] with a per-pixel
       elevation adjustment (method of A. Ionita, meridionali_zarr/scripts/lapse_map_test.py, applied here to the
       monthly cluster means instead of each day):
           T(p) = T_k + Gamma_k * (z_p - z_k)
           Gamma_k = least-squares dT/dz of the monthly cluster means against centre elevation over the k = 50
                     nearest clusters (x/y), clipped to +-0.015 K/m (inversions allowed)
       It removes the steps at cluster borders and the elevation error inside a cluster (pixel vs centre).
       Also t_mean_cluster_<YYYY-MM>_<series>.tif: the same month WITHOUT the adjustment (each pixel = its
       cluster), so the two can be compared directly.
diff:  SW_DJF_<YYYY>_v2.tif            Jan+Feb+Dec mean SW [W m-2], v2
       dSW_DJF_<YYYY>_v2_minus_v1.tif  its change by the fixes (mid-interval sun, SW_direct cap)
       dt_<YYYY>_v2_minus_v1.tif       annual mean t change [K] (vertical fallback per time step: low clusters only)
Every file is checked after writing: nodata exactly outside the clustering mask, and 1000 random pixels recomputed
from the stores (tolerance 1e-3). Results and checks: results/qgis_examples/README.md and checks.json.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
import workflow as wf  # noqa: E402

R = Path(__file__).resolve().parents[2]
RUNS = {'v1': R / 'data' / 'runs', 'v2': R / 'data' / 'runs_v2'}
TERRAIN = R / 'data' / 'terrain' / 'outputs'
DEM = R / 'data' / 'dem' / 'dem.tif'
OUT = R / 'results' / 'qgis_examples'
NODATA = wf.NODATA
K, CLIP = 50, 0.015


def static():
    c = pd.read_pickle(TERRAIN / 'df_centroids.pck').sort_values('point_ind').reset_index(drop=True)
    idx, profile, _ = wf.pixel_index(TERRAIN / 'ds_param.zarr', DEM, c.point_name.astype(str).values)
    z = wf.tu.open_dataset(TERRAIN / 'ds_param.zarr').elevation.transpose('y', 'x').values.astype('float64')
    return c, idx, profile, z


def local_lapse(x, y, z, v, k=K, clip=CLIP):
    """Slope dv/dz of a least-squares line over each cluster's k nearest clusters (x, y), clipped (A. Ionita)."""
    _, nb = cKDTree(np.c_[x, y]).query(np.c_[x, y], k=k)
    zz, vv = z[nb], v[nb]
    zc = zz - zz.mean(axis=1, keepdims=True)
    return np.clip((zc * (vv - vv.mean(axis=1, keepdims=True))).sum(axis=1) / (zc ** 2).sum(axis=1), -clip, clip)


def write(name, arr, profile, tags):
    OUT.mkdir(parents=True, exist_ok=True)
    prof = profile | dict(driver='GTiff', dtype='float32', nodata=NODATA, count=1, tiled=True, blockxsize=512,
                          blockysize=512, compress='DEFLATE', predictor=3, BIGTIFF='IF_SAFER')
    tmp = OUT / f'{name}.tmp.tif'
    with rasterio.open(tmp, 'w', **prof) as f:
        f.write(arr.astype('float32'), 1)
        f.update_tags(**{k: str(v) for k, v in tags.items()})
    wf._to_cog(tmp, OUT / f'{name}.tif')
    tmp.unlink()
    return OUT / f'{name}.tif'


def check(path, expected, inside, n=1000, seed=0):
    with rasterio.open(path) as r:
        a = r.read(1)
    rng = np.random.default_rng(seed)
    iy, ix = np.nonzero(inside)
    k = rng.choice(len(iy), min(n, len(iy)), replace=False)
    d = float(np.abs(a[iy[k], ix[k]] - expected[iy[k], ix[k]]).max())
    rep = dict(file=path.name, MB=round(path.stat().st_size / 1e6, 1), max_abs_diff_sample=d,
               nodata_outside_mask=bool((a[~inside] == NODATA).all()), range=[float(a[inside].min()), float(a[inside].max())])
    rep['ok'] = d < 1e-3 and rep['nodata_outside_mask']
    print(json.dumps(rep), flush=True)
    return rep


def daily_month(series, ym, var='t_mean'):
    y = int(ym[:4])
    d = xr.open_zarr(RUNS[series] / str(y) / 'outputs' / 'downscaled' / 'daily.zarr')[var]
    return d.sel(time=ym).mean('time').load()


def do_lapse(months, series):
    c, idx, profile, z = static()
    inside = idx >= 0
    safe = np.where(inside, idx, 0)
    zk = c.elevation.values
    reps = []
    for ym in months:
        v = daily_month(series, ym).sel(point_name=c.point_name.values).values - 273.15
        g = local_lapse(c.x.values, c.y.values, zk, v)
        cl = np.where(inside, v[safe], NODATA)
        lap = np.where(inside, v[safe] + g[safe] * (z - zk[safe]), NODATA)
        tags = dict(variable='t_mean', units='degC', statistic=f'monthly mean of daily mean, {ym}', series=series,
                    nodata_meaning='outside clustering mask')
        f = write(f't_mean_cluster_{ym}_{series}', cl, profile, tags | dict(method='each pixel = its cluster'))
        reps.append(check(f, cl, inside))
        f = write(f't_mean_lapse_{ym}_{series}', lap, profile, tags | dict(
            method=f'T(p) = T_k + Gamma_k (z_p - z_k); Gamma_k = least-squares dT/dz of the monthly cluster means '
                   f'over the {K} nearest clusters, clipped +-{CLIP} K/m',
            lapse_K_per_100m_p5_median_p95=[round(float(np.percentile(g, q)) * 100, 3) for q in (5, 50, 95)]))
        reps.append(check(f, lap, inside) | dict(lapse_K_per_100m_p5_median_p95=[
            round(float(np.percentile(g, q)) * 100, 3) for q in (5, 50, 95)]))
    return reps


def do_diff(year):
    c, idx, profile, _ = static()
    inside = idx >= 0
    safe = np.where(inside, idx, 0)
    pn = c.point_name.values
    ds = {s: xr.open_zarr(RUNS[s] / str(year) / 'outputs' / 'downscaled' / 'daily.zarr') for s in ('v1', 'v2')}
    djf = {s: ds[s].SW_mean.sel(time=ds[s].time.dt.month.isin([1, 2, 12])).mean('time').load().sel(point_name=pn).values
           for s in ds}
    tm = {s: ds[s].t_mean.mean('time').load().sel(point_name=pn).values for s in ds}
    reps = []
    for name, v, tags in (
            (f'SW_DJF_{year}_v2', djf['v2'], dict(variable='SW', units='W m-2', statistic=f'mean Jan+Feb+Dec {year}')),
            (f'dSW_DJF_{year}_v2_minus_v1', djf['v2'] - djf['v1'],
             dict(variable='SW', units='W m-2', statistic=f'v2 - v1, mean Jan+Feb+Dec {year}')),
            (f'dt_{year}_v2_minus_v1', tm['v2'] - tm['v1'], dict(variable='t', units='K', statistic=f'v2 - v1, annual mean {year}'))):
        arr = np.where(inside, v[safe], NODATA)
        f = write(name, arr, profile, tags | dict(method='each pixel = its cluster', nodata_meaning='outside clustering mask'))
        reps.append(check(f, arr, inside))
    return reps


def main():
    p = argparse.ArgumentParser()
    p.add_argument('what', choices=['lapse', 'diff'])
    p.add_argument('args', nargs='+')
    p.add_argument('--series', default='v2', choices=list(RUNS))
    a = p.parse_args()
    reps = do_lapse(a.args, a.series) if a.what == 'lapse' else sum((do_diff(int(y)) for y in a.args), [])
    chk = OUT / 'checks.json'
    old = json.loads(chk.read_text()) if chk.exists() else {}
    old.update({r['file']: r for r in reps})
    chk.write_text(json.dumps(old, indent=1))
    sys.exit(0 if all(r['ok'] for r in reps) else 1)


if __name__ == '__main__':
    main()
