"""
Lossless compression of a Crocus PRO_*.nc file in place (13 Nov 2026).

SURFEX writes PRO files uncompressed (NETCDF4_CLASSIC, float64). This rewrites the file with zlib level 4 + shuffle
(same format, same variables, attributes and values), checks that EVERY variable is bit-identical to the original,
and only then replaces the original. Typical gain: x8.7 for a full-output year (24 -> 2.7 GB, HY 2024-25 test).
    ../venv/bin/python meridionali_zarr/scripts/compress_pro.py <PRO_*.nc> [...]
Prints one line per file; exit 1 if any file failed (that original is left untouched).
"""
import os
import sys

import numpy as np
import xarray as xr

bad = 0
for src in sys.argv[1:]:
    tmp = src + '.zlib.tmp'
    try:
        with xr.open_dataset(src, decode_times=False, mask_and_scale=False) as d:
            enc0 = d[list(d.data_vars)[0]].encoding
            if enc0.get('zlib') or enc0.get('compression') in ('zlib', 'gzip'):
                print(f'{src}: already compressed, skipped'); continue
            d.to_netcdf(tmp, format='NETCDF4_CLASSIC',
                        encoding={v: dict(zlib=True, complevel=4, shuffle=True) for v in d.data_vars})
            with xr.open_dataset(tmp, decode_times=False, mask_and_scale=False) as e:
                same = set(d.variables) == set(e.variables) and all(
                    np.array_equal(d[v].values, e[v].values, equal_nan=d[v].dtype.kind == 'f') for v in d.variables)
        if not same:
            raise ValueError('values differ after compression')
        a, b = os.path.getsize(src), os.path.getsize(tmp)
        os.replace(tmp, src)
        print(f'{src}: {a / 1e9:.2f} -> {b / 1e9:.3f} GB (x{a / b:.1f}), identical')
    except Exception as ex:  # noqa: BLE001
        bad += 1
        if os.path.exists(tmp):
            os.remove(tmp)
        print(f'{src}: FAILED ({ex}); original kept')
sys.exit(1 if bad else 0)
