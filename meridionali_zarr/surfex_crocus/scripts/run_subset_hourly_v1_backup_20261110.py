"""
Crocus on a subset of points with HOURLY output and full snowpack profiles (HY 2024-2025, setup E).

Subset: 3 points per elevation class (<1000, 1000-1500, 1500-2000, >2000 m) x aspect (N, S), aspect consistent
(see common.points), slope 10-35 deg, nearest to a target elevation per class (800, 1250, 1750, 2200 m).
Forcing: the existing data/surfex_E/FORCING_2024090100_2025083123.nc (TopoPyScale to_surfex, unchanged values).
Namelist: snowtools OPTIONS_V8.1_NEW_OUTPUTS_NC.nam with only XTSTEP_OUTPUT 21600 -> 3600 s. Same s2m call as the
all-points run of 9 Nov 2026 (-g: initial ground temperature from the period's mean air temperature, then run).

    ~/TopoPyScale-repo-github/venv/bin/python scripts/run_subset_hourly.py
Output: hy2024-2025/subset_hourly/{subset_points.csv, FORCING_*.nc, OPTIONS_hourly.nam, s2m.log, output/pro/PRO_*.nc}
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import xarray as xr

from common import FORCING, OUT, points

PY = str(Path.home() / 'miniconda3' / 'envs' / 'surfex' / 'bin' / 'python')
SNOWTOOLS = Path.home() / 'git' / 'snowtools'
EXE = str(Path.home() / 'git' / 'surfex' / 'exe')
TARGET = {'<1000': 800, '1000-1500': 1250, '1500-2000': 1750, '>2000': 2200}


def select():
    p = points()
    p = p[(p.slope_deg >= 10) & (p.slope_deg <= 35) & p.aspect_class.isin(['N', 'S'])]
    sel = []
    for (ec, ac), g in p.groupby(['elev_class', 'aspect_class'], observed=True):
        g = g.assign(dz=(g.elevation - TARGET[ec]).abs()).nsmallest(3, 'dz')
        sel.append(g.drop(columns='dz'))
    return pd.concat(sel).sort_values(['elev_class', 'aspect_class', 'elevation']).reset_index(drop=True)


def main():
    d = OUT / 'subset_hourly'
    d.mkdir(parents=True, exist_ok=True)
    sel = select()
    sel.insert(0, 'point_in_subset', range(len(sel)))
    sel.to_csv(d / 'subset_points.csv', index=False)
    print(sel[['point_in_subset', 'point', 'elev_class', 'aspect_class', 'elevation', 'slope_deg', 'aspect_deg']]
          .round(1).to_string(index=False), flush=True)

    ff = d / FORCING.name
    with xr.open_dataset(FORCING) as f:
        sub = f.isel(Number_of_points=sel.point.values)
        assert (sub.point_ind.values == sel.point_ind.values).all()
        sub.load().to_netcdf(ff, format='NETCDF3_CLASSIC', unlimited_dims=['time'])
        t = pd.DatetimeIndex(sub.time.values)

    nam = (SNOWTOOLS / 'snowtools' / 'DATA' / 'OPTIONS_V8.1_NEW_OUTPUTS_NC.nam').read_text()
    nam, n = re.subn(r'XTSTEP_OUTPUT\s*=\s*21600\.', 'XTSTEP_OUTPUT = 3600.', nam)
    assert n == 1
    (d / 'OPTIONS_hourly.nam').write_text(nam)

    cmd = [PY, '-m', 'snowtools.tasks.s2m_command', 'research', '-b', f'{t[0]:%Y%m%d%H}', '-e', f'{t[-1]:%Y%m%d%H}',
           '-f', str(ff), '-o', 'output', '-w', 'work', '-s', EXE, '-n', str(d / 'OPTIONS_hourly.nam'), '-g']
    env = dict(os.environ, PYTHONPATH=str(SNOWTOOLS))
    env.pop('LD_LIBRARY_PATH', None)
    t0 = time.time()
    with open(d / 's2m.log', 'w') as log:
        log.write(' '.join(cmd) + '\n')
        log.flush()
        r = subprocess.run(cmd, cwd=d, env=env, stdout=log, stderr=subprocess.STDOUT)
    ok = r.returncode == 0 and 'OFFLINE ENDS CORRECTLY' in (d / 's2m.log').read_text()
    pro = sorted((d / 'output' / 'pro').glob('PRO_*.nc'))
    print(f'exit {r.returncode}, {"OK" if ok and pro else "FAILED"}, {time.time() - t0:.0f} s -> {pro}', flush=True)
    sys.exit(0 if ok and pro else 1)


if __name__ == '__main__':
    main()
