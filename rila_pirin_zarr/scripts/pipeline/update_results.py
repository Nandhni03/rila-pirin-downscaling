"""
Build rila_pirin_zarr/results/: one place to find every finished year, plus a status page.

    results/
      STATUS.md                     every year x series: done / running / downloading / queued
      ncar_v2/YYYY/                -> data/runs_v2/YYYY/outputs   FINAL: ERA5 14 levels 600-1000 hPa, fixed fork
                                                                   (branch integrate-fixes, LOG.md 2026-11-15)
      ncar_v2/t_mean_monthly/      -> t_mean_monthly_YYYY.tif     (12 bands, for QGIS)
      ncar_v1/YYYY/, t_mean_monthly/  the first NCAR series (data/runs, fork tag rila-pirin-ncar-v1), for comparison
      qgis_examples/                a few lapse-adjusted / difference GeoTIFFs (scripts/maps/, not built here)
The EDH series (data/runs_edh) was dropped on 2026-11-15 and is no longer linked.

Only years with a DONE marker (all months + checks passed) get a link. Links are relative, so they work on the host
and in the container (/app). Standard library only; safe to rerun at any time (rebuilds links + STATUS.md).

    python rila_pirin_zarr/scripts/pipeline/update_results.py          # once
    python rila_pirin_zarr/scripts/pipeline/update_results.py --every 600   # keep refreshing (used in the background)
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # rila_pirin_zarr/
DATA = ROOT / 'data'
OUT = ROOT / 'results'
YEARS = range(1940, 2026)   # 1940-1984 added 2026-11-10 (LOG.md)
SERIES = {
    'ncar_v2': dict(runs=DATA / 'runs_v2', loop=sorted((DATA / 'logs').glob('downscale_all_v2_*.log')),
                    title='NCAR v2 (final): ERA5 14 levels 600-1000 hPa, fixed TopoPyScale (SW cap, mid-interval sun, '
                          'per-step vertical fallback)'),
    'ncar_v1': dict(runs=DATA / 'runs', loop=sorted((DATA / 'logs').glob('downscale_all_2*.log')),
                    title='NCAR v1 (first series, superseded by v2): same input, fork tag rila-pirin-ncar-v1'),
}


def loop_state(logs):
    """Last loop message per year, e.g. {1985: 'downscaling'} from '[time] 1985 downscaling'."""
    st = {}
    for f in logs:
        for line in f.read_text(errors='replace').splitlines():
            parts = line.split('] ', 1)
            if len(parts) == 2 and parts[1][:4].isdigit():
                y, _, msg = parts[1].partition(' ')
                st[int(y)] = msg.strip()
    return st


def era5_state(y):
    d = DATA / 'era5_600-1000hPa' / str(y)
    if (d / 'ERA5_OK').exists():
        return 'ERA5 ready'
    m = d / 'state' / 'manifest.jsonl'
    if m.exists():
        n = sum('"status": "written"' in l for l in m.read_text(errors='replace').splitlines())
        return f'ERA5 downloading ({n} parts written)'
    return 'ERA5 queued'


def year_info(run):
    s = run / 'outputs' / 'year_summary.json'
    if not s.exists():
        return '', ''
    j = json.loads(s.read_text())
    fin = str(j.get('finished', ''))[:16]
    rng = (j.get('monthly_geotiff') or {}).get('range')
    return fin, (f'{rng[0]:.1f} .. {rng[1]:.1f}' if rng else '')


def relink(link, target):
    if link.is_symlink() or link.exists():
        if link.is_symlink() and os.readlink(link) == os.path.relpath(target, link.parent):
            return
        link.unlink()
    link.symlink_to(os.path.relpath(target, link.parent))


def build():
    OUT.mkdir(exist_ok=True)
    rows, counts = {}, {}
    for name, cfg in SERIES.items():
        sdir, tdir = OUT / name, OUT / name / 't_mean_monthly'
        tdir.mkdir(parents=True, exist_ok=True)
        loop = loop_state(cfg['loop'])
        n_done = 0
        for y in YEARS:
            run = cfg['runs'] / str(y)
            if (run / 'DONE').exists():
                n_done += 1
                fin, rng = year_info(run)
                status = f'**done** {fin}'
                relink(sdir / str(y), run / 'outputs')
                tif = run / 'outputs' / 'geotiff' / f't_mean_monthly_{y}.tif'
                if tif.exists():
                    relink(tdir / tif.name, tif)
            else:
                for stale in (sdir / str(y), tdir / f't_mean_monthly_{y}.tif'):
                    if stale.is_symlink():
                        stale.unlink()
                rng = ''
                if (run / 'FAILED').exists():
                    status = '**FAILED** (see logs)'
                elif loop.get(y) == 'downscaling' or any((run / 'logs').glob('run_year_*.log')):
                    # loop logs can go silent (stdout of a closed session), the run folder can't
                    done_m = len(list((run / 'outputs' / 'months').glob('*.json')))
                    status = f'downscaling ({done_m}/12 months)'
                else:
                    status = era5_state(y) if era5_state(y) != 'ERA5 ready' else 'queued'
            rows.setdefault(y, {})[name] = (status, rng)
        counts[name] = n_done

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    L = [f'# Rila-Pirin downscaling 1940-2025: results and status', '',
         f'Auto-generated by `scripts/pipeline/update_results.py`, last update **{now}** (refreshes every 10 min).', '',
         '| series | years done | where |', '|---|---:|---|']
    for name, cfg in SERIES.items():
        L.append(f'| {cfg["title"]} | **{counts[name]} / {len(YEARS)}** | `results/{name}/` |')
    L += ['', '**Use NCAR v2 as the final dataset.** v1 is the first run of the same input with the unfixed code; it',
          'is kept for comparison only. Do not mix v1 and v2 years in one time series.', '',
          'Each finished year `results/<series>/YYYY/` contains:', '',
          '- `downscaled/down.zarr`: hourly, 1002 clusters: t, p, q, u, v, w, ws, wd, SW, SW_direct, SW_diffuse, '
          'LW, tp',
          '- `downscaled/daily.zarr`: daily per cluster: t_mean/min/max, tp_sum, q_mean/min/max, SW(_direct/_diffuse)_mean, '
          'LW_mean, p_mean, u/v/w_mean, ws_mean/max, wd_vector_mean',
          '- `geotiff/t_mean_monthly_YYYY.tif`: monthly mean temperature [degC] on the 30 m grid, 12 bands '
          '(all of them also in `results/<series>/t_mean_monthly/`)',
          '- `year_summary.json`, `months/*.json`: QA and timings; clusters/terrain: `df_centroids.pck`, `ds_param.zarr`',
          '', '| year | NCAR v2 (final) | t range [degC] | NCAR v1 | t range [degC] |', '|---|---|---|---|---|']
    for y in YEARS:
        a, b = rows[y]['ncar_v2'], rows[y]['ncar_v1']
        L.append(f'| {y} | {a[0]} | {a[1]} | {b[0]} | {b[1]} |')
    L += ['', 'Decisions and history: `LOG.md`. Setup and commands: `README.md`. EDH (5 levels) was dropped on '
          '2026-11-15; its runs stay in data/runs_edh until deleted.', '']
    tmp = OUT / 'STATUS.md.tmp'
    tmp.write_text('\n'.join(L))
    tmp.replace(OUT / 'STATUS.md')
    return counts


if __name__ == '__main__':
    every = int(sys.argv[sys.argv.index('--every') + 1]) if '--every' in sys.argv else 0
    while True:
        try:
            c = build()
            print(datetime.now(timezone.utc).strftime('%H:%M'), c, flush=True)
        except Exception as e:                 # never let the refresher die on a half-written file
            print('update failed:', repr(e), flush=True)
        if not every:
            break
        time.sleep(every)
